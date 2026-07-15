"""Pure async BLE client for Novy Pureline Pro (no Home Assistant dependency)."""

from __future__ import annotations

import asyncio
import logging
import struct
from collections.abc import Callable
from typing import Any

from .const import (
    CMD_HOOD_STATUS,
    CMD_HOOD_STATUS_402,
    CMD_HOOD_STATUS_403,
    CMD_HOOD_STATUS_404,
    HOOD_STATUS_CMDS,
    RECONNECT_DELAY_S,
    REQUEST_TIMEOUT_S,
    UART_RX_CHAR_UUID,
    UART_TX_CHAR_UUID,
)
from .models import Packet400, Packet402, Packet403, Packet404

_LOGGER = logging.getLogger(__name__)

# Callback type: receives a dict of state-key -> value updates
StateCallback = Callable[[dict[str, Any]], None]

# Factory that returns an up-to-date BLEDevice (or None). Provided by the HA
# coordinator so that every connect() attempt uses the best available backend.
BLEDeviceFactory = Callable[[], Any]  # Returns bleak.backends.device.BLEDevice | None

# Seconds between polls: request the main status packet (400) every 3s.
_STATUS_CYCLE_SLEEP = 3
# Every Nth poll (~30s) also refresh the slow-changing extended status (402/403/404).
_STATUS_CYCLE_INTERVAL = 10

_STATUS_CYCLE_EXTRA_CMDS = [CMD_HOOD_STATUS, CMD_HOOD_STATUS_402, CMD_HOOD_STATUS_403, CMD_HOOD_STATUS_404]

class PurelineProClient:
    """Async BLE protocol client for the Novy Pureline Pro extractor hood.

    Manages the BLE connection and Nordic UART Service (NUS) communication.
    Parsed state is delivered via the ``on_state_update`` callback as a dict
    of state-key/value pairs that change on each received packet.

    All public methods are coroutines and must be awaited inside an
    already-running asyncio event loop.

    Args:
        address: Bluetooth MAC address of the hood (e.g. ``"AA:BB:CC:DD:EE:FF"``).
        on_state_update: Called synchronously whenever new state arrives.
        on_disconnect: Optional callback invoked on unexpected disconnection.
        ble_device_factory: Optional callable returning a BLEDevice for the
            current address; used with ``bleak_retry_connector`` when running
            inside Home Assistant.
    """

    def __init__(
        self,
        address: str,
        on_state_update: StateCallback,
        on_disconnect: Callable[[], None] | None = None,
        ble_device_factory: BLEDeviceFactory | None = None,
    ) -> None:
        self._address = address
        self._on_state_update = on_state_update
        self._on_disconnect_cb = on_disconnect
        self._ble_device_factory = ble_device_factory

        self._client: Any = None  # BleakClient at runtime
        self._poll_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        
        self._last_connect_attempt: float = 0.0
        self._connect_cooldown = 8.0   # seconds

        self.fast_count : int = 0

        # Guards against concurrent connect() calls (e.g. reconnect loop +
        # coordinator BT-advertisement callback racing each other).
        self._connecting: bool = False

        # Tracks which extended-status command (402/403/404) is in-flight so
        # _handle_notification can disambiguate Packet402 vs Packet404 (both
        # happen to be 20 bytes).
        self._pending_status_cmd: int | None = None

        # we should not start sending commands until the notification subscription is active, otherwise the device drops them on the floor and we get out of sync with pending_count
        self._notification_active : bool = False

        # Counts entity commands or status request sent but not yet ACK-ed by the device.
        # so we never overlap commands with cmds or status polls.
        self._response_future: asyncio.Future | None = None

        # Serialises all GATT writes — prevents concurrent TX from poll loop
        # and command handlers racing each other and overwhelming the BLE proxy.
        self._send_command_lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Return True when the BLE link is established."""
        return self._client is not None and self._client.is_connected

    async def connect(self) -> None:
        _LOGGER.info("connect() Pureline Pro")
        """Open the BLE connection and subscribe to NUS notifications.

        Guards against concurrent calls: if a connect attempt is already in
        progress the second caller waits for it to finish rather than returning
        immediately, so callers always see a settled is_connected state.
        """
        if self.is_connected:
            _LOGGER.debug("connect() called but already connected — skipping")
            return
        if self._connecting:
            # Another coroutine is mid-connect — wait for it to settle.
            _LOGGER.debug("connect() waiting for in-progress connect to settle")
            while self._connecting and not self.is_connected:
                await asyncio.sleep(0.2)
            # If that attempt succeeded we're done; otherwise fall through and
            # try again ourselves.
            if self.is_connected:
                _LOGGER.debug("connect() settled — already connected")
                return
            _LOGGER.debug("connect() settled — not connected, retrying")

        self._connecting = True
        try:
            await self._do_connect()
        finally:
            self._connecting = False

    async def _do_connect(self) -> None:
        """Internal: perform the actual BLE connection."""
        self._last_connect_attempt = asyncio.get_event_loop().time()
        from bleak import BleakClient  # lazy — avoids blocking import at module load

        ble_device = self._ble_device_factory() if self._ble_device_factory else None

        if ble_device is not None:
            try:
                from bleak_retry_connector import establish_connection
                self._client = await establish_connection(
                    BleakClient,
                    ble_device,
                    self._address,
                    disconnected_callback=self._on_bleak_disconnected,
                )
            except ImportError:
                # Fallback if bleak_retry_connector not available (standalone use)
                self._client = BleakClient(
                    self._address,
                    disconnected_callback=self._on_bleak_disconnected,
                )
                await self._client.connect()
        elif self._ble_device_factory is not None:
            # Factory is set (HA context) but device is not currently visible.
            # Do NOT fall back to raw BleakClient — HA's BLE stack will reject it.
            raise RuntimeError(
                f"BLE device {self._address} not found in HA registry — "
                "ensure the hood is powered on and in range"
            )
        else:
            # Standalone (non-HA) use: connect directly by address
            self._client = BleakClient(
                self._address,
                disconnected_callback=self._on_bleak_disconnected,
            )
            await self._client.connect()

        # Small settle delay: ESPHome BT proxies occasionally drop the link if
        # GATT operations start too quickly after the connection is established.
        await asyncio.sleep(0.5)

        await self._client.start_notify(UART_TX_CHAR_UUID, self._on_notification)
        _LOGGER.info("Connected to Pureline Pro %s", self._address)
        self._notification_active = True
        self.fast_count = 0

    async def disconnect(self) -> None:
        """Stop the polling loop and close the BLE connection."""
        await self.stop_polling()
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None

    async def send_command(self, cmd_id: int, *args: int) -> None:
        """Send an ASCII command frame: ``[cmd_id;arg1;arg2...]``

        Serialised via a write lock so that concurrent callers (poll loop +
        entity command handlers) never overlap GATT writes.

        Args:
            cmd_id: Command identifier (see ``const`` module).
            *args:  Optional integer arguments.

        Raises:
            BleakError: If the BLE write fails.
            RuntimeError: If not connected.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected — call connect() first")

        while not self._notification_active:
            if not self.is_connected:
                raise RuntimeError("Disconnected while waiting for notification subscription")
            _LOGGER.debug("send_command waiting for notification subscription to become active")
            await asyncio.sleep(0.2)

        if args:
            frame = f"[{cmd_id};{';'.join(str(a) for a in args)}]"
        else:
            frame = f"[{cmd_id}]"

        async with self._send_command_lock:  # This enforces "at most 1 command"
            if self._response_future and not self._response_future.done():
                # This should never happen because of the lock, but safety first
                self._response_future.cancel()

            _LOGGER.debug("TX: %s", frame)
            if cmd_id in HOOD_STATUS_CMDS:
                self._pending_status_cmd = cmd_id

            # Create a new future for this command
            loop = asyncio.get_running_loop()
            self._response_future = loop.create_future()

            try:
                await self._client.write_gatt_char(UART_RX_CHAR_UUID, frame.encode(), response=False)

                # 200 ms gap between writes — the BLE proxy and device drop the
                # connection when writes arrive too quickly (observed at RSSI ≈ -80 dBm).
                await asyncio.sleep(0.2)

                # Wait for notification or timeout
                await asyncio.wait_for(self._response_future, REQUEST_TIMEOUT_S)

            except asyncio.TimeoutError:
                _LOGGER.debug("TX failed due to timeout for: %s", frame)
                # Clean up on timeout
                if self._response_future and not self._response_future.done():
                    self._response_future.cancel()
                raise TimeoutError(f"Command '{frame}' timed out after {REQUEST_TIMEOUT_S}s")
            except Exception:
                _LOGGER.debug("TX failed for: %s", frame)
                if self._response_future and not self._response_future.done():
                    self._response_future.cancel()
                raise
            finally:
                if cmd_id in HOOD_STATUS_CMDS:
                    self._pending_status_cmd = None
                self._response_future = None  # Clean up


    async def start_polling(self) -> None:
        """Start the background polling loop (connects if not already connected)."""
        if self._poll_task and not self._poll_task.done():
            return
        self._poll_task = asyncio.ensure_future(self._poll_loop())


    async def stop_polling(self) -> None:
        """Cancel the background polling loop and suppress further auto-reconnects."""
        # Cancel any pending reconnect before it can re-establish the connection.
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        self._reconnect_task = None
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._poll_task = None

    # ------------------------------------------------------------------
    # Internal — connection management
    # ------------------------------------------------------------------

    def _on_bleak_disconnected(self, _client: Any) -> None:
        if self._client is None:
            # Already handled (callback sometimes fires multiple times via proxy)
            return
        _LOGGER.debug("Pureline Pro %s  disconnected", self._address)
        self._client = None
        # Clear all pending-response flags so any waiting send_command()
        # calls exit their loop immediately instead of waiting out the deadline.
        self._pending_status_cmd = None
        self._notification_active = False

        # Request a full 402/403/404 cycle after the next reconnect so state
        # is refreshed as soon as the connection is restored.
        if self._on_disconnect_cb:
            self._on_disconnect_cb()
        # Ensure only one reconnect task is running at a time
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.ensure_future(self._reconnect())

    async def _reconnect(self) -> None:
        attempt = 0
        while True:
            await asyncio.sleep(RECONNECT_DELAY_S * (1.5 ** attempt))  # 8s → 12s → 18s...
            attempt = min(attempt + 1, 6)  # cap backoff

            if self.is_connected:
                return

            try:
                await self.connect()
                _LOGGER.info("Reconnected successfully")
                return
            except Exception as err:
                _LOGGER.error("Reconnect attempt failed: %s", err)

    # ----------------------------------------x--------------------------
    # Internal — notification / packet parsing
    # ------------------------------------------------------------------

    def _on_notification(self, _handle: int, data: bytes) -> None:
        if self._response_future and not self._response_future.done():
            # You might want to decode/parse the data here
            try:
                response = self._handle_notification(data)
                self._response_future.set_result(response)
            except Exception as e:
                _LOGGER.debug("_on_notification exception")
                self._response_future.set_exception(e)
        else:
            # Unexpected notification (or previous one timed out)
            _LOGGER.debug("Unexpected notification: %s", data.hex())

    def can_attempt_connect(self) -> bool:
        """Return whether we're allowed to attempt a connection now."""
        if self._connecting:
            return False
        now = asyncio.get_event_loop().time()
        return now - self._last_connect_attempt >= self._connect_cooldown

    def _handle_notification(self, data: bytes) -> None:
        """Route an incoming BLE payload to the correct packet parser."""

        # ACK strings arrive as ASCII, e.g. ``[1;1;1]`` (one value per command).
        if data.startswith(b"[") and data.endswith(b"]"):
            content = data[1:-1].decode(errors="replace")
            _LOGGER.debug("ACK: [%s]", content)
            return

        size = len(data)
        state: dict[str, Any] | None = None

        _LOGGER.debug("Packet len %d payload: %s pending_cmd=%s", size, data.hex(), self._pending_status_cmd)

        if self._pending_status_cmd == CMD_HOOD_STATUS:
            state = self._parse_400(data)
            if state is None:
                _LOGGER.debug("Packet400 parse failed for %d-byte payload: %s", size, data.hex())

        elif self._pending_status_cmd == CMD_HOOD_STATUS_402:
            state = self._parse_402(data)
            if state is None:
                _LOGGER.debug("Packet402 parse failed for %d-byte payload: %s", size, data.hex())

        elif self._pending_status_cmd == CMD_HOOD_STATUS_403:
            state = self._parse_403(data)
            if state is None:
                _LOGGER.debug("Packet403 parse failed for %d-byte payload: %s", size, data.hex())

        elif self._pending_status_cmd == CMD_HOOD_STATUS_404:
            state = self._parse_404(data)
            if state is None:
                _LOGGER.debug("Packet404 parse failed for %d-byte payload: %s", size, data.hex())

        else:
            _LOGGER.error("Unhandled notification: %d bytes, pending_cmd=%s, data=%s", size, self._pending_status_cmd, data.hex())

        if state:
            self._on_state_update(state)

    # ------------------------------------------------------------------
    # Internal — individual packet parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_400(data: bytes) -> dict[str, Any] | None:
        try:
            pkt = Packet400.from_bytes(data)
        except (ValueError, struct.error) as err:
            _LOGGER.debug("Packet400 parse error: %s", err)
            return None
        return {
            "fan_state": pkt.fan_state,
            "fan_speed": pkt.fanspeed,
            "light_state": pkt.light_state,
            "light_mode": pkt.lightmode,
            "brightness": pkt.brightness,
            "brightness_pct": pkt.brightness_pct,
            "colortemp": pkt.colortemp,
            "color_temp_mireds": pkt.color_temp_mireds,
            "boost": pkt.boost,
            "stopping": pkt.stopping,
            "timer_seconds": pkt.timer_seconds,
            "grease_dirty": pkt.grease_dirty,
        }

    @staticmethod
    def _parse_402(data: bytes) -> dict[str, Any] | None:
        try:
            pkt = Packet402.from_bytes(data)
        except (ValueError, struct.error) as err:
            _LOGGER.debug("Packet402 parse error: %s", err)
            return None
        return {
            "recirculate": pkt.recirculate,
            "grease_minutes": pkt.grease_minutes,
            "firmware_version": pkt.firmware_version,
        }

    @staticmethod
    def _parse_403(data: bytes) -> dict[str, Any] | None:
        try:
            pkt = Packet403.from_bytes(data)
        except (ValueError, struct.error) as err:
            _LOGGER.debug("Packet403 parse error: %s", err)
            return None
        return {
            "fan_operating_minutes": pkt.fan_operating_minutes,
            "switch_off_fan_speed": pkt.switch_off_fan_speed,
        }

    @staticmethod
    def _parse_404(data: bytes) -> dict[str, Any] | None:
        try:
            pkt = Packet404.from_bytes(data)
        except (ValueError, struct.error) as err:
            _LOGGER.debug("Packet404 parse error: %s", err)
            return None
        return {
            "led_operating_minutes": pkt.led_operating_minutes,
        }

    # ------------------------------------------------------------------
    # Internal — polling loop
    # ------------------------------------------------------------------


    async def _run_extra_status_cycle(self) -> None:
        """Poll 402 / 403 / 404 in sequence (used at startup and after reconnect)."""
        for cmd in _STATUS_CYCLE_EXTRA_CMDS:
            if not self.is_connected:
                _LOGGER.debug("STATUS_CYCLE aborted — not connected at cmd %d", cmd)
                return
            try:
                await self.send_command(cmd, 0)
            except Exception as err:
                _LOGGER.debug("STATUS_CYCLE cmd %d error: %s", cmd, err)
            await asyncio.sleep(0.2)

    async def _poll_loop(self) -> None:
        _LOGGER.debug("Poll loop starting")

        # Wait for the first successful connection.  During HA startup the BLE
        # device is often not in the cache yet, so connect() may fail.  Rather
        # than exiting permanently we retry until either we succeed or
        # stop_polling() is called.  _on_bt_advertisement may establish the
        # connection concurrently — we'll detect that via is_connected.
        while not self.is_connected:
            try:
                await self.connect()
            except Exception as err:
                _LOGGER.warning(
                    "Initial connect failed: %s — retrying in %ds",
                    err, RECONNECT_DELAY_S,
                )
                await asyncio.sleep(RECONNECT_DELAY_S)

        _LOGGER.debug("Poll loop connected — running initial STATUS_CYCLE")

        self.fast_count = 0
        while True:
            if not self.is_connected:
                # Disconnected — reconnect is handled by _on_bleak_disconnected /
                # _reconnect() / _on_bt_advertisement.  Just wait here.
                await asyncio.sleep(1)
                continue

            try:
                if self.fast_count == 0:
                    await self._run_extra_status_cycle()
                else:
                    await self.send_command(CMD_HOOD_STATUS, 0)
                
                self.fast_count += 1
                if self.fast_count >= _STATUS_CYCLE_INTERVAL:
                    self.fast_count = 0

            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.warning("Poll error: %s", err)
            await asyncio.sleep(_STATUS_CYCLE_SLEEP)
