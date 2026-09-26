# Fujitsu FGLair Local

Home Assistant integration that controls Fujitsu air conditioners with an FGLair Wi-Fi adapter directly over your network, using the adapter's Ayla LAN mode. No cloud is used after setup, and state changes are pushed by the unit rather than polled.

Tested on the AP-WF3E adapter. Other FGLair adapters use the same protocol and may work; please open an issue with your model either way.

## Requirements

- Home Assistant 2026.3.0 or newer.
- The air conditioner and Home Assistant on the same network. The unit opens its own connection back to Home Assistant, and it only connects to addresses on its own subnet.
- The unit's LAN key. Setup can fetch it from the FGLair cloud once, or you can paste one you saved earlier.
- A plain-HTTP port on Home Assistant that the unit can reach. The unit cannot speak HTTPS; see [Callback address](#callback-address).

## Installation

### HACS (recommended)

This is a custom repository, so HACS has to be told about it once. After that it updates like any other HACS integration.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Dr-Blank&repository=fujitsu-lan-ha&category=integration)

Click the badge above, then **Download**. It fills the repository in for you.

If the badge does not work, add it by hand:

1. **HACS > ⋮ (top right) > Custom repositories**.
2. Repository `https://github.com/Dr-Blank/fujitsu-lan-ha`, type **Integration**, then **Add**.
3. Search HACS for **Fujitsu FGLair Local** and **Download** it.

Either way, **restart Home Assistant** afterwards: custom integrations are only loaded at startup.

### Manual

Copy `custom_components/fglair_local` into your Home Assistant `config/custom_components/` directory and restart Home Assistant.

### Adding a unit

A unit on your network is usually discovered and appears under **Settings > Devices & services**. If it does not, add it with **Add integration > Fujitsu FGLair Local**.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=fglair_local)

### Updating

HACS shows an update when a new release is tagged. Download it and restart Home Assistant.

## Setup

Choose how Home Assistant gets the unit's LAN key:

- **Sign in to FGLair.** Enter the email, password and region of your FGLair app account. Home Assistant fetches each unit's LAN key and address once, then never contacts the cloud again. Your password is not stored.
- **I have the LAN key.** Enter the unit's IP address and a LAN key you saved earlier. Nothing leaves your network.

Home Assistant then registers with the unit and waits up to 30 seconds for it to connect back. The entry is created only after the unit has connected and the key has been checked.

Give the unit a fixed IP address in your router. If its address changes anyway, DHCP discovery updates the entry.

### Callback address

The unit connects back to Home Assistant at an address and port Home Assistant gives it. By default this is the address Home Assistant uses to reach the unit, on Home Assistant's own web server port.

If the default does not work, setup asks for the address and port:

- **Home Assistant in Docker (bridge network):** Home Assistant cannot see the host's LAN address, and the unit refuses the container's internal address. Enter the host machine's LAN address and the port published for Home Assistant. To have new units pick it up automatically, set **Local network** under **Settings > System > Network** to `http://<host address>:<port>`.
- **Home Assistant serving HTTPS:** The unit can only connect over plain HTTP. Put a plain-HTTP reverse proxy in front of Home Assistant on your LAN and enter its address and port.
- **Firewall:** The port must accept connections from the unit.

To change the callback address later, for example after moving Home Assistant to another machine, open the entry's menu and choose **Reconfigure**. The unit is checked at the new address before the change is saved.

## Entities

- **Climate:** on/off, HVAC mode, target temperature, fan speed (including quiet), and vertical and horizontal swing with fixed louvre positions.
- **Switches:** economy, powerful, outdoor unit low noise, energy saving fan and human sensor, for the features your unit reports. Other on/off settings the unit reports, such as the Wi-Fi LED, are configuration entities.
- **Occupancy:** the unit's human sensor.
- **Outdoor temperature:** created once the unit reports a reading.
- **Re-read all properties:** asks the unit for every value again.
- Raw sensors for other properties the unit reports, disabled by default.

## Known limitations

- **One local controller per unit.** Adding a unit disconnects any other local controller, such as the AirCon add-on.
- **Cloud integrations interfere.** Home Assistant's built-in Fujitsu FGLair integration asks the unit to refresh every 5 minutes. For about 2 minutes after each refresh the unit ignores local commands. Disable or remove the cloud integration for units added here.
- **IR remote louvre changes are not reported.** The unit reports mode and temperature changes made with the remote, but not louvre changes. The louvre state updates the next time it is read, for example with **Re-read all properties**.
- **Timers are not supported yet.**
- **LAN key changes.** If the unit is re-paired in the FGLair app and gets a new LAN key, remove the entry and add the unit again.

## Troubleshooting

Download diagnostics from the device page. They include the unit's last reported values and session state, with the LAN key, serial number and addresses redacted.

For more detail, enable debug logging for the integration from its entry, or add this to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.fglair_local: debug
    aioayla_lan: debug
```

The LAN key grants full local control of the unit. The integration replaces it with `**REDACTED**` in its own and the library's log output, including tracebacks, and in diagnostics. Still check anything you post, such as a `configuration.yaml` or a key-fetch script's output.

## License

Apache License 2.0. See [LICENSE](LICENSE).
