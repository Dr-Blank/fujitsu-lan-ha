"""End-to-end tests of the binary sensors, driven by a simulated unit."""

import pytest

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import ATTR_DEVICE_CLASS, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from . import SimulatedUnit
from .const import OCCUPANCY_ENTITY_ID, PROBLEM_ENTITY_ID


@pytest.mark.parametrize(
    ("prop", "entity_id", "device_class", "value", "expected"),
    [
        pytest.param(
            "human_det",
            OCCUPANCY_ENTITY_ID,
            BinarySensorDeviceClass.OCCUPANCY,
            1,
            STATE_ON,
            id="occupied",
        ),
        pytest.param(
            "human_det",
            OCCUPANCY_ENTITY_ID,
            BinarySensorDeviceClass.OCCUPANCY,
            0,
            STATE_OFF,
            id="empty",
        ),
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
    ],
)
async def test_binary_sensor(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    prop: str,
    entity_id: str,
    device_class: BinarySensorDeviceClass,
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
    assert state.attributes[ATTR_DEVICE_CLASS] == device_class
