"""Home Assistant-specific constants for the Novy Pureline Pro integration.

Protocol constants (UUIDs, command IDs, packet sizes) live in the
``purelinepro_ble`` sub-package and are re-exported here for convenience.
"""

from .purelinepro_ble.const import (  # noqa: F401
    CMD_FAN_DEFAULT,
    CMD_FAN_RECIRCULATE,
    CMD_FAN_SPEED,
    CMD_FAN_STATE,
    CMD_LIGHT_BRIGHTNESS,
    CMD_LIGHT_COLORTEMP,
    CMD_LIGHT_DEFAULT,
    CMD_LIGHT_OFF,
    CMD_LIGHT_ON_AMBI,
    CMD_LIGHT_ON_WHITE,
    CMD_POWER,
    CMD_RESET_GREASE,
    COLOR_TEMP_KELVIN_COOL,
    COLOR_TEMP_KELVIN_WARM,
    COLOR_TEMP_MIREDS_COOL,
    COLOR_TEMP_MIREDS_WARM,
    UART_SERVICE_UUID,
)

DOMAIN = "novy_pureline_pro"

# HA color-temp range (Kelvin, required since HA 2026.1)
COLOR_TEMP_MIN_KELVIN = COLOR_TEMP_KELVIN_WARM   # 2700 K  (warmest)
COLOR_TEMP_MAX_KELVIN = COLOR_TEMP_KELVIN_COOL   # 6500 K  (coolest)

# Mired aliases kept for any internal conversion helpers
COLOR_TEMP_MIN_MIREDS = COLOR_TEMP_MIREDS_COOL
COLOR_TEMP_MAX_MIREDS = COLOR_TEMP_MIREDS_WARM

# Config entry keys
CONF_ADDRESS = "address"

# Platforms provided by this integration
PLATFORMS = ["fan", "light", "button", "switch", "sensor", "binary_sensor"]
