"""End-to-end tests of the binary sensors, driven by a simulated unit."""

import pytest

from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
    BinarySensorDeviceClass,
)
from homeassistant.const import ATTR_DEVICE_CLASS, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import SimulatedUnit
from .const import DSN, PROBLEM_ENTITY_ID
from custom_components.fglair_local.const import DOMAIN

DEMAND_ENTITY_ID = "binary_sensor.air_conditioner_demand_response"


@pytest.mark.parametrize(
    ("prop", "entity_id", "device_class", "value", "expected"),
    [
        pytest.param(
            "error_code",
            PROBLEM_ENTITY_ID,
            BinarySensorDeviceClass.PROBLEM,
            1574,
            STATE_ON,
            id="error",
        ),
        pytest.param(
            "error_code",
            PROBLEM_ENTITY_ID,
            BinarySensorDeviceClass.PROBLEM,
            0,
            STATE_OFF,
            id="no_error",
        ),
        pytest.param(
            "demand_control",
            DEMAND_ENTITY_ID,
            None,
            3,
            STATE_ON,
            id="demand_response",
        ),
        pytest.param(
            "demand_control", DEMAND_ENTITY_ID, None, 0, STATE_OFF, id="no_demand"
        ),
    ],
)
async def test_binary_sensor(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    prop: str,
    entity_id: str,
    device_class: BinarySensorDeviceClass | None,
    value: int,
    expected: str,
) -> None:
    """Each binary sensor appears once reported and is on while its value is non-zero."""
    await unit.key_exchange()
    assert hass.states.get(entity_id) is None

    await unit.push(prop, value)

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == expected
    assert state.attributes.get(ATTR_DEVICE_CLASS) == device_class


@pytest.fixture
def stale_occupancy(entity_registry: er.EntityRegistry) -> None:
    """Register the occupancy sensor an earlier version created."""
    entity_registry.async_get_or_create(
        BINARY_SENSOR_DOMAIN,
        DOMAIN,
        f"{DSN}_human_det",
        suggested_object_id="air_conditioner_occupancy",
    )


@pytest.mark.usefixtures("stale_occupancy")
async def test_human_sensor_flag_not_occupancy(
    hass: HomeAssistant, unit: SimulatedUnit, entity_registry: er.EntityRegistry
) -> None:
    """`human_det` says the unit has a sensor, so the old occupancy sensor goes."""
    await unit.key_exchange()
    await unit.push("human_det", 1)

    assert (
        entity_registry.async_get_entity_id(
            BINARY_SENSOR_DOMAIN, DOMAIN, f"{DSN}_human_det"
        )
        is None
    )
    assert hass.states.get("binary_sensor.air_conditioner_occupancy") is None
