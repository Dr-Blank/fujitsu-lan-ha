"""Binary sensors for Fujitsu FGLair Local."""

from functools import partial

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FglairLocalConfigEntry, FglairLocalDevice
from .entity import FglairLocalEntity, async_add_when_reported
from .properties import ERROR_CODE, HUMAN_DETECTED, is_numeric, raw_int

# Each is on while its property is non-zero.
BINARY_SENSORS = (
    BinarySensorEntityDescription(
        key=HUMAN_DETECTED, device_class=BinarySensorDeviceClass.OCCUPANCY
    ),
    BinarySensorEntityDescription(
        key=ERROR_CODE,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


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
        [
            (description.key, partial(FglairLocalBinarySensor, device, description))
            for description in BINARY_SENSORS
        ],
        ready=is_numeric,
    )


class FglairLocalBinarySensor(FglairLocalEntity, BinarySensorEntity):
    """Binary sensor fed by one pushed property."""

    def __init__(
        self, device: FglairLocalDevice, description: BinarySensorEntityDescription
    ) -> None:
        """Initialise."""
        super().__init__(device)
        self.entity_description = description
        self._attr_unique_id = f"{device.dsn}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Whether the property is non-zero."""
        raw = raw_int(self.device.values.get(self.entity_description.key))
        return None if raw is None else raw != 0
