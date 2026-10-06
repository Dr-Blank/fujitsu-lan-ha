"""End-to-end tests of the sensors, driven by a simulated unit."""

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import SimulatedUnit
from .const import OUTDOOR_ENTITY_ID

RAW_ENTITY_ID = "sensor.air_conditioner_raw_mystery_value"


@pytest.mark.parametrize("method", ["POST", "PUT"])
async def test_outdoor_temperature(
    hass: HomeAssistant, unit: SimulatedUnit, method: str
) -> None:
    """The outdoor reading is decoded, whichever verb the firmware pushes with."""
    await unit.key_exchange()

    # 206: the primed reads are still queued.
    assert await unit.push("outdoor_temperature", 8700, method) == 206

    state = hass.states.get(OUTDOOR_ENTITY_ID)
    assert state is not None
    assert state.state == "37.0"


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(65535, id="int"),
        pytest.param("65535", id="str"),
        pytest.param("garbage", id="non_numeric"),
    ],
)
async def test_outdoor_temperature_created_when_reported(
    hass: HomeAssistant, unit: SimulatedUnit, value: int | str
) -> None:
    """A unit without an outdoor reading reports 65535 and gets no sensor for it.

    The sensor appears once a reading arrives.
    """
    await unit.key_exchange()
    assert hass.states.get(OUTDOOR_ENTITY_ID) is None

    await unit.push("outdoor_temperature", value)
    assert hass.states.get(OUTDOOR_ENTITY_ID) is None

    await unit.push("outdoor_temperature", 8700)

    state = hass.states.get(OUTDOOR_ENTITY_ID)
    assert state is not None
    assert state.state == "37.0"


async def test_outdoor_temperature_lost(
    hass: HomeAssistant, unit: SimulatedUnit
) -> None:
    """A reading that turns into the 65535 sentinel is shown as unknown."""
    await unit.key_exchange()
    await unit.push("outdoor_temperature", 8700)

    await unit.push("outdoor_temperature", 65535)

    state = hass.states.get(OUTDOOR_ENTITY_ID)
    assert state is not None
    assert state.state == STATE_UNKNOWN


async def test_repeated_value_is_not_rewritten(
    hass: HomeAssistant, unit: SimulatedUnit, freezer: FrozenDateTimeFactory
) -> None:
    """The unit re-reports unchanged values; they do not touch the state."""
    await unit.key_exchange()
    # A unit that leaves the primed reads queued would go unavailable meanwhile.
    await unit.drain()
    await unit.push("outdoor_temperature", 8700)
    state = hass.states.get(OUTDOOR_ENTITY_ID)
    assert state is not None
    reported = state.last_reported

    freezer.tick(60)
    await unit.push("outdoor_temperature", 8700)

    state = hass.states.get(OUTDOOR_ENTITY_ID)
    assert state is not None
    assert state.last_reported == reported


async def test_raw_sensor_disabled_by_default(
    hass: HomeAssistant, unit: SimulatedUnit, entity_registry: er.EntityRegistry
) -> None:
    """Raw sensors are diagnostics that only matter when decoding a new property."""
    await unit.key_exchange()

    await unit.push("mystery_value", 42)

    entry = entity_registry.async_get(RAW_ENTITY_ID)
    assert entry is not None
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(RAW_ENTITY_ID) is None


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_raw_sensor_for_unknown_property(
    hass: HomeAssistant, unit: SimulatedUnit
) -> None:
    """Any property the unit reports gets a raw sensor, even one nothing maps."""
    await unit.key_exchange()
    assert hass.states.get(RAW_ENTITY_ID) is None

    await unit.push("mystery_value", 42)

    state = hass.states.get(RAW_ENTITY_ID)
    assert state is not None
    assert state.state == "42"


@pytest.mark.parametrize(
    "value", [pytest.param(65535, id="int"), pytest.param("65535", id="str")]
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_raw_sensor_not_created_for_sentinel(
    hass: HomeAssistant, unit: SimulatedUnit, value: int | str
) -> None:
    """Properties the model does not have report 65535 and get no raw sensor."""
    await unit.key_exchange()

    await unit.push("mystery_value", value)

    assert hass.states.get(RAW_ENTITY_ID) is None


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_raw_sensor_truncates_long_value(
    hass: HomeAssistant, unit: SimulatedUnit
) -> None:
    """Home Assistant rejects states over 255 characters."""
    await unit.key_exchange()

    await unit.push("mystery_value", "x" * 300)

    state = hass.states.get(RAW_ENTITY_ID)
    assert state is not None
    assert state.state == "x" * 255


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_raw_sensor_unknown_after_session_drop(
    hass: HomeAssistant, init_integration: MockConfigEntry, unit: SimulatedUnit
) -> None:
    """A changeable value is forgotten with the session, so it reads unknown."""
    await unit.key_exchange()
    await unit.push("mystery_value", 42)

    init_integration.runtime_data.lan._drop_session()  # noqa: SLF001
    await unit.key_exchange()

    state = hass.states.get(RAW_ENTITY_ID)
    assert state is not None
    assert state.state == STATE_UNKNOWN
