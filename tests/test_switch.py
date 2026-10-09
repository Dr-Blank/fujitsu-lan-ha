"""End-to-end tests of the on/off switches, driven by a simulated unit."""

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import SimulatedUnit, written
from .const import DSN, ECONOMY_ENTITY_ID
from custom_components.fglair_local.const import DOMAIN
from custom_components.fglair_local.properties import TOGGLE_PROPERTIES


@pytest.mark.parametrize(
    ("value", "expected"),
    [pytest.param(0, STATE_OFF, id="off"), pytest.param(1, STATE_ON, id="on")],
)
async def test_created_when_reported(
    hass: HomeAssistant, unit: SimulatedUnit, value: int, expected: str
) -> None:
    """A switch only appears once the unit reports its property."""
    await unit.key_exchange()
    assert hass.states.get(ECONOMY_ENTITY_ID) is None

    await unit.push("economy_mode", value)

    state = hass.states.get(ECONOMY_ENTITY_ID)
    assert state is not None
    assert state.state == expected


@pytest.mark.parametrize("platforms", [[Platform.SWITCH]])
async def test_switches(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    unit: SimulatedUnit,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """The settings the FGLair app shows are named as it does, the rest raw."""
    await unit.key_exchange()
    await unit.push_all(dict.fromkeys(TOGGLE_PROPERTIES, 0))

    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("entity_id", "name", "service", "value", "before", "after"),
    [
        pytest.param(
            ECONOMY_ENTITY_ID,
            "economy_mode",
            SERVICE_TURN_ON,
            1,
            STATE_OFF,
            STATE_ON,
            id="app_named_on",
        ),
        pytest.param(
            ECONOMY_ENTITY_ID,
            "economy_mode",
            SERVICE_TURN_OFF,
            0,
            STATE_ON,
            STATE_OFF,
            id="app_named_off",
        ),
        pytest.param(
            "switch.air_conditioner_min_heat",
            "min_heat",
            SERVICE_TURN_ON,
            1,
            STATE_OFF,
            STATE_ON,
            id="raw_named_on",
        ),
        pytest.param(
            "switch.air_conditioner_min_heat",
            "min_heat",
            SERVICE_TURN_OFF,
            0,
            STATE_ON,
            STATE_OFF,
            id="raw_named_off",
        ),
    ],
)
async def test_turn_writes_boolean(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    entity_id: str,
    name: str,
    service: str,
    value: int,
    before: str,
    after: str,
) -> None:
    """Switching writes a boolean and shows the new state until the unit says otherwise."""
    await unit.key_exchange()
    await unit.push(name, 1 - value)

    await hass.services.async_call(
        SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    assert written(await unit.fetch_write()) == (name, value, "boolean")
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == after

    # The unit refused the change, as its read-back shows.
    await unit.push(name, 1 - value)

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == before


@pytest.fixture
def stale_demand_control(entity_registry: er.EntityRegistry) -> None:
    """Register the demand control switch an earlier version created."""
    entity_registry.async_get_or_create(SWITCH_DOMAIN, DOMAIN, f"{DSN}_demand_control")


@pytest.mark.usefixtures("stale_demand_control", "init_integration")
async def test_demand_control_switch_removed(
    entity_registry: er.EntityRegistry,
) -> None:
    """Demand control is read-only, so an earlier switch for it goes on setup."""
    assert (
        entity_registry.async_get_entity_id(
            SWITCH_DOMAIN, DOMAIN, f"{DSN}_demand_control"
        )
        is None
    )
