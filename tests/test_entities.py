"""Snapshot tests for every entity Fujitsu FGLair Local creates."""

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import SimulatedUnit
from .const import (
    CLIMATE_ENTITY_ID,
    DSN,
    ECONOMY_ENTITY_ID,
    ENTRY_DATA,
    OCCUPANCY_ENTITY_ID,
    REFRESH_ENTITY_ID,
    SETTINGS_SUPPORTED,
    UNIT_DATAPOINTS,
)
from custom_components.fglair_local import PLATFORMS
from custom_components.fglair_local.const import DOMAIN


@pytest.mark.parametrize(
    "entity_id",
    [CLIMATE_ENTITY_ID, REFRESH_ENTITY_ID],
)
@pytest.mark.usefixtures("init_integration")
async def test_unavailable_before_key_exchange(
    hass: HomeAssistant, entity_id: str
) -> None:
    """Nothing is known about the unit until it has dialled in."""
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


@pytest.mark.parametrize(
    "platforms",
    [pytest.param([platform], id=platform) for platform in PLATFORMS],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    unit: SimulatedUnit,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """A unit that has reported its state yields these entities."""
    await unit.key_exchange()
    await unit.push_all(UNIT_DATAPOINTS)

    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


# Entities that need a numeric value, unlike the raw sensor.
NUMERIC_ENTITIES = [
    pytest.param("economy_mode", ECONOMY_ENTITY_ID, id="switch"),
    pytest.param("human_det", OCCUPANCY_ENTITY_ID, id="binary_sensor"),
    pytest.param(
        "filter_sign_reset", "button.air_conditioner_filter_sign_reset", id="button"
    ),
]


@pytest.mark.parametrize(("name", "entity_id"), NUMERIC_ENTITIES)
@pytest.mark.parametrize(
    "value", [pytest.param(65535, id="int"), pytest.param("65535", id="str")]
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_not_created_for_sentinel(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    name: str,
    entity_id: str,
    value: int | str,
) -> None:
    """The unit lists its model family's properties; 65535 marks absent ones."""
    await unit.key_exchange()

    await unit.push(name, value)

    assert hass.states.get(entity_id) is None
    assert hass.states.get(f"sensor.air_conditioner_raw_{name}") is None


@pytest.mark.parametrize(("name", "entity_id"), NUMERIC_ENTITIES)
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_non_numeric_value_gets_only_raw_sensor(
    hass: HomeAssistant, unit: SimulatedUnit, name: str, entity_id: str
) -> None:
    """A value that is not an integer cannot be on or off, but is still shown raw."""
    await unit.key_exchange()

    await unit.push(name, "garbage")

    assert hass.states.get(entity_id) is None
    state = hass.states.get(f"sensor.air_conditioner_raw_{name}")
    assert state is not None
    assert state.state == "garbage"


async def test_device_info_from_datapoints(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    unit: SimulatedUnit,
    device_registry: dr.DeviceRegistry,
) -> None:
    """The model and firmware the unit reports land on its device."""
    await unit.key_exchange()
    await unit.push_all({"model_name": "TESTMODEL01", "mcu_fw_version": "0.0.1,:,:,:,"})

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, DSN), init_integration.entry_id
    )
    assert device is not None
    assert device.model == "TESTMODEL01"
    assert device.sw_version == "0.0.1"
    assert device.serial_number == DSN


@pytest.mark.usefixtures("mock_register")
@pytest.mark.parametrize(
    ("title", "name", "entity_id"),
    [
        pytest.param("Bedroom", "Bedroom", "climate.bedroom", id="room_name"),
        pytest.param(DSN, "Air conditioner", CLIMATE_ENTITY_ID, id="dsn"),
    ],
)
async def test_device_name(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    title: str,
    name: str,
    entity_id: str,
) -> None:
    """The unit is named after its entry, unless that is only its DSN."""
    entry = MockConfigEntry(domain=DOMAIN, title=title, unique_id=DSN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, DSN), entry.entry_id
    )
    assert device is not None
    assert device.name == name
    assert hass.states.get(entity_id) is not None


@pytest.mark.parametrize(("name", "entity_id"), NUMERIC_ENTITIES[:2])
async def test_value_turning_sentinel_is_unknown(
    hass: HomeAssistant, unit: SimulatedUnit, name: str, entity_id: str
) -> None:
    """An entity stays once created, and reads unknown if the value turns 65535."""
    await unit.key_exchange()
    await unit.push_all({**SETTINGS_SUPPORTED, name: 1})

    await unit.push(name, 65535)

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_UNKNOWN


async def test_disabled_entity_stops_listening(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An entity the user disables is no longer updated by pushed values."""
    await unit.key_exchange()
    await unit.push_all({**SETTINGS_SUPPORTED, "economy_mode": 0})

    entity_registry.async_update_entity(
        ECONOMY_ENTITY_ID, disabled_by=er.RegistryEntryDisabler.USER
    )
    await hass.async_block_till_done()
    assert hass.states.get(ECONOMY_ENTITY_ID) is None

    await unit.push("economy_mode", 1)

    assert hass.states.get(ECONOMY_ENTITY_ID) is None
    assert "incorrectly being triggered" not in caplog.text
