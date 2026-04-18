# Novy Pureline Pro — Home Assistant Custom Integration

A native Home Assistant integration for the **Novy Pureline Pro** extractor hood, communicating over Bluetooth Low Energy (BLE) using the Nordic UART Service (NUS) protocol. It provides full local control with no cloud dependency (`iot_class: local_push`).

This integration is based on reverse-engineering the communication between the official mobile app and the extractor hood.

---

## 🐛 Compatibility

Tested with Novy Pureline Pro and Novy Cloud extractor

## Installation & Setup

### Prerequisites

- Home Assistant 2023.8 or newer
- A Bluetooth adapter (USB dongle or integrated) accessible to the HA host, **or** an [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html) within range of the hood
- Novy Pureline Pro extractor hood, powered on

No additional Python packages are required (`requirements: []` in `manifest.json`). `bleak` and `bleak_retry_connector` are bundled with HA.
### Manual installation

1. **HACS**: Add this repository (`eigger/hass-purelinepro`) to HACS as a custom repository

### Manual installation

1. Copy the `custom_components/novy_pureline_pro/` folder into your HA `config/custom_components/` directory:
   ```
   config/
   └── custom_components/
       └── novy_pureline_pro/
           ├── __init__.py
           ├── manifest.json
           ├── config_flow.py
           ├── coordinator.py
           ├── const.py
           ├── light.py
           ├── fan.py
           ├── switch.py
           ├── button.py
           ├── sensor.py
           ├── binary_sensor.py
           └── purelinepro_ble/
               ├── __init__.py
               ├── client.py
               ├── models.py
               └── const.py
   ```
2. Restart Home Assistant.

### Configuration

**Automatic discovery (recommended):**
If the hood is advertising and HA's Bluetooth integration can see it, a discovery notification will appear in **Settings → Devices & Services**. Click **Configure** and confirm.

**Manual setup:**
1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Novy Pureline Pro**.
3. If the hood is visible in HA's BT cache, select it from the picker. Otherwise, select **"Enter MAC address manually…"** and type the hood's Bluetooth MAC address (`AA:BB:CC:DD:EE:FF`).

The config entry is keyed by BT address; duplicate entries for the same address are rejected.

---

## Enabling Debug Logging

Add the following to your `configuration.yaml` and restart Home Assistant:

```yaml
logger:
  logs:
    custom_components.novy_pureline_pro: debug
```

Debug output includes:
- BLE advertisement events and connection state changes
- All TX command frames (e.g., `TX: [28;1;75]`)
- ACK receipts (e.g., `ACK: [1;1;1]`)
- Raw packet payloads in hex (e.g., `Packet len 16 payload: 020a00...`)
- Poll loop events and STATUS_CYCLE milestones
- Reconnect attempts and failures

---

## The controls

### Switches

- `Recirculate`: Toggles between normal and recirculate mode.

---

### Fan

The fan allows for setting on/off and speed 

---

### Light

The light (combines white/ambient), supports color and brightness control.

---

### Buttons

Useful remote-like actions:
  
- `power`: simulates power of remote
- `delayed_off`: if clicked it sets the fan to 25% and puts it off after 5 minutes
- `set_default_light`: sets default light for ambi or white, if ambi or white mode is not active it does nothing....
- `ambi_light`: start ambi light mode
- `white_light`: start white light mode
- `set_default_speed`: sets default speed
- `reset_grease`: resets grease filter timer

---

### Sensors

Monitor extractor hood status and usage:

- `off_timer`: when in cooldown mode, this gives how long remaining before off
- `boost_timer`: when in boost mode (fan +75%) this is the remaing time before the fan speed gets lowered
- `grease_timer`: remainig time before grease filter needs cleaning
- `operating_hours_led`: total hours the leds where on
- `operating_hours_fan`: total hours the fan was on

---

### Binary Sensors

- `cleangrease`: Indicates when the grease filter needs cleaning.

---


## 📎 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## 🙏 Credits

Thanks to the open-source community for tools and documentation that made this reverse engineering effort possible.
