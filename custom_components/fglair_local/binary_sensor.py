"""Binary sensors for Fujitsu FGLair Local."""

from functools import partial

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FglairLocalConfigEntry, FglairLocalDevice
from .entity import FglairLocalEntity, async_add_when_reported
from .properties import HUMAN_DETECTED, is_numeric, raw_int


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FglairLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    device = entry.runtime_data
    async_add_when_reported(
        entry,
        async_add_entities,
        [(HUMAN_DETECTED, partial(FglairLocalOccupancy, device))],
        ready=is_numeric,
    )


class FglairLocalOccupancy(FglairLocalEntity, BinarySensorEntity):
    """The unit's presence sensor."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, device: FglairLocalDevice) -> None:
        """Initialise."""
        super().__init__(device)
        self._attr_unique_id = f"{device.dsn}_{HUMAN_DETECTED}"

    @property
    def is_on(self) -> bool | None:
        """Whether the unit senses someone."""
        raw = raw_int(self.device.values.get(HUMAN_DETECTED))
        return None if raw is None else raw != 0
