"""Packet dataclasses and struct-based parsing for Novy Pureline Pro BLE responses."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .const import (
    COLOR_TEMP_MIREDS_COOL,
    COLOR_TEMP_MIREDS_WARM,
    PACKET_400_SIZE,
    PACKET_402_SIZE,
    PACKET_403_SIZE,
    PACKET_404_SIZE,
)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def swap16(value: int) -> int:
    """Swap bytes of a 16-bit big-endian value stored in a little-endian field."""
    return ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)


def swap32(value: int) -> int:
    """Swap bytes of a 32-bit big-endian value stored in a little-endian field."""
    return struct.unpack("<I", struct.pack(">I", value))[0]


def raw_brightness_to_pct(raw: int) -> float:
    """Convert raw brightness byte (0-255) to fraction (0.0-1.0)."""
    return raw / 255.0


def pct_to_raw_brightness(pct: float) -> int:
    """Convert fraction (0.0-1.0) to raw brightness byte (0-255)."""
    return round(max(0.0, min(1.0, pct)) * 255)


def raw_colortemp_to_mireds(raw: int) -> int:
    """Map raw color-temp byte (0-255) to mireds (154-370).

    Raw 0   -> 154 mireds (6500 K, cool white)
    Raw 255 -> 370 mireds (2700 K, warm white)
    """
    return round(
        COLOR_TEMP_MIREDS_COOL
        + (raw / 255.0) * (COLOR_TEMP_MIREDS_WARM - COLOR_TEMP_MIREDS_COOL)
    )


def mireds_to_raw_colortemp(mireds: int) -> int:
    """Map mireds (154-370) to raw color-temp byte (0-255)."""
    clamped = max(COLOR_TEMP_MIREDS_COOL, min(COLOR_TEMP_MIREDS_WARM, mireds))
    return round(
        (clamped - COLOR_TEMP_MIREDS_COOL)
        / (COLOR_TEMP_MIREDS_WARM - COLOR_TEMP_MIREDS_COOL)
        * 255
    )


# ---------------------------------------------------------------------------
# Packet 400 (16 bytes) — main operating state, polled every second
# ---------------------------------------------------------------------------

@dataclass
class Packet400:
    """Main status packet (cmd 400), 16 bytes."""

    flags1: int = 0       # bit0 = fan motor energised; bit1 = boost/stopping timer active; bit2 = afterrun/stop-sequence active
    fanspeed: int = 0     # 0-100 %
    flags2: int = 0       # bit0 = grease filter needs cleaning
    unknown1: int = 0
    unknown2: int = 0
    lightmode: int = 0    # 0=off, 1=white preset, 2=ambi preset
    brightness: int = 0   # 0-255
    colortemp: int = 0    # 0-255 (raw)
    countdown: int = 0    # little-endian uint16 but logically big-endian
    unknown3: int = 0
    unknown4: int = 0
    unknown5: int = 0

    # Derived fields populated by __post_init__
    fan_state: bool = field(default=False, init=False)
    light_state: bool = field(default=False, init=False)
    boost: bool = field(default=False, init=False)
    stopping: bool = field(default=False, init=False)
    timer_seconds: int = field(default=0, init=False)
    grease_dirty: bool = field(default=False, init=False)
    brightness_pct: float = field(default=0.0, init=False)
    color_temp_mireds: int = field(default=COLOR_TEMP_MIREDS_COOL, init=False)

    def __post_init__(self) -> None:
        self.fan_state = self.fanspeed > 0
        self.light_state = self.brightness > 0
        timer_active = bool(self.flags1 & 0x02)
        self.boost = timer_active and self.fanspeed > 75
        self.stopping = timer_active and not self.boost
        self.timer_seconds = swap16(self.countdown) if timer_active else 0
        self.grease_dirty = bool(self.flags2 & 0x01)
        self.brightness_pct = raw_brightness_to_pct(self.brightness)
        self.color_temp_mireds = raw_colortemp_to_mireds(self.colortemp)

    @classmethod
    def from_bytes(cls, data: bytes) -> Packet400:
        if len(data) != PACKET_400_SIZE:
            raise ValueError(f"Packet400: expected {PACKET_400_SIZE} bytes, got {len(data)}")
        f = struct.unpack_from("<BBBBBBBBHHHH", data)
        return cls(
            flags1=f[0], fanspeed=f[1], flags2=f[2],
            unknown1=f[3], unknown2=f[4], lightmode=f[5],
            brightness=f[6], colortemp=f[7], countdown=f[8],
            unknown3=f[9], unknown4=f[10], unknown5=f[11],
        )


# ---------------------------------------------------------------------------
# Packet 402 (20 bytes) — recirculate mode, grease timer, firmware version
# ---------------------------------------------------------------------------

@dataclass
class Packet402:
    """Extended status packet (cmd 402), 20 bytes."""

    unknown1: int = 0
    flags: int = 0          # bit0 = recirculate mode active
    unknown2: int = 0
    greasetime: int = 0     # big-endian uint32, seconds
    major: int = 0
    minor: int = 0
    patch: int = 0
    unknown3: int = 0
    unknown4: int = 0
    unknown5: int = 0

    recirculate: bool = field(default=False, init=False)
    grease_minutes: int = field(default=0, init=False)
    firmware_version: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.recirculate = bool(self.flags & 0x01)
        self.grease_minutes = swap32(self.greasetime) // 60
        self.firmware_version = f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def from_bytes(cls, data: bytes) -> Packet402:
        if len(data) != PACKET_402_SIZE:
            raise ValueError(f"Packet402: expected {PACKET_402_SIZE} bytes, got {len(data)}")
        f = struct.unpack_from("<HBBIBBBBII", data)
        return cls(
            unknown1=f[0], flags=f[1], unknown2=f[2], greasetime=f[3],
            major=f[4], minor=f[5], patch=f[6], unknown3=f[7],
            unknown4=f[8], unknown5=f[9],
        )


# ---------------------------------------------------------------------------
# Packet 403 (21 bytes) — default speeds, operating hours (fan)
# ---------------------------------------------------------------------------

@dataclass
class Packet403:
    """Extended status packet (cmd 403), 21 bytes."""

    switch_off_fan_speed: int = 0
    unknown1: int = 0
    another_timer: int = 0       # big-endian uint32, seconds
    recirculate_timer: int = 0   # big-endian uint32, seconds
    fan_timer: int = 0           # big-endian uint32, seconds (total fan-on time)
    fan_speed: int = 0
    functional_brightness: int = 0
    functional_color: int = 0
    ambi_brightness: int = 0
    ambi_color: int = 0
    unknown2: int = 0

    fan_operating_minutes: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.fan_operating_minutes = swap32(self.fan_timer) // 60

    @classmethod
    def from_bytes(cls, data: bytes) -> Packet403:
        _STRUCT = "<BBIIIBBBBBB"  # 20 bytes: BB + 3×I + 6×B
        needed = struct.calcsize(_STRUCT)
        if len(data) < needed:
            raise ValueError(f"Packet403: need {needed} bytes, got {len(data)}")
        f = struct.unpack_from(_STRUCT, data)
        return cls(
            switch_off_fan_speed=f[0], unknown1=f[1],
            another_timer=f[2], recirculate_timer=f[3], fan_timer=f[4],
            fan_speed=f[5], functional_brightness=f[6], functional_color=f[7],
            ambi_brightness=f[8], ambi_color=f[9], unknown2=f[10],
        )


# ---------------------------------------------------------------------------
# Packet 404 (20 bytes) — operating hours (LED)
# NOTE: same size as Packet402 — caller must use in-flight command tag
# ---------------------------------------------------------------------------

@dataclass
class Packet404:
    """Extended status packet (cmd 404), 20 bytes."""

    unknown1: int = 0
    unknown2: int = 0
    unknown3: int = 0
    unknown4: int = 0
    ledtimer: int = 0    # big-endian uint32, seconds (total LED-on time)
    unknown5: int = 0
    unknown6: int = 0

    led_operating_minutes: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.led_operating_minutes = swap32(self.ledtimer) // 60

    @classmethod
    def from_bytes(cls, data: bytes) -> Packet404:
        # Layout (packed): 3×uint32, uint8, uint32, uint8, uint16 = 20 bytes
        _STRUCT = "<IIIBIBH"
        needed = struct.calcsize(_STRUCT)
        if len(data) < needed:
            raise ValueError(f"Packet404: need {needed} bytes, got {len(data)}")
        f = struct.unpack_from(_STRUCT, data)
        return cls(
            unknown1=f[0], unknown2=f[1], unknown3=f[2],
            unknown4=f[3], ledtimer=f[4], unknown5=f[5], unknown6=f[6],
        )
