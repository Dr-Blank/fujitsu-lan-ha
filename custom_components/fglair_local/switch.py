"""On/off settings for Fujitsu FGLair Local, named after their raw property."""

from functools import partial
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import FglairLocalConfigEntry, FglairLocalDevice
from .entity import FglairLocalEntity, async_add_when_reported
from .properties import DEMAND_CONTROL, TOGGLE_PROPERTIES, is_numeric, raw_int

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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FglairLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    device = entry.runtime_data
    registry = er.async_get(hass)
    # Read-only state, once wrongly offered as a switch.
    if entity_id := registry.async_get_entity_id(
        Platform.SWITCH, DOMAIN, f"{device.dsn}_{DEMAND_CONTROL}"
    ):
        registry.async_remove(entity_id)
    async_add_when_reported(
        entry,
        async_add_entities,
        [
            (prop, partial(FglairLocalSwitch, device, prop))
            for prop in TOGGLE_PROPERTIES
        ],
        ready=is_numeric,
    )


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
