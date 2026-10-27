"""Unit tests for the purelinepro_ble packet parsers and conversion helpers.

These cover the pure protocol layer only — no Home Assistant or BLE stack is
required — so they run under a plain ``pytest`` invocation from the repo root.
"""

from __future__ import annotations

import struct

import pytest

from purelinepro_ble.models import (
    Packet400,
    Packet402,
    Packet403,
    Packet404,
    mireds_to_raw_colortemp,
    pct_to_raw_brightness,
    raw_brightness_to_pct,
    raw_colortemp_to_mireds,
    swap16,
    swap32,
)


# --- byte-order helpers -------------------------------------------------

def test_swap16_reverses_bytes():
    assert swap16(0x0102) == 0x0201
    # swap16 is its own inverse
    assert swap16(swap16(300)) == 300


def test_swap32_reverses_bytes():
    assert swap32(0x01020304) == 0x04030201
    assert swap32(swap32(3600)) == 3600


# --- brightness / colour-temp conversions -------------------------------

def test_brightness_round_trip():
    assert raw_brightness_to_pct(0) == 0.0
    assert raw_brightness_to_pct(255) == 1.0
    assert pct_to_raw_brightness(0.0) == 0
    assert pct_to_raw_brightness(1.0) == 255


@pytest.mark.parametrize("pct", [-1.0, 2.0])
def test_pct_to_raw_brightness_clamps(pct):
    assert 0 <= pct_to_raw_brightness(pct) <= 255


def test_colortemp_endpoints():
    assert raw_colortemp_to_mireds(0) == 154    # coolest (6500 K)
    assert raw_colortemp_to_mireds(255) == 370  # warmest (2700 K)
    assert mireds_to_raw_colortemp(154) == 0
    assert mireds_to_raw_colortemp(370) == 255


def test_mireds_to_raw_clamps_out_of_range():
    assert mireds_to_raw_colortemp(100) == 0    # below the cool end
    assert mireds_to_raw_colortemp(500) == 255  # above the warm end


# --- Packet400: main operating state ------------------------------------

def _pack400(flags1=0, fanspeed=0, flags2=0, lightmode=0, brightness=0,
             colortemp=0, countdown=0):
    return struct.pack(
        "<BBBBBBBBHHHH",
        flags1, fanspeed, flags2, 0, 0, lightmode, brightness, colortemp,
        countdown, 0, 0, 0,
    )


def test_packet400_running_with_stop_timer():
    pkt = Packet400.from_bytes(
        _pack400(flags1=0x02, fanspeed=50, flags2=0x01, lightmode=1,
                 brightness=128, colortemp=0, countdown=swap16(300))
    )
    assert pkt.fan_state is True
    assert pkt.fanspeed == 50
    assert pkt.light_state is True
    assert pkt.lightmode == 1
    assert pkt.brightness == 128
    assert pkt.brightness_pct == pytest.approx(128 / 255)
    assert pkt.color_temp_mireds == 154
    assert pkt.grease_dirty is True
    assert pkt.boost is False       # speed <= 75
    assert pkt.stopping is True     # timer active, not boosting
    assert pkt.timer_seconds == 300


def test_packet400_boost():
    pkt = Packet400.from_bytes(
        _pack400(flags1=0x02, fanspeed=90, countdown=swap16(120))
    )
    assert pkt.boost is True        # timer active and speed > 75
    assert pkt.stopping is False
    assert pkt.timer_seconds == 120


def test_packet400_idle():
    pkt = Packet400.from_bytes(_pack400())
    assert pkt.fan_state is False
    assert pkt.light_state is False
    assert pkt.boost is False
    assert pkt.stopping is False
    assert pkt.timer_seconds == 0
    assert pkt.grease_dirty is False


def test_packet400_wrong_length_raises():
    with pytest.raises(ValueError):
        Packet400.from_bytes(b"\x00" * 15)


# --- Packet402: recirculate / grease / firmware -------------------------

def test_packet402():
    data = struct.pack("<HBBIBBBBII", 0, 1, 0, swap32(3600), 1, 2, 3, 0, 0, 0)
    pkt = Packet402.from_bytes(data)
    assert pkt.recirculate is True
    assert pkt.grease_minutes == 60      # 3600 s / 60
    assert pkt.firmware_version == "1.2.3"


def test_packet402_wrong_length_raises():
    with pytest.raises(ValueError):
        Packet402.from_bytes(b"\x00" * 19)


# --- Packet403: fan operating hours -------------------------------------

def test_packet403():
    data = struct.pack("<BBIIIBBBBBB", 25, 0, 0, 0, swap32(7200), 0, 0, 0, 0, 0, 0)
    pkt = Packet403.from_bytes(data)
    assert pkt.switch_off_fan_speed == 25
    assert pkt.fan_operating_minutes == 120   # 7200 s / 60


# --- Packet404: LED operating hours -------------------------------------

def test_packet404():
    data = struct.pack("<IIIBIBH", 0, 0, 0, 0, swap32(36000), 0, 0)
    pkt = Packet404.from_bytes(data)
    assert pkt.led_operating_minutes == 600   # 36000 s / 60
