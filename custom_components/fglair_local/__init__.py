"""Fujitsu FGLair air conditioners over Ayla LAN mode."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import FglairLocalConfigEntry, FglairLocalDevice
from .views import async_get_server

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: FglairLocalConfigEntry) -> bool:
    """Set up a unit."""
    device = FglairLocalDevice(hass, entry, async_get_server(hass))
    entry.runtime_data = device
    entry.async_on_unload(device.detach)
    entry.async_on_unload(device.async_start())
    entry.async_create_background_task(
        hass, device.lan.run(), f"fglair_local register {device.dsn}"
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: FglairLocalConfigEntry
) -> bool:
    """Unload a unit."""
    # Before the platforms go, so a late datapoint cannot add an entity to one.
    entry.runtime_data.detach()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
