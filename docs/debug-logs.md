# Debug logs

When something goes wrong, a debug log shows what the unit and Home Assistant sent each other. Attach one to your [issue](https://github.com/Dr-Blank/fujitsu-lan-ha/issues) along with the diagnostics file from the device page.

## Turn on debug logging

Pick one of these. All of them log both the integration and the `aioayla_lan` library it uses.

### From the integration page (unit already added)

1. Go to **Settings > Devices & services > Fujitsu FGLair Local**.
2. Open the **⋮** menu and choose **Enable debug logging**.
3. Reproduce the problem: change the setting that misbehaves, or wait until the unit drops out.
4. Open the **⋮** menu again and choose **Disable debug logging**. Your browser downloads the log file.

### Without a restart (also works while adding a unit)

1. Go to **Developer tools > Actions** and switch to **YAML mode**.
2. Run this action:

   ```yaml
   action: logger.set_level
   data:
     custom_components.fglair_local: debug
     aioayla_lan: debug
   ```

3. Reproduce the problem.
4. Download the log as described in [Find the log](#find-the-log).

This setting is lost on restart.

### From `configuration.yaml` (kept across restarts)

Use this if the problem happens at startup or only every few hours. Add this to `configuration.yaml`, then restart Home Assistant:

```yaml
logger:
  default: warning
  logs:
    custom_components.fglair_local: debug
    aioayla_lan: debug
```

If you already have a `logger:` section, add the two lines under its `logs:` instead.

## Find the log

Go to **Settings > System > Logs**, open the **⋮** menu and choose **Download full log**. The log on that page is filtered and shortened, so send the downloaded file, not a copy of the page.

Note the time the problem happened, so the right part of the log can be found.

## Before you post

- The integration replaces the LAN key with `**REDACTED**` in its log output, so you do not need to remove it. Still look over the file before posting.
- The log contains your units' IP addresses and serial numbers (DSN). Replace them if you prefer; keep each one consistent, for example `192.168.1.x` → `IP_A`, so the log still makes sense.
- Do not post your FGLair password, your `configuration.yaml` secrets, or a LAN key from a script's output.
- Attach the file to the issue (drag it into the comment box) rather than pasting it.

## Turn it off again

Debug logging writes a lot. When you are done, choose **Disable debug logging**, or remove the lines from `configuration.yaml` and restart.
