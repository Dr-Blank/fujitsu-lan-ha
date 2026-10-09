"""On/off settings for Fujitsu FGLair Local, named after their raw property."""

from collections.abc import Mapping
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import FglairLocalConfigEntry, FglairLocalDevice
from .entity import FglairLocalEntity
from .properties import (
    DEMAND_CONTROL,
    DEVICE_CAPABILITIES,
    HUMAN_DET_AUTO_SAVE,
    HUMAN_DETECTED,
    TOGGLE_CAPABILITY,
    TOGGLE_PROPERTIES,
    Capability,
    is_numeric,
    raw_int,
)

# Settings the FGLair app shows, named as it does. The rest keep their raw name.
APP_SETTINGS = {
    "economy_mode": "economy",
    "powerful_mode": "powerful",
    "outdoor_low_noise": "outdoor_low_noise",
    "indoor_fan_control": "energy_saving_fan",
    "human_det_auto_save": "human_sensor",
    "wifi_led_enable": "wifi_led",
}
# Shown with the controls rather than as configuration.
PRIMARY = frozenset(
    {
        "economy_mode",
        "powerful_mode",
        "outdoor_low_noise",
        "indoor_fan_control",
        "human_det_auto_save",
    }
)


def _supported(values: Mapping[str, Any], prop: str) -> bool | None:
    """Whether the FGLair app offers the setting on this unit; None until known."""
    if prop == HUMAN_DET_AUTO_SAVE:
        if (sensor := raw_int(values.get(HUMAN_DETECTED))) is None:
            return None
        return sensor == 1
    if (bit := TOGGLE_CAPABILITY.get(prop)) is None:
        return True
    if (caps := raw_int(values.get(DEVICE_CAPABILITIES))) is None:
        return None
    return bit in Capability(caps)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FglairLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a switch for each setting the unit reports and supports."""
    device = entry.runtime_data
    registry = er.async_get(hass)

    # Read-only state, once wrongly offered as a switch.
    if entity_id := registry.async_get_entity_id(
        Platform.SWITCH, DOMAIN, f"{device.dsn}_{DEMAND_CONTROL}"
    ):
        registry.async_remove(entity_id)
    waiting = list(TOGGLE_PROPERTIES)

    @callback
    def add_supported() -> None:
        new = []
        for prop in list(waiting):
            supported = _supported(device.values, prop)
            # An earlier version's entity stays in the registry for the user to remove.
            if supported is False:
                waiting.remove(prop)
            elif supported and is_numeric(device.values.get(prop)):
                waiting.remove(prop)
                new.append(FglairLocalSwitch(device, prop))
        if new:
            async_add_entities(new)

    add_supported()
    entry.async_on_unload(device.async_add_listener(add_supported))


class FglairLocalSwitch(FglairLocalEntity, SwitchEntity):
    """On/off property, added once the unit reports it."""

    def __init__(self, device: FglairLocalDevice, prop: str) -> None:
        """Initialise."""
        super().__init__(device)
        self._prop = prop
        if prop not in PRIMARY:
            self._attr_entity_category = EntityCategory.CONFIG
        self._attr_unique_id = f"{device.dsn}_{prop}"
        if prop in APP_SETTINGS:
            self._attr_translation_key = APP_SETTINGS[prop]
        else:
            self._attr_name = prop

    @property
    def is_on(self) -> bool | None:
        """Whether the unit reports the setting on."""
        raw = raw_int(self.device.values.get(self._prop))
        return None if raw is None else raw != 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the setting on."""
        self._write(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the setting off."""
        self._write(0)

    def _write(self, value: int) -> None:
        # The unit seldom echoes writes; the coordinator reads the value back.
        self.device.set_property(self._prop, value)
