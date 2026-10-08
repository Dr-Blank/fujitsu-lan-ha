"""Sensors for Fujitsu FGLair Local."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FglairLocalConfigEntry, FglairLocalDevice
from .entity import FglairLocalEntity, async_add_when_reported
from .properties import (
    ERROR_CODE,
    OUTDOOR_TEMPERATURE,
    decode_error_code,
    decode_sensed_temperature,
    is_numeric,
    is_reported,
)

# Longest state Home Assistant stores.
MAX_STATE_LENGTH = 255


@dataclass(frozen=True, kw_only=True)
class FglairLocalSensorEntityDescription(SensorEntityDescription):
    """Sensor fed by one property."""

    decode: Callable[[Any], float | str | None]


SENSORS = (
    FglairLocalSensorEntityDescription(
        key=OUTDOOR_TEMPERATURE,
        translation_key=OUTDOOR_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        decode=decode_sensed_temperature,
    ),
    # Unknown while there is no error; the problem binary sensor says so.
    FglairLocalSensorEntityDescription(
        key=ERROR_CODE,
        translation_key=ERROR_CODE,
        entity_category=EntityCategory.DIAGNOSTIC,
        decode=decode_error_code,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FglairLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors, and a raw sensor for each property the unit reports."""
    device = entry.runtime_data
    async_add_when_reported(
        entry,
        async_add_entities,
        [
            (description.key, partial(FglairLocalSensor, device, description))
            for description in SENSORS
        ],
        ready=is_numeric,
    )
    added: set[str] = set()

    @callback
    def add_raw() -> None:
        new = [
            name
            for name, value in device.values.items()
            if name not in added and is_reported(value)
        ]
        added.update(new)
        if new:
            async_add_entities(FglairLocalRawSensor(device, name) for name in new)

    add_raw()
    entry.async_on_unload(device.async_add_listener(add_raw))


class FglairLocalSensor(FglairLocalEntity, SensorEntity):
    """Sensor fed by one pushed property."""

    entity_description: FglairLocalSensorEntityDescription

    def __init__(
        self,
        device: FglairLocalDevice,
        description: FglairLocalSensorEntityDescription,
    ) -> None:
        """Initialise."""
        super().__init__(device)
        self.entity_description = description
        self._attr_unique_id = f"{device.dsn}_{description.key}"

    @property
    def native_value(self) -> float | str | None:
        """Decoded value."""
        return self.entity_description.decode(
            self.device.values.get(self.entity_description.key)
        )


class FglairLocalRawSensor(FglairLocalEntity, SensorEntity):
    """Undecoded value of one property, named after it."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, device: FglairLocalDevice, prop: str) -> None:
        """Initialise."""
        super().__init__(device)
        self._prop = prop
        self._attr_name = f"raw {prop}"
        self._attr_unique_id = f"{device.dsn}_raw_{prop}"

    @property
    def native_value(self) -> str | None:
        """Value as the unit sent it."""
        if (value := self.device.values.get(self._prop)) is None:
            return None
        return str(value)[:MAX_STATE_LENGTH]
