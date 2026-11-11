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
<!-- ha-marketplace:exclude-start -->
[![Open your Home Assistant instance and show this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=bwynants&repository=hass-purelinepro&category=integration)

### Marketplace (Home Assistant 2026.11 or newer, recommended)

1. Click the badge above, or open **Settings → Marketplace → Add from link** (top right; the Marketplace needs a GitHub account connected for custom repositories).
2. Add `https://github.com/bwynants/hass-purelinepro` with type **Integration**.
3. Install **Novy Pureline Pro** and restart Home Assistant.

### HACS (Home Assistant 2026.10 or older)

1. In HACS, open the overflow menu → **Custom repositories**.
2. Add `https://github.com/bwynants/hass-purelinepro` with type **Integration**.
3. Install **Novy Pureline Pro** and restart Home Assistant.

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
           ├── services.py
           ├── services.yaml
           └── purelinepro_ble/
               ├── __init__.py
               ├── client.py
               ├── models.py
               └── const.py
   ```
2. Restart Home Assistant.
<!-- ha-marketplace:exclude-end -->

### Configuration

**Automatic discovery (recommended):**
If the hood is advertising and HA's Bluetooth integration can see it, a discovery notification will appear in **Settings → Devices & Services**. Click **Configure** and confirm.

**Manual setup:**
1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Novy Pureline Pro**.
3. If the hood is visible in HA's BT cache, select it from the picker. Otherwise, select **"Enter MAC address manually…"** and type the hood's Bluetooth MAC address (`AA:BB:CC:DD:EE:FF`).

The config entry is keyed by BT address; duplicate entries for the same address are rejected.

if you have a novy extractor hood but it returns another name (not pureline pro) the Bluetooth MAC address can be obtaind from the log by enableing debug logging. Add the address manually. If really compatible please report the name to me so i can add it for auto discovery...
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
- `delayed_off`: lowers the fan to the stored switch-off speed (25% by default, see `set_default_speed`) and starts a countdown that switches the fan off when it expires: 5 minutes normally, 30 minutes in recirculate mode. The remaining time is shown by the `off_timer` sensor. The countdown is cancelled, leaving the fan running, when:
  - the fan speed is raised above the switch-off speed, from the hood's buttons, the Novy app or Home Assistant;
  - the fan is switched off by other means;
  - the hood's own stop timer becomes active.

  Switching the light to the ambi preset at the same time (what the hood's own firmware does) is optional: enable **Switch light to ambi on Delayed Off** under the integration's **Configure** options. It is off by default so that Home Assistant stays in control of the light.
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

## Services

### `novy_pureline_pro.send_command`

Sends a raw command frame (`[command;arg1;arg2;...]`) to the hood. Intended for commands that have no entity yet and for protocol exploration. Available from version 1.2.0.

> ⚠️ The frame is sent as-is, without any check on what it does. Only send commands you understand.

| Field | Required | Description |
| --- | --- | --- |
| `command` | yes | Command ID (0–999), for example `10` (power), `28` (fan speed), `400` (status). |
| `args` | no | List of integer arguments, for example `[1, 75]`. Defaults to none. |
| `config_entry_id` | no | The hood to send to. Can be left out when only one hood is configured; required when several are loaded. |
| `refresh` | no | Request a status report afterwards so the entities update. Defaults to `true`; skipped when the command itself is the status request (`400`). |

Example, sending the frame `[28;1;75]`:

```yaml
action: novy_pureline_pro.send_command
data:
  command: 28
  args: [1, 75]
```

The service optionally returns a response (use `response_variable` in a script or automation, or tick **Return response** in **Developer tools → Actions**):

| Key | Description |
| --- | --- |
| `frame` | The frame that was sent, for example `[28;1;75]`. |
| `reply` | The hood's reply to the command, see below. |
| `refreshed` | Whether a status report was requested afterwards. |
| `state` | The integration's state for the hood after the call. |

`reply` describes the first notification the hood sends back, and has one of three forms:

| `type` | Other keys | Meaning |
| --- | --- | --- |
| `ack` | `raw`: the ACK content, for example `1;1;1` | The hood acknowledged the command with an ASCII frame. |
| `status` | `raw`: the packet in hex, `state`: the decoded values | The hood answered with a status packet the integration can parse (for example after command `400`). |
| `unknown` | `raw`: the packet in hex | The hood answered with a packet the integration does not recognise. Useful when exploring the protocol. |

Example response:

```yaml
frame: "[28;1;75]"
reply:
  type: ack
  raw: "1;1;1"
refreshed: true
state:
  ...
```

The call fails with an error when the hood cannot be found, is not loaded or not connected, or when the hood does not reply within the request timeout.

---


## 📎 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## 🙏 Credits

Thanks to the open-source community for tools and documentation that made this reverse engineering effort possible.
