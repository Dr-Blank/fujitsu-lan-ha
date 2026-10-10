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
DEFROST_ENTITY_ID = "binary_sensor.air_conditioner_defrost"


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
        pytest.param(
            "demand_control",
            DEMAND_ENTITY_ID,
            None,
            4,
            STATE_OFF,
            id="demand_out_of_range",
        ),
        pytest.param(
            "op_status",
            DEFROST_ENTITY_ID,
            BinarySensorDeviceClass.RUNNING,
            1 << 24,
            STATE_ON,
            id="defrost",
        ),
        pytest.param(
            "op_status",
            DEFROST_ENTITY_ID,
            BinarySensorDeviceClass.RUNNING,
            1 << 28,
            STATE_OFF,
            id="no_defrost",
        ),
        pytest.param(
            "op_status",
            "binary_sensor.air_conditioner_operation_restricted",
            None,
            1 << 3,
            STATE_ON,
            id="mode_locked",
        ),
        pytest.param(
            "op_status",
            "binary_sensor.air_conditioner_operation_restricted",
            None,
            1 << 24,
            STATE_OFF,
            id="not_restricted",
        ),
        pytest.param(
            "op_status",
            "binary_sensor.air_conditioner_oil_recovery",
            None,
            1 << 28,
            STATE_ON,
            id="oil_recovery",
        ),
        pytest.param(
            "op_status",
            "binary_sensor.air_conditioner_mode_conflict",
            None,
            1 << 25,
            STATE_ON,
            id="mode_conflict",
        ),
        pytest.param(
            "op_status",
            "binary_sensor.air_conditioner_maintenance",
            None,
            1 << 22,
            STATE_ON,
            id="maintenance",
        ),
        pytest.param(
            "op_status",
            "binary_sensor.air_conditioner_pump_down",
            None,
            1 << 29,
            STATE_ON,
            id="pump_down",
        ),
        pytest.param(
            "op_status",
            "binary_sensor.air_conditioner_test_run",
            None,
            1 << 30,
            STATE_ON,
            id="test_run",
        ),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_binary_sensor(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    prop: str,
    entity_id: str,
    device_class: BinarySensorDeviceClass | None,
    value: int,
    expected: str,
) -> None:
    """Each binary sensor appears once its property is reported, on per its value."""
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


async def test_service_states_disabled_by_default(
    hass: HomeAssistant, unit: SimulatedUnit, entity_registry: er.EntityRegistry
) -> None:
    """Installer and service states are rare, so only defrost and restrictions show."""
    await unit.key_exchange()
    await unit.push("op_status", 0)

    assert hass.states.get(DEFROST_ENTITY_ID) is not None
    assert hass.states.get("binary_sensor.air_conditioner_operation_restricted")
    entry = entity_registry.async_get("binary_sensor.air_conditioner_pump_down")
    assert entry is not None
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


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
