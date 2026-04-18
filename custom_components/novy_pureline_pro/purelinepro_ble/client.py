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
    CMD_FAN_RECIRCULATE,
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

        # Guards against concurrent connect() calls (e.g. reconnect loop +
        # coordinator BT-advertisement callback racing each other).
        self._connecting: bool = False

        # Tracks which extended-status command (402/403/404) is in-flight so
        # _handle_notification can disambiguate Packet402 vs Packet404 (both
        # happen to be 20 bytes).
        self._pending_status_cmd: int | None = None

        # Counts entity commands or status request sent but not yet ACK-ed by the device.
        # so we never overlap commands with cmds or status polls.
        self._pending_count: int = 0

        # Serialises all GATT writes — prevents concurrent TX from poll loop
        # and command handlers racing each other and overwhelming the BLE proxy.
        self._write_lock: asyncio.Lock = asyncio.Lock()

        # Set by _on_bleak_disconnected so the poll loop re-runs the
        # 402/403/404 STATUS_CYCLE immediately after reconnect.
        self._full_cycle_needed: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Return True when the BLE link is established."""
        return self._client is not None and self._client.is_connected

    async def connect(self) -> None:
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
            while self._connecting:
                await asyncio.sleep(0.1)
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
        if args:
            frame = f"[{cmd_id};{';'.join(str(a) for a in args)}]"
        else:
            frame = f"[{cmd_id}]"

        # Wait for any previous commands before sending a new one 
        ack_deadline = asyncio.get_event_loop().time() + REQUEST_TIMEOUT_S
        while self._pending_count > 0:
            _LOGGER.debug("waiting for pending responses before TX %s", frame)
            if asyncio.get_event_loop().time() > ack_deadline:
                _LOGGER.error(
                    "Timed out waiting for %d pending response before TX %s — proceeding",
                    self._pending_count,
                    frame,
                )
                self._pending_count = 0
                break
            await asyncio.sleep(0.1)

        async with self._write_lock:
            _LOGGER.debug("TX: %s", frame)
            if cmd_id in HOOD_STATUS_CMDS:
                self._pending_status_cmd = cmd_id
            # Track entity commands (not status polls) so request_status can
            # wait for ACKs before issuing a new 40x request.
            self._pending_count += 1
            try:
                await self._client.write_gatt_char(UART_RX_CHAR_UUID, frame.encode(), response=False)
            # 300 ms gap between writes — the BLE proxy and device drop the
            # connection when writes arrive too quickly (observed at RSSI ≈ -80 dBm).
            #await asyncio.sleep(0.3)
            except Exception:
                _LOGGER.debug("TX failed for: %s", frame)
                self._pending_count -= 1
                if cmd_id in HOOD_STATUS_CMDS:
                    self._pending_status_cmd = None
                raise
        if cmd_id is CMD_FAN_RECIRCULATE:
            # force an immediate state refresh after recirculate toggle
            await self.send_command(CMD_HOOD_STATUS_402, 0)

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
        _LOGGER.warning("Pureline Pro %s unexpectedly disconnected", self._address)
        self._client = None
        # Clear all pending-response flags so any waiting send_command()
        # calls exit their loop immediately instead of waiting out the deadline.
        self._pending_status_cmd = None
        self._pending_count = 0
        # Request a full 402/403/404 cycle after the next reconnect so state
        # is refreshed as soon as the connection is restored.
        self._full_cycle_needed = True
        if self._on_disconnect_cb:
            self._on_disconnect_cb()
        # Ensure only one reconnect task is running at a time
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.ensure_future(self._reconnect())

    async def _reconnect(self) -> None:
        await asyncio.sleep(RECONNECT_DELAY_S)
        try:
            await self.connect()
        except Exception as err:
            _LOGGER.error("Reconnect failed: %s — retrying", err)
            self._reconnect_task = asyncio.ensure_future(self._reconnect())

    # ------------------------------------------------------------------
    # Internal — notification / packet parsing
    # ------------------------------------------------------------------

    def _on_notification(self, _handle: int, data: bytes) -> None:
        asyncio.ensure_future(self._handle_notification(data))

    async def _handle_notification(self, data: bytes) -> None:
        """Route an incoming BLE payload to the correct packet parser."""

        self._pending_count = max(0, self._pending_count - 1)

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
            self._pending_status_cmd = None
            if state is None:
                _LOGGER.debug("Packet400 parse failed for %d-byte payload: %s", size, data.hex())

        elif self._pending_status_cmd == CMD_HOOD_STATUS_402:
            state = self._parse_402(data)
            self._pending_status_cmd = None
            if state is None:
                _LOGGER.debug("Packet402 parse failed for %d-byte payload: %s", size, data.hex())

        elif self._pending_status_cmd == CMD_HOOD_STATUS_403:
            state = self._parse_403(data)
            self._pending_status_cmd = None
            if state is None:
                _LOGGER.debug("Packet403 parse failed for %d-byte payload: %s", size, data.hex())

        elif self._pending_status_cmd == CMD_HOOD_STATUS_404:
            state = self._parse_404(data)
            self._pending_status_cmd = None
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

    STATUS_CYCLE_INTERVAL = 30  # poll 402/403/404 once every 30 seconds
    _STATUS_CYCLE = [CMD_HOOD_STATUS_402, CMD_HOOD_STATUS_403, CMD_HOOD_STATUS_404]

    async def _run_status_cycle(self) -> None:
        """Poll 402 / 403 / 404 in sequence (used at startup and after reconnect)."""
        _LOGGER.debug("STATUS_CYCLE starting (connected=%s)", self.is_connected)
        for cmd in self._STATUS_CYCLE:
            if not self.is_connected:
                _LOGGER.debug("STATUS_CYCLE aborted — not connected at cmd %d", cmd)
                return
            try:
                await self.send_command(cmd, 0)
            except Exception as err:
                _LOGGER.debug("STATUS_CYCLE cmd %d error: %s", cmd, err)
            await asyncio.sleep(0.5)
        _LOGGER.debug("STATUS_CYCLE complete")

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
        await self._run_status_cycle()

        fast_count = 0
        cycle_index = 0
        while True:
            # After a reconnect, re-run the full 402/403/404 cycle immediately.
            if self._full_cycle_needed and self.is_connected:
                self._full_cycle_needed = False
                await self._run_status_cycle()
                fast_count = 0

            if not self.is_connected:
                # Disconnected — reconnect is handled by _on_bleak_disconnected /
                # _reconnect() / _on_bt_advertisement.  Just wait here.
                await asyncio.sleep(1)
                continue

            try:
                if fast_count >= self.STATUS_CYCLE_INTERVAL:
                    fast_count = 0
                    cmd = self._STATUS_CYCLE[cycle_index % len(self._STATUS_CYCLE)]
                    cycle_index += 1
                    await self.send_command(cmd, 0)
                else:
                    if fast_count % 1 == 0:
                        await self.send_command(CMD_HOOD_STATUS, 0)
                    fast_count += 1
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.warning("Poll error: %s", err)
            await asyncio.sleep(1)
