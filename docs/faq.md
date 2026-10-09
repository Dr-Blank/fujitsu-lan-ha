# FAQ

Answers to the questions that come up most. If yours is not here, [open an issue](https://github.com/Dr-Blank/fujitsu-lan-ha/issues) with a [debug log](debug-logs.md) and the diagnostics file from the device page.

## The unit shows as unavailable

The Wi-Fi adapter can stop answering on the network while the air conditioner itself keeps running. This has been seen once on an AP-WF3E, where it lasted over half an hour until the unit was power-cycled, and a UTY-TFSXW1 user reported a unit that would not connect while being added until it was power-cycled. The cause is not known yet. If it happens to you, please [open an issue](https://github.com/Dr-Blank/fujitsu-lan-ha/issues) with the time and your adapter model.

Fujitsu's procedure, from the FGLair app:

1. Turn the air conditioner off with the remote.
2. Switch it off at the breaker or mains and wait at least 5 minutes. The remote alone is not enough: the adapter stays powered.
3. Switch it back on and wait up to 15 minutes for the adapter to rejoin Wi-Fi. Home Assistant reconnects by itself.
4. If it does not come back, repeat these steps.

If the unit still does not come back, check that its IP address has not changed (see [Give the unit a fixed IP address](#give-the-unit-a-fixed-ip-address)).

How you notice it:

- The entities show as unavailable.
- After 30 seconds the log shows a warning: `<serial>: not responding at <address>`. When the unit is back, an info line says how long it was gone.
- For adapters this has been seen on (AP-WF3E so far), a repair appears under **Settings > System > Repairs** after 10 minutes, with these steps.

With debug logging on, a hung adapter shows `registration failed: TimeoutError()` (or `registration failed:` followed by nothing, on 0.2.0 and older) every 10 seconds.

## Give the unit a fixed IP address

Home Assistant reaches the unit at the IP address saved when it was added. Reserve that address for the adapter in your router (often called a DHCP reservation or static lease), so it keeps the same one after a power cut or router restart. The adapter usually shows up in the router's device list with a hostname of `AP-WF…` (AP-WF3E and similar) or `AC-UTY-` followed by its MAC address (UTY adapters), unless it was renamed there.

If the address changes anyway:

- While the adapter answers at its new address, DHCP discovery updates the entry by itself.
- Otherwise, open the entry's **⋮** menu, choose **Reconfigure > Address or LAN key** and enter the new address. There is no need to remove and re-add the unit.

## The unit got a new LAN key

Re-pairing the unit in the FGLair app gives it a new LAN key, and Home Assistant can no longer connect with the old one. Open the entry's **⋮** menu and choose **Reconfigure**, then either:

- **Fetch the LAN key from FGLair**: sign in once and the new key is fetched for you.
- **Address or LAN key**: paste the new key yourself.

The unit is checked with the new key before it is saved. Entities, automations and history are kept.

## Home Assistant moved to another address or port

The unit connects back to Home Assistant at the address saved during setup. Open the entry's **⋮** menu and choose **Reconfigure > How the unit reaches Home Assistant**. See [Callback address](../README.md#callback-address) for Docker and HTTPS setups.

## The log says a setting "was not acknowledged"

Up to 0.2.0, every change could log `could not set <setting> to <value>: <setting> was not acknowledged`, although the unit had applied it. Not every adapter confirms every change: a UTY-TFSXW1 confirmed none in the logs so far, and an AP-WF3E missed confirmations just after a restart. Since 0.2.1 a missing confirmation is not treated as a failure: the setting stays as you set it, and the integration reads it back from the unit about 12 seconds later to be sure. A warning is only logged when the unit refuses a change or does not pick it up at all.

## The state jumps back for a second after a change

On 0.2.0 and older, a change the unit did not confirm was undone until the read-back showed the new value, so the mode could flick back for a second or two. Update to 0.2.1 or newer.

## Why is the lowest fan speed "quiet" and the louvre positions "position 1" to "position N"?

The integration uses Fujitsu's own names: the remote's fan button cycles AUTO, HIGH, MED, LOW and QUIET, and the unit reports that speed as quiet. Louvre positions are numbered from 1 to the number of steps your unit reports: vertical from the top, horizontal from the left. Up to 0.2.3 the horizontal positions were named `left`, `left_center`, `center`, `right_center` and `right`; from 0.2.4 they are `position_1` to `position_5`, so update automations and scenes that use the old names. Other integrations use other names (`diffuse`, `Vertical_1`, `off`); automations moved from them need the names here: `quiet` and `position_1` to `position_N`.

## Can it show whether the unit is heating, cooling or defrosting?

Not yet. The unit does not push such a value when it changes, so the integration now reads the two candidates, `op_status` and `monitor1`, every minute. On an AP-WF3E, `op_status` stayed 0 both while the compressor ran and after it stopped, while one field of `monitor1` went from 1 to 0. That is a single sample, so it is not used yet.

To help, take diagnostics twice in the same mode: once while the compressor runs (cold or hot air comes out) and once after it stops (raise the target above the room temperature when cooling, or lower it when heating). The two values are read once a minute, so wait a minute after the air changes before each download. Attach both files to an issue and say what the unit was doing.

## Can I use another integration at the same time?

Another local controller, such as the AirCon add-on, is disconnected when this integration connects, as only one local controller is allowed at a time. A cloud integration that refreshes the unit, such as Home Assistant's built-in Fujitsu FGLair integration, makes the unit ignore local commands for about 2 minutes after each refresh, so disable it for units added here. See [Known limitations](../README.md#known-limitations).
