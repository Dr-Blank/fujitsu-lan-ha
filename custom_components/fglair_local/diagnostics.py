"""Diagnostics for Fujitsu FGLair Local."""

import time
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_CALLBACK_HOST, CONF_DSN, CONF_LANIP_KEY
from .coordinator import FglairLocalConfigEntry

# The LAN key grants full local control of the unit.
TO_REDACT = {CONF_LANIP_KEY, CONF_DSN, CONF_HOST, CONF_CALLBACK_HOST}


def _age(since: float | None) -> float | None:
    return None if since is None else round(time.monotonic() - since, 1)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FglairLocalConfigEntry
) -> dict[str, Any]:
    """Return the entry's settings, session state and last known values."""
    device = entry.runtime_data
    return {
        "entry_data": async_redact_data(entry.data, TO_REDACT),
        "available": device.available,
        "connected": device.lan.connected,
        "seconds_since_seen": _age(device.lan.last_seen),
        "seconds_pending": _age(device.lan.pending_since),
        "values": device.values,
    }
