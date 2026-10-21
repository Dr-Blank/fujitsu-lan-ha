# Fujitsu FGLair Local

Home Assistant integration that controls Fujitsu air conditioners with an FGLair Wi-Fi adapter directly over your network, using the adapter's Ayla LAN mode. No cloud is used after setup. The unit pushes most state changes; the few it rarely pushes, such as the room and outdoor temperature, are read every minute.

## Supported adapters

The integration reads which modes, fan speeds and louvres your unit has from the unit itself, so adapters that speak the same protocol should work without changes. The adapter families below come from the FGLair app's own adapter list; only two have been tried on a real unit.

| Adapter | How it was checked | Notes |
| --- | --- | --- |
| AP-WF3E | Tested on a unit | |
| UTY-TFSXW1 | Reported working ([#1](https://github.com/Dr-Blank/fujitsu-lan-ha/issues/1)) | |
| AP-WF1E, AP-WF2E, AP-WF4E | From the FGLair app, untested | Same adapter generation as the AP-WF3E. |
| AP-WA1E to AP-WA6E, AP-WC1E to AP-WC4E, AP-WD1E | From the FGLair app, untested | The app handles them like the AP-WF adapters. |
| AP-WB1E to AP-WB4E | From the FGLair app, untested | **Partly supported.** These adapters set the louvres and report defrost through other values, which the integration does not read yet: expect no louvre control, and the Defrost sensor and the HVAC action never showing a defrost. The unit's target temperature moves in whole degrees. |
| AP-WG | Listed in the FGLair app as a planned model, untested | |

Units with these adapters are discovered automatically: the integration looks for the network names the adapters give themselves (`AP-W…` or `AC-UTY-` followed by the MAC address). The names of the untested families are taken from the app and may differ in practice; if yours is not discovered, add it by hand.

If you try it with another adapter, please [open an issue](https://github.com/Dr-Blank/fujitsu-lan-ha/issues) saying whether it works. Include the adapter model (printed on the adapter, for example AP-WF3E or UTY-TFSXF3), your indoor unit model, the adapter's name in your router's device list, and the diagnostics file from the device page. Working reports help as much as broken ones. Support for the AP-WB louvres needs someone with such an adapter to test it.

Only Fujitsu units set up in the FGLair app are supported. Other brands' appliances that also use the Ayla platform use different property names and will not work.

## Requirements

- Home Assistant 2026.3.0 or newer.
- The air conditioner and Home Assistant on the same network. The unit opens its own connection back to Home Assistant, and it only connects to addresses on its own subnet.
- A fixed IP address for the unit. Reserve one for the adapter in your router; see [Give the unit a fixed IP address](docs/faq.md#give-the-unit-a-fixed-ip-address).
- The unit's LAN key. Setup can fetch it from the FGLair cloud once, or you can paste one you saved earlier.
- A plain-HTTP port on Home Assistant that the unit can reach. The unit cannot speak HTTPS; see [Callback address](#callback-address).

## Installation

### HACS (recommended)

[HACS](https://hacs.xyz) (Home Assistant Community Store) installs and updates custom integrations from inside Home Assistant. If **HACS** is not in your sidebar, set it up first by following the [HACS getting started guide](https://hacs.xyz/docs/use/).

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

Give the unit a fixed IP address in your router. If its address changes anyway, DHCP discovery updates the entry while the unit answers at its new address; otherwise enter the new address with **Reconfigure**.

### Reconfigure

Open the entry's **⋮** menu and choose **Reconfigure** to change, without removing the unit:

- **Address or LAN key:** the unit's IP address, its LAN key, or both. Leave the key empty to keep the current one.
- **Fetch the LAN key from FGLair:** sign in once to fetch a new key, for example after the unit was re-paired in the FGLair app.
- **How the unit reaches Home Assistant:** the callback address, see below.

The unit is checked with the new settings before they are saved.

### Options

The entry's **Configure** button has one setting, **Wait after the adapter restarts**, off by default, with its **Wait time** (600 seconds by default). Turn it on only if the unit gets stuck after its adapter restarts; see the [FAQ](docs/faq.md#the-unit-gets-stuck-after-its-adapter-restarts).

### Callback address

The unit connects back to Home Assistant at an address and port Home Assistant gives it. By default this is the address Home Assistant uses to reach the unit, on Home Assistant's own web server port.

If the default does not work, setup asks for the address and port:

- **Home Assistant in Docker (bridge network):** Home Assistant cannot see the host's LAN address, and the unit refuses the container's internal address. Enter the host machine's LAN address and the port published for Home Assistant. To have new units pick it up automatically, set **Local network** under **Settings > System > Network** to `http://<host address>:<port>`.
- **Home Assistant serving HTTPS:** The unit can only connect over plain HTTP. Put a plain-HTTP reverse proxy in front of Home Assistant on your LAN and enter its address and port.
- **Firewall:** The port must accept connections from the unit.

To change the callback address later, for example after moving Home Assistant to another machine, choose **Reconfigure > How the unit reaches Home Assistant**.

## Entities

- **Climate:** on/off, HVAC mode, target temperature, fan speed (including quiet) and room temperature. The room temperature is read every minute; to read it more often, see the [FAQ](docs/faq.md#how-often-is-the-room-temperature-updated). The target range follows the mode, as in the FGLair app: 16–30 °C in heat, 18–30 °C otherwise, or the range the unit reports.
  - **Vertical louvre** (swing mode): swing, stop, or hold at a fixed step: position 1 (the highest) to the number of steps the unit reports, up to 15. Units that report no count can only swing or stop.
  - **Horizontal louvre** (horizontal swing mode), on units that have one: swing, stop, or hold at a fixed step: position 1 (the leftmost) to the number of steps the unit reports, up to 15.
- **Switches:** economy, powerful, outdoor unit low noise, energy saving fan and human sensor, for the features your unit reports and supports (the FGLair app's rules: its capability flags, and human sensor only on units with one). Other on/off settings the unit reports, such as the Wi-Fi LED, are configuration entities.
  - **HVAC action:** "Defrosting" while the unit defrosts its outdoor coil, otherwise not set. The unit reports no other running state, so heating, cooling and idle are not shown.
- **Defrost:** on while the unit defrosts. Read every minute, so it can lag by up to a minute.
- **Demand response:** on while a utility demand-response event limits the unit. Read-only.
- **Operation restricted** (diagnostic): on while a central controller or building management system blocks some operation of the unit, such as changing the mode or target temperature. Commands it blocks are ignored by the unit.
- **Oil recovery, Mode conflict, Maintenance, Pump down, Test run** (diagnostic, disabled by default): special states the unit reports, mostly during installation or service. Mode conflict is on when the unit asks for a mode the shared outdoor unit is not running, for example heat while another indoor unit cools.
- **Outdoor temperature:** created once the unit reports a reading. Read every minute.
- **Problem** (diagnostic): on while the unit reports an error.
- **Error message** (diagnostic): what the error is, for example "Outdoor unit main board fault", or "No error". See [Error codes](docs/error-codes.md).
- **Error code** (diagnostic): the error as the FGLair app and the wired remote controller show it, for example `62.6`. Unknown while there is no error.
- **Re-read all properties:** asks the unit for every value again.
- Raw sensors for other properties the unit reports, disabled by default.

## Known limitations

- **One local controller per unit.** Adding a unit disconnects any other local controller, such as the AirCon add-on.
- **Cloud integrations interfere.** Home Assistant's built-in Fujitsu FGLair integration asks the unit to refresh every 5 minutes. For about 2 minutes after each refresh the unit ignores local commands. Disable or remove the cloud integration for units added here.
- **IR remote louvre changes are not reported.** The unit reports mode and temperature changes made with the remote, but not louvre changes. The louvre state updates the next time it is read, for example with **Re-read all properties**.
- **Timers are not supported yet.**
- **The Wi-Fi adapter may stop answering.** Seen once on an AP-WF3E: it stopped answering on the network until the unit was switched off at the breaker. A UTY-TFSXW1 user reported something similar while adding a unit. The cause is not known yet. See [The unit shows as unavailable](docs/faq.md#the-unit-shows-as-unavailable).
- **No heating / cooling / idle activity.** The unit reports only defrost, not whether the compressor is running; see the [FAQ](docs/faq.md#can-it-show-whether-the-unit-is-heating-cooling-or-defrosting).

## Troubleshooting

Start with the [FAQ](docs/faq.md). It covers a unit that shows as unavailable, a changed IP address or LAN key, and the "was not acknowledged" warnings.

Download diagnostics from the device page. They include the unit's last reported values and session state, with the LAN key, serial number and addresses redacted.

For more detail, turn on debug logging and attach the log to your issue. [Debug logs](docs/debug-logs.md) shows how to turn it on, where to find the log, and what to check before posting.

The LAN key grants full local control of the unit. The integration replaces it with `**REDACTED**` in its own and the library's log output, including tracebacks, and in diagnostics. Still check anything you post, such as a `configuration.yaml` or a key-fetch script's output.

## License

Apache License 2.0. See [LICENSE](LICENSE).
