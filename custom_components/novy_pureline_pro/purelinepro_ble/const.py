"""Protocol constants for Novy Pureline Pro BLE communication."""

# Nordic UART Service (NUS)
UART_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
UART_RX_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write (client -> hood)
UART_TX_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify (hood -> client)

# Command IDs
CMD_POWER = 10
CMD_LIGHT_ON_AMBI = 15
CMD_LIGHT_ON_WHITE = 16
CMD_LIGHT_BRIGHTNESS = 21
CMD_LIGHT_COLORTEMP = 22
CMD_RESET_GREASE = 23
CMD_FAN_RECIRCULATE = 25
CMD_FAN_SPEED = 28
CMD_FAN_STATE = 29
CMD_LIGHT_OFF = 36
CMD_FAN_DEFAULT = 41
CMD_LIGHT_DEFAULT = 42
CMD_HOOD_STATUS = 400
CMD_HOOD_STATUS_402 = 402
CMD_HOOD_STATUS_403 = 403
CMD_HOOD_STATUS_404 = 404

# status commands (responses need in-flight tag to disambiguate)
HOOD_STATUS_CMDS = (CMD_HOOD_STATUS, CMD_HOOD_STATUS_402, CMD_HOOD_STATUS_403, CMD_HOOD_STATUS_404)

# Packet sizes in bytes
# Packet402/403/404 may all be 20 bytes — _pending_extended_cmd tag disambiguates
PACKET_400_SIZE = 16
PACKET_402_SIZE = 20
PACKET_403_SIZE = 20  # struct format is also 20 bytes (BBIIIBBBBB B = 20)
PACKET_404_SIZE = 20

# Light color temperature range
COLOR_TEMP_RAW_MIN = 0
COLOR_TEMP_RAW_MAX = 255
COLOR_TEMP_MIREDS_COOL = 154   # 6500 K (raw = 0)
COLOR_TEMP_MIREDS_WARM = 370   # 2700 K (raw = 255)
COLOR_TEMP_KELVIN_COOL = 6500  # raw = 0   (coolest / white)
COLOR_TEMP_KELVIN_WARM = 2700  # raw = 255 (warmest / amber)

# Connection settings
REQUEST_TIMEOUT_S = 8   # skip non-responding extended status quickly
RECONNECT_DELAY_S = 5
