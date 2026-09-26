"""End-to-end tests of the occupancy sensor, driven by a simulated unit."""

import pytest

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import ATTR_DEVICE_CLASS, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from . import SimulatedUnit
from .const import OCCUPANCY_ENTITY_ID


@pytest.mark.parametrize(
    ("value", "expected"),
    [pytest.param(1, STATE_ON, id="occupied"), pytest.param(0, STATE_OFF, id="empty")],
)
async def test_occupancy(
    hass: HomeAssistant, unit: SimulatedUnit, value: int, expected: str
) -> None:
    """The presence sensor appears once reported and follows the unit."""
    await unit.key_exchange()
    assert hass.states.get(OCCUPANCY_ENTITY_ID) is None

    await unit.push("human_det", value)

    state = hass.states.get(OCCUPANCY_ENTITY_ID)
    assert state is not None
    assert state.state == expected
    assert state.attributes[ATTR_DEVICE_CLASS] == BinarySensorDeviceClass.OCCUPANCY
