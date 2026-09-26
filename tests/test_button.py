"""End-to-end tests of the buttons, driven by a simulated unit."""

import pytest

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant

from . import SimulatedUnit, read_resource, written
from .const import REFRESH_ENTITY_ID
from custom_components.fglair_local.properties import (
    EXTRA_PROPERTIES,
    PRIME_PROPERTIES,
    RESET_PROPERTIES,
)

PRIMED = (*PRIME_PROPERTIES, *EXTRA_PROPERTIES)


@pytest.mark.parametrize(
    "name", [pytest.param(name, id=name) for name in RESET_PROPERTIES]
)
async def test_reset_press_queues_write(
    hass: HomeAssistant, unit: SimulatedUnit, name: str
) -> None:
    """A reset button appears once reported, and pressing it writes 1."""
    entity_id = f"button.air_conditioner_{name}"
    await unit.key_exchange()
    assert hass.states.get(entity_id) is None
    await unit.push(name, 0)

    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    assert written(await unit.fetch_write()) == (name, 1, "integer")


async def test_refresh_press_queues_reads(
    hass: HomeAssistant, unit: SimulatedUnit
) -> None:
    """Re-reading asks the unit for every known property again."""
    await unit.key_exchange()
    for _ in PRIMED:
        await unit.fetch_command()
    assert (await unit.fetch_command())["data"] == {}

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: REFRESH_ENTITY_ID},
        blocking=True,
    )

    assert [read_resource(await unit.fetch_command()) for _ in PRIMED] == [
        f"property.json?name={name}" for name in PRIMED
    ]
    assert (await unit.fetch_command())["data"] == {}
