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
from .const import DSN, ECONOMY_ENTITY_ID, SETTINGS_SUPPORTED
from custom_components.fglair_local.const import DOMAIN
from custom_components.fglair_local.properties import TOGGLE_PROPERTIES

CAPABILITIES = SETTINGS_SUPPORTED["device_capabilities"]
COIL_DRY = 1 << 18
COIL_DRY_ENTITY_ID = "switch.air_conditioner_coil_dry_mode"
HUMAN_SENSOR_ENTITY_ID = "switch.air_conditioner_human_sensor"


@pytest.fixture
def stale_switches(entity_registry: er.EntityRegistry) -> None:
    """Register switches an earlier version created, ahead of the entry loading."""
    for prop in ("demand_control", "coil_dry_mode"):
        entity_registry.async_get_or_create(
            SWITCH_DOMAIN,
            DOMAIN,
            f"{DSN}_{prop}",
            suggested_object_id=f"air_conditioner_{prop}",
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [pytest.param(0, STATE_OFF, id="off"), pytest.param(1, STATE_ON, id="on")],
)
async def test_created_when_reported(
    hass: HomeAssistant, unit: SimulatedUnit, value: int, expected: str
) -> None:
    """A supported switch only appears once the unit reports its property."""
    await unit.key_exchange()
    await unit.push_all(SETTINGS_SUPPORTED)
    assert hass.states.get(ECONOMY_ENTITY_ID) is None

    await unit.push("economy_mode", value)

    state = hass.states.get(ECONOMY_ENTITY_ID)
    assert state is not None
    assert state.state == expected


@pytest.mark.parametrize(
    ("datapoints", "entity_id", "created"),
    [
        pytest.param(
            {"device_capabilities": CAPABILITIES, "economy_mode": 0},
            ECONOMY_ENTITY_ID,
            True,
            id="capability_set",
        ),
        pytest.param(
            {"device_capabilities": CAPABILITIES & ~(1 << 12), "economy_mode": 0},
            ECONOMY_ENTITY_ID,
            False,
            id="capability_unset",
        ),
        pytest.param(
            {"economy_mode": 0}, ECONOMY_ENTITY_ID, False, id="capabilities_unknown"
        ),
        pytest.param(
            {"device_capabilities": 65535, "economy_mode": 0},
            ECONOMY_ENTITY_ID,
            False,
            id="capabilities_sentinel",
        ),
        pytest.param(
            {"device_capabilities": CAPABILITIES & ~(1 << 16), "powerful_mode": 0},
            "switch.air_conditioner_powerful",
            False,
            id="powerful_unset",
        ),
        pytest.param(
            {"device_capabilities": CAPABILITIES, "coil_dry_mode": 0},
            COIL_DRY_ENTITY_ID,
            False,
            # Reported by an AP-WF3E without the capability.
            id="coil_dry_unset",
        ),
        pytest.param(
            {"device_capabilities": CAPABILITIES | COIL_DRY, "coil_dry_mode": 0},
            COIL_DRY_ENTITY_ID,
            True,
            id="coil_dry_set",
        ),
        pytest.param(
            {"human_det": 1, "human_det_auto_save": 0},
            HUMAN_SENSOR_ENTITY_ID,
            True,
            id="human_sensor",
        ),
        pytest.param(
            {"human_det": 0, "human_det_auto_save": 0},
            HUMAN_SENSOR_ENTITY_ID,
            False,
            id="no_human_sensor",
        ),
        pytest.param(
            {"human_det_auto_save": 0},
            HUMAN_SENSOR_ENTITY_ID,
            False,
            id="human_sensor_unknown",
        ),
        pytest.param(
            {"wifi_led_enable": 0},
            "switch.air_conditioner_wi_fi_led",
            True,
            id="ungated",
        ),
    ],
)
async def test_created_only_when_supported(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    datapoints: dict[str, int],
    entity_id: str,
    created: bool,
) -> None:
    """A switch needs what the FGLair app needs to offer the setting."""
    await unit.key_exchange()
    await unit.push_all(datapoints)

    assert (hass.states.get(entity_id) is not None) is created


@pytest.mark.parametrize(
    ("before", "support", "entity_id"),
    [
        pytest.param(
            {"economy_mode": 1},
            {"device_capabilities": CAPABILITIES},
            ECONOMY_ENTITY_ID,
            id="capabilities",
        ),
        pytest.param(
            {"human_det_auto_save": 1},
            {"human_det": 1},
            HUMAN_SENSOR_ENTITY_ID,
            id="human_sensor",
        ),
    ],
)
async def test_created_when_support_arrives_late(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    before: dict[str, int],
    support: dict[str, int],
    entity_id: str,
) -> None:
    """A setting reported before the unit says it supports it appears once it does."""
    await unit.key_exchange()
    await unit.push_all(before)
    assert hass.states.get(entity_id) is None

    await unit.push_all(support)

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_ON


@pytest.mark.usefixtures("stale_switches", "init_integration")
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
    # Whether coil dry is supported is not yet known, so its switch stays.
    assert entity_registry.async_get(COIL_DRY_ENTITY_ID) is not None


@pytest.mark.usefixtures("stale_switches")
async def test_unsupported_switch_kept_in_registry(
    hass: HomeAssistant, unit: SimulatedUnit, entity_registry: er.EntityRegistry
) -> None:
    """A switch from before support was checked is not provided, but not deleted.

    The user's renames and area stay until they remove it.
    """
    await unit.key_exchange()
    await unit.push_all({"device_capabilities": CAPABILITIES, "coil_dry_mode": 0})

    assert entity_registry.async_get(COIL_DRY_ENTITY_ID) is not None
    assert hass.states.get(COIL_DRY_ENTITY_ID) is None


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
    await unit.push_all(
        {
            "device_capabilities": CAPABILITIES | COIL_DRY,
            "human_det": 1,
            **dict.fromkeys(TOGGLE_PROPERTIES, 0),
        }
    )

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
    await unit.push_all({**SETTINGS_SUPPORTED, name: 1 - value})

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
