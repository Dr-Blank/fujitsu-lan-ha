"""Actions for Fujitsu FGLair Local, named after their raw property."""

from functools import partial

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FglairLocalConfigEntry, FglairLocalDevice
from .entity import FglairLocalEntity, async_add_when_reported
from .properties import RESET_PROPERTIES, is_numeric


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FglairLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    device = entry.runtime_data
    async_add_entities([FglairLocalRefreshButton(device)])
    async_add_when_reported(
        entry,
        async_add_entities,
        [
            (prop, partial(FglairLocalResetButton, device, prop))
            for prop in RESET_PROPERTIES
        ],
        ready=is_numeric,
    )


class FglairLocalResetButton(FglairLocalEntity, ButtonEntity):
    """Write-only action property, pressed by writing 1."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, device: FglairLocalDevice, prop: str) -> None:
        """Initialise."""
        super().__init__(device)
        self._prop = prop
        self._attr_name = prop
        self._attr_unique_id = f"{device.dsn}_{prop}"

    async def async_press(self) -> None:
        """Trigger the action."""
        self.device.set_property(self._prop, 1, optimistic=False)


class FglairLocalRefreshButton(FglairLocalEntity, ButtonEntity):
    """Re-read every known property, e.g. after changing something in the app."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "refresh"

    def __init__(self, device: FglairLocalDevice) -> None:
        """Initialise."""
        super().__init__(device)
        self._attr_unique_id = f"{device.dsn}_refresh"

    async def async_press(self) -> None:
        """Queue reads of every known property."""
        self.device.request_all()
