"""Base entity for Fujitsu FGLair Local."""

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import FglairLocalConfigEntry, FglairLocalDevice
from .properties import is_reported


class FglairLocalEntity(Entity):
    """Entity pushed by a `FglairLocalDevice`."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, device: FglairLocalDevice) -> None:
        """Initialise."""
        self.device = device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.dsn)},
            manufacturer="Fujitsu General",
            name=device.name,
            serial_number=device.dsn,
        )

    @property
    def available(self) -> bool:
        """Available while a LAN session is up."""
        return self.device.available

    async def async_added_to_hass(self) -> None:
        """Subscribe to pushed updates."""
        self.async_on_remove(self.device.async_add_listener(self._handle_device_update))

    @callback
    def _handle_device_update(self) -> None:
        """Write the state the unit pushed."""
        self.async_write_ha_state()


@callback
def async_add_when_reported(
    entry: FglairLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    candidates: Iterable[tuple[str, Callable[[], Entity]]],
    ready: Callable[[Any], bool] = is_reported,
) -> None:
    """Add each entity once the unit reports a value for its property that passes `ready`.

    The unit lists its whole model family's properties, most of them 65535.
    """
    device = entry.runtime_data
    waiting = list(candidates)

    @callback
    def add_reported() -> None:
        found = [c for c in waiting if ready(device.values.get(c[0]))]
        for candidate in found:
            waiting.remove(candidate)
        if found:
            async_add_entities(create() for _, create in found)

    add_reported()
    entry.async_on_unload(device.async_add_listener(add_reported))
