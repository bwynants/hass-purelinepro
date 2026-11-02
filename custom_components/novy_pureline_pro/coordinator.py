"""Home Assistant coordinator wrapping the purelinepro_ble library."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_last_service_info,
    async_register_callback,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CMD_HOOD_STATUS, CMD_FAN_STATE, CONF_ADDRESS, DOMAIN

if TYPE_CHECKING:
    from .purelinepro_ble import PurelineProClient

_LOGGER = logging.getLogger(__name__)

type PurelineProConfigEntry = ConfigEntry["PurelineProCoordinator"]


class PurelineProCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Thin HA coordinator that owns a PurelineProClient and distributes state.

    BLE device tracking strategy
    -----------------------------
    Rather than calling ``async_ble_device_from_address`` at every connect
    attempt (which fails when the device has not recently advertised), the
    coordinator registers a persistent Bluetooth callback.  Each time HA's
    scanner sees an advertisement from the hood, the callback fires and:

    * updates ``_ble_device`` with a fresh BLEDevice (including the correct
      adapter / proxy path for ``bleak_retry_connector``), and
    * triggers ``client.connect()`` if we are currently disconnected.

    The callback is unregistered automatically when the config entry is
    unloaded via ``entry.async_on_unload``.
    """

    config_entry: PurelineProConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PurelineProConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry)
        self._address: str = entry.data[CONF_ADDRESS]
        self.data: dict[str, Any] = {}
        self._ble_device: Any = None  # BLEDevice, kept fresh by BT callback

        from .purelinepro_ble import PurelineProClient  # deferred — avoids blocking import

        self._client: PurelineProClient = PurelineProClient(
            address=self._address,
            on_state_update=self._on_state_update,
            on_disconnect=self._on_disconnect,
            ble_device_factory=self._get_ble_device,
        )

        # Software auto-off countdown (mirrors C++ auto_off_timer_).
        self._auto_off_task: asyncio.Task[None] | None = None
        # Fan speed the countdown runs at (the switch-off speed). A later
        # increase means someone wants the hood back at full strength (hood
        # buttons, app or HA), so the countdown is dropped instead of
        # switching the fan off under their hands.
        self._auto_off_speed: int | None = None

    # ------------------------------------------------------------------
    # DataUpdateCoordinator hooks
    # ------------------------------------------------------------------

    async def _async_setup(self) -> None:
        """One-time setup called automatically on the first coordinator refresh."""
        _LOGGER.info("Setting up Pureline Pro %s", self._address)
        
        # Seed from HA's BT cache — try connectable first, then any advertisement.
        # Do NOT block here waiting for an advertisement: config-entry setup must
        # return promptly.  Connecting (with retries) happens in the background
        # via the poll loop and the advertisement callback registered below.
        self._ble_device = async_ble_device_from_address(
            self.hass, self._address, connectable=True
        ) or async_ble_device_from_address(
            self.hass, self._address, connectable=False
        )

        if self._ble_device:
            _LOGGER.info(
                "BT cache hit for %s on setup (connectable=%s)",
                self._address,
                getattr(self._ble_device, "connectable", "?"),
            )
        else:
            # Log what devices HA *can* see to help diagnose range / adapter issues
            last = async_last_service_info(self.hass, self._address, connectable=False)
            if last:
                _LOGGER.info(
                    "Device %s last seen at %s (rssi=%d) — not currently in cache",
                    self._address,
                    last.advertisement.local_name or last.name,
                    last.rssi,
                )
            else:
                _LOGGER.warning(
                    "Device %s not found in HA Bluetooth registry at all. "
                    "Make sure the hood is powered on and the HA Bluetooth "
                    "integration (or an ESPHome BT proxy) can reach it. "
                    "The integration will connect automatically once an "
                    "advertisement is received.",
                    self._address,
                )

        # Register a persistent callback — NOT restricted to connectable=True so
        # we catch the device even when it sends non-connectable advertisements.
        # HA calls it immediately if the device is already in the cache.
        cancel = async_register_callback(
            self.hass,
            self._on_bt_advertisement,
            BluetoothCallbackMatcher(address=self._address),
            BluetoothScanningMode.ACTIVE,
        )
        self.config_entry.async_on_unload(cancel)
        
        # Start the polling loop (connects as soon as BLEDevice becomes available)
        await self._client.start_polling()

    async def _async_update_data(self) -> dict[str, Any]:
        """Return cached state — all updates arrive as BLE push notifications."""
        return self.data

    # ------------------------------------------------------------------
    # Bluetooth advertisement callback
    # ------------------------------------------------------------------

    @callback
    def _on_bt_advertisement(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """Called by HA whenever the hood sends a BLE advertisement.

        Keeps _ble_device up-to-date (the BLEDevice carries the adapter /
        proxy path needed by bleak_retry_connector) and triggers a connect
        attempt if we are currently disconnected.
        """
        self._ble_device = service_info.device
        _LOGGER.debug(
            "Advertisement from %s  rssi=%d  connectable=%s  connected=%s",
            service_info.address,
            service_info.rssi,
            service_info.connectable,
            self._client.is_connected,
        )
        # Only attempt to connect when we have a connectable device
        if not self._client.is_connected and service_info.connectable and self._client.can_attempt_connect():
            self.hass.async_create_task(
                self._client.connect(),
                name=f"purelinepro_connect_{self._address}",
            )

    # ------------------------------------------------------------------
    # Public helpers used by entity platforms
    # ------------------------------------------------------------------

    def _get_ble_device(self) -> Any:
        """Return the most recently seen BLEDevice (for bleak_retry_connector).

        Falls back to HA's BT cache (both connectable and non-connectable) when
        the advertisement callback has not yet fired.
        """
        if self._ble_device is None:
            # Prefer connectable advertisement; fall back to any advertisement
            self._ble_device = async_ble_device_from_address(
                self.hass, self._address, connectable=True
            ) or async_ble_device_from_address(
                self.hass, self._address, connectable=False
            )
        return self._ble_device

    @property
    def available(self) -> bool:
        """Return True when the BLE link is established."""
        return self._client.is_connected

    async def disconnect(self) -> None:
        """Disconnect BLE and cancel any pending software auto-off countdown."""
        self._cancel_auto_off("disconnect")
        await self._client.disconnect()

    async def send_command(self, cmd_id: int, *args: int) -> None:
        """Forward a command to the hood via the BLE client."""
        try:
            await self._client.send_command(cmd_id, *args)
        except Exception as err:
            _LOGGER.error("send_command(%d) failed: %s", cmd_id, err)

    # ------------------------------------------------------------------
    # Callbacks from PurelineProClient
    # ------------------------------------------------------------------

    def _on_state_update(self, state: dict[str, Any]) -> None:
        """Merge incoming state and notify all HA entities."""
        previous_speed = self.data.get("fan_speed")
        self.data.update(state)
        # Cancel software auto-off if the hood's own stop-timer became active
        # (C++ comment: "we can not have 2 timers running"), if the fan has
        # been turned off by other means, or if the fan speed was raised
        # above the countdown speed: whoever did that (hood buttons, app, HA)
        # wants the hood running, the countdown must not switch it off.
        if self._auto_off_task and not self._auto_off_task.done():
            device_timer_active = state.get("stopping") and state.get("timer_seconds", 0) > 0
            fan_is_off = state.get("fan_state") is False
            # A real increase versus the last known speed is required: the
            # first status packet after the Delayed Off button may still
            # carry the pre-countdown (higher) speed, and that must not
            # cancel the countdown it belongs to.
            new_speed = state.get("fan_speed")
            speed_raised = (
                new_speed is not None
                and previous_speed is not None
                and self._auto_off_speed is not None
                and new_speed > previous_speed
                and new_speed > self._auto_off_speed
            )
            if device_timer_active or fan_is_off or speed_raised:
                self._cancel_auto_off(
                    f"device_timer={device_timer_active} fan_off={fan_is_off} "
                    f"speed_raised={speed_raised} ({previous_speed}->{new_speed})"
                )
        self.async_set_updated_data(self.data)

    def start_auto_off(self, duration_seconds: int, speed: int | None = None) -> None:
        """Start (or restart) the software delayed-off countdown.

        Runs a background task that ticks down every second, updates
        ``coordinator.data["auto_off_seconds"]`` so the Off Timer sensor
        shows the remaining time, and turns the fan off when it expires.

        Args:
            duration_seconds: Countdown length (300 s normally, 1800 s in
                recirculate mode — matches C++ 5 / 30 min logic).
            speed: Fan speed the countdown runs at. A later increase above
                it cancels the countdown (see ``_on_state_update``). None
                keeps the old behaviour: only fan-off or the device timer
                cancel it.
        """
        if self._auto_off_task and not self._auto_off_task.done():
            self._auto_off_task.cancel()
        self._auto_off_speed = speed
        self._auto_off_task = self.hass.async_create_task(
            self._auto_off_countdown(duration_seconds),
            name=f"purelinepro_auto_off_{self._address}",
        )

    def _cancel_auto_off(self, reason: str) -> None:
        """Drop a running software countdown, if any, without touching the fan."""
        if self._auto_off_task and not self._auto_off_task.done():
            _LOGGER.debug("Auto-off cancelled (%s)", reason)
            self._auto_off_task.cancel()
        self._auto_off_task = None
        self._auto_off_speed = None
        self.data["auto_off_seconds"] = 0

    async def _auto_off_countdown(self, duration_seconds: int) -> None:
        """Countdown coroutine: ticks every second and turns the fan off at 0."""
        remaining = duration_seconds
        try:
            while remaining > 0:
                self.data["auto_off_seconds"] = remaining
                self.async_set_updated_data(self.data)
                await asyncio.sleep(1)
                remaining -= 1
            # Countdown finished — turn fan off
            _LOGGER.info("Auto-off timer expired — turning fan off")
            self.data["auto_off_seconds"] = 0
            self.async_set_updated_data(self.data)
            self._auto_off_speed = None
            await self.send_command(CMD_FAN_STATE, 1, 0)
            await self.send_command(CMD_HOOD_STATUS, 0)
        except asyncio.CancelledError:
            self._auto_off_speed = None
            self.data["auto_off_seconds"] = 0
            self.async_set_updated_data(self.data)
            raise

    def _on_disconnect(self) -> None:
        _LOGGER.debug("Pureline Pro %s disconnected", self._address)
        # PurelineProClient handles automatic reconnect; _on_bt_advertisement
        # will re-seed _ble_device when the hood starts advertising again.
