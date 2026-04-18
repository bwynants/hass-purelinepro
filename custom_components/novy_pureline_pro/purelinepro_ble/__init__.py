"""purelinepro_ble — BLE protocol library for the Novy Pureline Pro extractor hood.

Public API
----------
- :class:`PurelineProClient` — async BLE client (main entry point)
- :mod:`models` — typed packet dataclasses (Packet400/402/403/404)
- :mod:`const` — protocol constants (UUIDs, command IDs, packet sizes)
"""

from .client import PurelineProClient, StateCallback
from .const import (
    CMD_FAN_DEFAULT,
    CMD_FAN_RECIRCULATE,
    CMD_FAN_SPEED,
    CMD_FAN_STATE,
    CMD_HOOD_STATUS,
    CMD_HOOD_STATUS_402,
    CMD_HOOD_STATUS_403,
    CMD_HOOD_STATUS_404,
    CMD_LIGHT_BRIGHTNESS,
    CMD_LIGHT_COLORTEMP,
    CMD_LIGHT_DEFAULT,
    CMD_LIGHT_OFF,
    CMD_LIGHT_ON_AMBI,
    CMD_LIGHT_ON_WHITE,
    CMD_POWER,
    CMD_RESET_GREASE,
    COLOR_TEMP_MIREDS_COOL,
    COLOR_TEMP_MIREDS_WARM,
    UART_RX_CHAR_UUID,
    UART_SERVICE_UUID,
    UART_TX_CHAR_UUID,
)
from .models import (
    Packet400,
    Packet402,
    Packet403,
    Packet404,
    mireds_to_raw_colortemp,
    pct_to_raw_brightness,
    raw_brightness_to_pct,
    raw_colortemp_to_mireds,
)

__all__ = [
    "PurelineProClient",
    "StateCallback",
    "Packet400",
    "Packet402",
    "Packet403",
    "Packet404",
    "raw_brightness_to_pct",
    "pct_to_raw_brightness",
    "raw_colortemp_to_mireds",
    "mireds_to_raw_colortemp",
    "CMD_POWER",
    "CMD_LIGHT_ON_AMBI",
    "CMD_LIGHT_ON_WHITE",
    "CMD_LIGHT_BRIGHTNESS",
    "CMD_LIGHT_COLORTEMP",
    "CMD_RESET_GREASE",
    "CMD_FAN_RECIRCULATE",
    "CMD_FAN_SPEED",
    "CMD_FAN_STATE",
    "CMD_LIGHT_OFF",
    "CMD_FAN_DEFAULT",
    "CMD_LIGHT_DEFAULT",
    "CMD_HOOD_STATUS",
    "CMD_HOOD_STATUS_402",
    "CMD_HOOD_STATUS_403",
    "CMD_HOOD_STATUS_404",
    "COLOR_TEMP_MIREDS_COOL",
    "COLOR_TEMP_MIREDS_WARM",
    "UART_SERVICE_UUID",
    "UART_RX_CHAR_UUID",
    "UART_TX_CHAR_UUID",
]
