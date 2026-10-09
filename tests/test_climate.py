"""End-to-end tests of the climate entity, driven by a simulated unit."""

import pytest
from pytest_homeassistant_custom_component.common import (
    async_mock_restore_state_shutdown_restart,
    mock_restore_cache_with_extra_data,
)

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_SWING_HORIZONTAL_MODE,
    ATTR_SWING_HORIZONTAL_MODES,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_SWING_HORIZONTAL_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util.unit_system import (
    METRIC_SYSTEM,
    US_CUSTOMARY_SYSTEM,
    UnitSystem,
)

from . import SimulatedUnit, read_resource, written
from .const import AC_INFO1, AC_INFO1_FROM_20, CLIMATE_ENTITY_ID, UNIT_DATAPOINTS
from custom_components.fglair_local.climate import DEFAULT_SETPOINT
from custom_components.fglair_local.const import DOMAIN
from custom_components.fglair_local.properties import (
    EXTRA_PROPERTIES,
    POSITIONS,
    PRIME_PROPERTIES,
)

PRIMED = (*PRIME_PROPERTIES, *EXTRA_PROPERTIES)
# Heat pump with both swing axes, from UNIT_DATAPOINTS.
CAPABILITIES = {"device_capabilities": 229375}
SWING_FEATURES = (
    ClimateEntityFeature.SWING_MODE | ClimateEntityFeature.SWING_HORIZONTAL_MODE
)
NO_SWING = ClimateEntityFeature(0)
# Without a position count, a louvre can only swing or stop.
SWING_ONLY = ["on", "off"]
# Counts from UNIT_DATAPOINTS: 4 vertical, 5 horizontal from the left.
LOUVRE_COUNTS = {"af_vertical_num_dir": 4, "af_horizontal_num_dir": 21}
VERTICAL_MODES = ["on", "off", *POSITIONS[:4]]
HORIZONTAL_MODES = ["on", "off", *POSITIONS[:5]]

OFF_WITHOUT_SETPOINT = {**UNIT_DATAPOINTS, "operation_mode": 0, "adjust_temperature": 0}
RESTORED_SETPOINT = 21.5


@pytest.fixture
def restored_setpoint(hass: HomeAssistant) -> None:
    """Seed the setpoint saved before a restart, ahead of the entry loading."""
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(CLIMATE_ENTITY_ID, HVACMode.OFF),
                {ATTR_TEMPERATURE: RESTORED_SETPOINT},
            ),
        ),
    )


async def test_state_from_datapoints(hass: HomeAssistant, unit: SimulatedUnit) -> None:
    """Pushed raw values are decoded into the climate state."""
    await unit.key_exchange()
    await unit.push_all(UNIT_DATAPOINTS)

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.state == HVACMode.COOL
    assert state.attributes[ATTR_TEMPERATURE] == 24.0
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 28.5
    assert state.attributes[ATTR_FAN_MODE] == "auto"
    assert state.attributes[ATTR_SWING_MODE] == "on"
    assert state.attributes[ATTR_SWING_HORIZONTAL_MODE] == "position_5"


@pytest.mark.parametrize(
    ("capabilities", "hvac_modes", "fan_modes"),
    [
        pytest.param(
            229375,
            ["off", "cool", "dry", "fan_only", "heat", "heat_cool"],
            ["quiet", "low", "medium", "high", "auto"],
            id="heat_pump",
        ),
        pytest.param(
            # Cool, dry, fan auto and fan low only.
            0b1_0010_0011,
            ["off", "cool", "dry"],
            ["low", "auto"],
            id="cooling_only",
        ),
    ],
)
async def test_modes_follow_capabilities(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    capabilities: int,
    hvac_modes: list[str],
    fan_modes: list[str],
) -> None:
    """Only the modes the unit reports it supports are offered."""
    await unit.key_exchange()
    await unit.push("device_capabilities", capabilities)

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[ATTR_HVAC_MODES] == hvac_modes
    assert state.attributes[ATTR_FAN_MODES] == fan_modes


async def test_services_queue_writes(hass: HomeAssistant, unit: SimulatedUnit) -> None:
    """Service calls reach the unit as property writes, ahead of the primed reads."""
    await unit.key_exchange()
    await unit.push_all(UNIT_DATAPOINTS)

    for service, data in (
        (SERVICE_SET_TEMPERATURE, {ATTR_TEMPERATURE: 25}),
        (SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: HVACMode.HEAT}),
        (SERVICE_SET_FAN_MODE, {ATTR_FAN_MODE: "quiet"}),
        (SERVICE_SET_SWING_MODE, {ATTR_SWING_MODE: "position_4"}),
        (SERVICE_SET_SWING_HORIZONTAL_MODE, {ATTR_SWING_HORIZONTAL_MODE: "on"}),
        (SERVICE_TURN_OFF, {}),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            service,
            {ATTR_ENTITY_ID: CLIMATE_ENTITY_ID, **data},
            blocking=True,
        )

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_TEMPERATURE] == 25.0
    assert state.attributes[ATTR_FAN_MODE] == "quiet"
    assert state.attributes[ATTR_SWING_MODE] == "position_4"
    assert state.attributes[ATTR_SWING_HORIZONTAL_MODE] == "on"

    writes = [await unit.fetch_write() for _ in range(6)]
    commands = [*writes, *[await unit.fetch_command() for _ in PRIMED]]
    assert [command["seq_no"] for command in commands] == list(range(len(commands)))
    assert [written(command) for command in writes] == [
        ("adjust_temperature", 250, "integer"),
        ("fan_speed", 0, "integer"),
        # The unit ignores swing writes that are not typed boolean.
        ("af_vertical_swing", 0, "boolean"),
        ("af_vertical_direction", 4, "integer"),
        ("af_horizontal_swing", 1, "boolean"),
        # Turning off replaced the queued heat write and went out last.
        ("operation_mode", 0, "integer"),
    ]
    assert [read_resource(command) for command in commands[6:]] == [
        f"property.json?name={name}" for name in PRIMED
    ]
    assert (await unit.fetch_command())["data"] == {}


async def test_turn_on_waits_for_the_unit(
    hass: HomeAssistant, unit: SimulatedUnit
) -> None:
    """Turning on resumes the last mode, which only the unit knows."""
    await unit.key_exchange()
    await unit.push_all({**UNIT_DATAPOINTS, "operation_mode": 0})

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: CLIMATE_ENTITY_ID},
        blocking=True,
    )

    assert written(await unit.fetch_write()) == ("operation_mode", 1, "integer")
    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.state == HVACMode.OFF

    await unit.push("operation_mode", 3)

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.state == HVACMode.COOL


async def test_set_temperature_with_mode(
    hass: HomeAssistant, unit: SimulatedUnit
) -> None:
    """A setpoint sent together with a mode writes both."""
    await unit.key_exchange()
    await unit.push_all({**UNIT_DATAPOINTS, "operation_mode": 0})

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {
            ATTR_ENTITY_ID: CLIMATE_ENTITY_ID,
            ATTR_TEMPERATURE: 22.5,
            ATTR_HVAC_MODE: HVACMode.HEAT,
        },
        blocking=True,
    )

    assert [written(await unit.fetch_write()) for _ in range(2)] == [
        ("operation_mode", 6, "integer"),
        ("adjust_temperature", 225, "integer"),
    ]
    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_TEMPERATURE] == 22.5


async def test_set_temperature_checked_against_current_mode(
    hass: HomeAssistant, unit: SimulatedUnit
) -> None:
    """Home Assistant checks the target against the current mode's range, not the new one's."""
    await unit.key_exchange()
    await unit.push_all(UNIT_DATAPOINTS)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {
                ATTR_ENTITY_ID: CLIMATE_ENTITY_ID,
                ATTR_TEMPERATURE: 16,
                ATTR_HVAC_MODE: HVACMode.HEAT,
            },
            blocking=True,
        )

    assert read_resource(await unit.fetch_command()) == (
        f"property.json?name={PRIMED[0]}"
    )


@pytest.mark.parametrize(
    ("datapoints", "min_temp", "max_temp"),
    [
        pytest.param({"operation_mode": 3}, 18.0, 30.0, id="cool"),
        pytest.param({"operation_mode": 4}, 18.0, 30.0, id="dry"),
        pytest.param({"operation_mode": 2}, 18.0, 30.0, id="auto"),
        pytest.param({"operation_mode": 6}, 16.0, 30.0, id="heat"),
        pytest.param({"operation_mode": 5}, 16.0, 30.0, id="fan"),
        pytest.param({"operation_mode": 0}, 16.0, 30.0, id="off"),
        pytest.param({"operation_mode": 65535}, 16.0, 30.0, id="mode_sentinel"),
        pytest.param({}, 16.0, 30.0, id="mode_unknown"),
        pytest.param(
            {"operation_mode": 3, "ac_info1": AC_INFO1}, 18.0, 30.0, id="cool_reported"
        ),
        pytest.param(
            {"operation_mode": 6, "ac_info1": AC_INFO1}, 16.0, 30.0, id="heat_reported"
        ),
        pytest.param(
            {"operation_mode": 3, "ac_info1": AC_INFO1_FROM_20},
            20.0,
            30.0,
            id="cool_from_20",
        ),
        pytest.param(
            {"operation_mode": 4, "ac_info1": AC_INFO1_FROM_20},
            20.0,
            30.0,
            id="dry_follows_cool",
        ),
        pytest.param(
            {"operation_mode": 2, "ac_info1": AC_INFO1_FROM_20},
            20.0,
            30.0,
            id="auto_from_20",
        ),
        pytest.param(
            {"operation_mode": 6, "ac_info1": AC_INFO1_FROM_20},
            16.0,
            30.0,
            id="heat_from_16",
        ),
        pytest.param(
            {"operation_mode": 0, "ac_info1": AC_INFO1_FROM_20},
            16.0,
            30.0,
            id="off_spans_all",
        ),
    ],
)
async def test_setpoint_range_follows_mode(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    datapoints: dict[str, int | str],
    min_temp: float,
    max_temp: float,
) -> None:
    """Each mode has the unit's own setpoint range, else the FGLair app's."""
    await unit.key_exchange()
    await unit.push_all(datapoints)

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[ATTR_MIN_TEMP] == min_temp
    assert state.attributes[ATTR_MAX_TEMP] == max_temp


async def test_setpoint_below_mode_range_rejected(
    hass: HomeAssistant, unit: SimulatedUnit
) -> None:
    """A setpoint the current mode does not accept is refused without writing it."""
    await unit.key_exchange()
    await unit.push_all({**UNIT_DATAPOINTS, "ac_info1": AC_INFO1_FROM_20})

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: CLIMATE_ENTITY_ID, ATTR_TEMPERATURE: 19},
            blocking=True,
        )

    assert read_resource(await unit.fetch_command()) == (
        f"property.json?name={PRIMED[0]}"
    )


@pytest.mark.parametrize(
    ("datapoints", "swing_modes", "swing_horizontal_modes", "features"),
    [
        pytest.param(
            {"device_capabilities": 0b1100_0000_0001},
            SWING_ONLY,
            SWING_ONLY,
            SWING_FEATURES,
            id="both_axes",
        ),
        pytest.param(
            {"device_capabilities": 0b1100_0000_0001, **LOUVRE_COUNTS},
            VERTICAL_MODES,
            HORIZONTAL_MODES,
            SWING_FEATURES,
            id="both_axes_with_counts",
        ),
        pytest.param(
            {"device_capabilities": 0b0100_0000_0001},
            SWING_ONLY,
            None,
            ClimateEntityFeature.SWING_MODE,
            id="vertical_only",
        ),
        pytest.param(
            {"device_capabilities": 0b1000_0000_0001},
            None,
            SWING_ONLY,
            ClimateEntityFeature.SWING_HORIZONTAL_MODE,
            id="horizontal_only",
        ),
        pytest.param(
            {"device_capabilities": 0b0000_0000_0001},
            None,
            None,
            NO_SWING,
            id="no_swing",
        ),
        pytest.param(
            # The capability bits win over a reported swing property.
            {
                "device_capabilities": 0b0000_0000_0001,
                "af_vertical_swing": 0,
                "af_horizontal_swing": 0,
            },
            None,
            None,
            NO_SWING,
            id="no_swing_but_reported",
        ),
        pytest.param({}, None, None, NO_SWING, id="unknown_nothing_reported"),
        pytest.param(
            {"af_vertical_swing": 0},
            SWING_ONLY,
            None,
            ClimateEntityFeature.SWING_MODE,
            id="unknown_vertical_reported",
        ),
        pytest.param(
            {"af_horizontal_swing": 1},
            None,
            SWING_ONLY,
            ClimateEntityFeature.SWING_HORIZONTAL_MODE,
            id="unknown_horizontal_reported",
        ),
        pytest.param(
            {"af_vertical_swing": 65535, "af_horizontal_swing": 65535},
            None,
            None,
            NO_SWING,
            id="unknown_sentinel_reported",
        ),
        pytest.param(
            {"device_capabilities": 65535, "af_vertical_swing": 1},
            SWING_ONLY,
            None,
            ClimateEntityFeature.SWING_MODE,
            id="sentinel_capabilities",
        ),
    ],
)
async def test_swing_axes_offered(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    datapoints: dict[str, int],
    swing_modes: list[str] | None,
    swing_horizontal_modes: list[str] | None,
    features: ClimateEntityFeature,
) -> None:
    """An axis is offered when its capability bit is set.

    Until the unit reports its capabilities, an axis is offered once its swing
    property has been reported.
    """
    await unit.key_exchange()
    await unit.push_all(datapoints)

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes.get(ATTR_SWING_MODES) == swing_modes
    assert state.attributes.get(ATTR_SWING_HORIZONTAL_MODES) == swing_horizontal_modes
    assert state.attributes[ATTR_SUPPORTED_FEATURES] & SWING_FEATURES == features


@pytest.mark.parametrize(
    ("num_dir", "swing_modes"),
    [
        pytest.param(4, VERTICAL_MODES, id="four"),
        pytest.param(6, ["on", "off", *POSITIONS[:6]], id="six"),
        pytest.param(3, ["on", "off", *POSITIONS[:3]], id="three"),
        pytest.param(1, ["on", "off", "position_1"], id="one"),
        pytest.param(15, ["on", "off", *POSITIONS], id="fifteen"),
        pytest.param(0, SWING_ONLY, id="zero"),
        pytest.param(-1, SWING_ONLY, id="negative"),
        pytest.param(16, SWING_ONLY, id="too_many"),
        pytest.param(65535, SWING_ONLY, id="sentinel"),
    ],
)
async def test_vertical_positions_follow_count(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    num_dir: int,
    swing_modes: list[str],
) -> None:
    """Vertical positions follow a count from 1 to 15; otherwise there are none."""
    await unit.key_exchange()
    await unit.push_all({**CAPABILITIES, "af_vertical_num_dir": num_dir})

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[ATTR_SWING_MODES] == swing_modes
    # The vertical count says nothing about the horizontal louvre.
    assert state.attributes[ATTR_SWING_HORIZONTAL_MODES] == SWING_ONLY


@pytest.mark.parametrize(
    ("num_dir", "swing_horizontal_modes"),
    [
        pytest.param(5, HORIZONTAL_MODES, id="five_from_right"),
        pytest.param(21, HORIZONTAL_MODES, id="five_from_left"),
        pytest.param(3, ["on", "off", *POSITIONS[:3]], id="three_from_right"),
        pytest.param(19, ["on", "off", *POSITIONS[:3]], id="three_from_left"),
        pytest.param(2, ["on", "off", *POSITIONS[:2]], id="two_from_right"),
        pytest.param(20, ["on", "off", *POSITIONS[:4]], id="four_from_left"),
        pytest.param(15, ["on", "off", *POSITIONS], id="fifteen_from_right"),
        pytest.param(31, ["on", "off", *POSITIONS], id="fifteen_from_left"),
        pytest.param(0, SWING_ONLY, id="zero"),
        pytest.param(16, SWING_ONLY, id="sixteen"),
        pytest.param(32, SWING_ONLY, id="too_many"),
        pytest.param(-1, SWING_ONLY, id="negative"),
        pytest.param(65535, SWING_ONLY, id="sentinel"),
    ],
)
async def test_horizontal_positions_follow_count(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    num_dir: int,
    swing_horizontal_modes: list[str],
) -> None:
    """Horizontal positions follow the count, listed left to right either way.

    1-15 count from the right, 17-31 from the left; anything else gives none.
    """
    await unit.key_exchange()
    await unit.push_all({**CAPABILITIES, "af_horizontal_num_dir": num_dir})

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[ATTR_SWING_HORIZONTAL_MODES] == swing_horizontal_modes
    assert state.attributes[ATTR_SWING_MODES] == SWING_ONLY


@pytest.mark.parametrize(
    ("datapoints", "swing_mode", "swing_horizontal_mode"),
    [
        pytest.param(
            {
                "af_vertical_swing": 1,
                "af_vertical_direction": 2,
                "af_horizontal_swing": 1,
                "af_horizontal_direction": 3,
            },
            "on",
            "on",
            id="swinging",
        ),
        pytest.param(
            {
                "af_vertical_swing": 0,
                "af_vertical_direction": 2,
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 3,
            },
            "position_2",
            "position_3",
            id="held",
        ),
        pytest.param(
            {
                "af_vertical_swing": 0,
                "af_vertical_direction": 4,
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 5,
            },
            "position_4",
            "position_5",
            id="held_at_last",
        ),
        pytest.param(
            {
                "af_vertical_swing": 0,
                "af_vertical_direction": 4,
                "af_vertical_num_dir": 3,
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 5,
                "af_horizontal_num_dir": 19,
            },
            "off",
            "off",
            id="beyond_count",
        ),
        pytest.param(
            {
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 1,
                "af_horizontal_num_dir": 5,
            },
            None,
            "position_5",
            id="from_right_first",
        ),
        pytest.param(
            {
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 2,
                "af_horizontal_num_dir": 5,
            },
            None,
            "position_4",
            id="from_right_second",
        ),
        pytest.param(
            {
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 5,
                "af_horizontal_num_dir": 5,
            },
            None,
            "position_1",
            id="from_right_last",
        ),
        pytest.param(
            {
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 1,
                "af_horizontal_num_dir": 4,
            },
            None,
            "position_4",
            id="from_right_numbered",
        ),
        pytest.param(
            {
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 1,
                "af_horizontal_num_dir": 19,
            },
            None,
            "position_1",
            id="from_left_three",
        ),
        pytest.param(
            {
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 2,
                "af_horizontal_num_dir": 20,
            },
            None,
            "position_2",
            id="from_left_numbered",
        ),
        pytest.param(
            {
                "af_vertical_swing": 0,
                "af_vertical_direction": 2,
                "af_vertical_num_dir": 0,
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 3,
                "af_horizontal_num_dir": 0,
            },
            "off",
            "off",
            id="no_positions",
        ),
        pytest.param(
            {
                "af_vertical_swing": 0,
                "af_vertical_direction": 6,
                "af_vertical_num_dir": 6,
                "af_horizontal_swing": 1,
            },
            "position_6",
            "on",
            id="held_numbered",
        ),
        pytest.param(
            {
                "af_vertical_swing": 0,
                "af_vertical_direction": 1,
                "af_vertical_num_dir": 8,
                "af_horizontal_swing": 1,
            },
            "position_1",
            "on",
            id="held_numbered_first",
        ),
        pytest.param(
            {
                "af_vertical_swing": 0,
                "af_vertical_direction": 7,
                "af_vertical_num_dir": 6,
                "af_horizontal_swing": 1,
            },
            "off",
            "on",
            id="beyond_numbered_count",
        ),
        pytest.param(
            {
                "af_vertical_swing": 0,
                "af_vertical_direction": 4,
                "af_vertical_num_dir": 4,
                "af_horizontal_swing": 1,
            },
            "position_4",
            "on",
            id="held_last_with_count",
        ),
        pytest.param(
            {
                "af_vertical_swing": 0,
                "af_vertical_direction": 5,
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 6,
            },
            "off",
            "off",
            id="out_of_range",
        ),
        pytest.param(
            {
                "af_vertical_swing": 0,
                "af_vertical_direction": 0,
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 0,
            },
            "off",
            "off",
            id="position_zero",
        ),
        pytest.param(
            {
                "af_vertical_swing": 0,
                "af_vertical_direction": 65535,
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 65535,
            },
            "off",
            "off",
            id="position_sentinel",
        ),
        pytest.param(
            {"af_vertical_swing": 0, "af_horizontal_swing": 0},
            "off",
            "off",
            id="position_unknown",
        ),
        pytest.param(
            {
                "af_vertical_swing": 65535,
                "af_vertical_direction": 2,
                "af_horizontal_swing": 65535,
                "af_horizontal_direction": 3,
            },
            None,
            None,
            id="swing_sentinel",
        ),
        pytest.param(
            {"af_vertical_direction": 2, "af_horizontal_direction": 3},
            None,
            None,
            id="swing_unknown",
        ),
    ],
)
async def test_swing_state(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    datapoints: dict[str, int],
    swing_mode: str | None,
    swing_horizontal_mode: str | None,
) -> None:
    """Swinging reads as on, a held louvre as its position, anything else as off.

    Swing is not claimed to be off before the unit reports it.
    """
    await unit.key_exchange()
    await unit.push_all({**CAPABILITIES, **LOUVRE_COUNTS, **datapoints})

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[ATTR_SWING_MODE] == swing_mode
    assert state.attributes[ATTR_SWING_HORIZONTAL_MODE] == swing_horizontal_mode


@pytest.mark.parametrize(
    ("before", "service", "data", "writes", "attribute", "after"),
    [
        pytest.param(
            {"af_vertical_swing": 0},
            SERVICE_SET_SWING_MODE,
            {ATTR_SWING_MODE: "on"},
            [("af_vertical_swing", 1, "boolean")],
            ATTR_SWING_MODE,
            "on",
            id="vertical_on",
        ),
        pytest.param(
            {"af_vertical_swing": 1},
            SERVICE_SET_SWING_MODE,
            {ATTR_SWING_MODE: "off"},
            [("af_vertical_swing", 0, "boolean")],
            ATTR_SWING_MODE,
            # A stopped louvre shows the position the unit last reported.
            "position_1",
            id="vertical_off",
        ),
        pytest.param(
            {"af_vertical_swing": 1},
            SERVICE_SET_SWING_MODE,
            {ATTR_SWING_MODE: "position_3"},
            [
                ("af_vertical_swing", 0, "boolean"),
                ("af_vertical_direction", 3, "integer"),
            ],
            ATTR_SWING_MODE,
            "position_3",
            id="vertical_position",
        ),
        pytest.param(
            {"af_vertical_swing": 1, "af_vertical_num_dir": 6},
            SERVICE_SET_SWING_MODE,
            {ATTR_SWING_MODE: "position_5"},
            [
                ("af_vertical_swing", 0, "boolean"),
                ("af_vertical_direction", 5, "integer"),
            ],
            ATTR_SWING_MODE,
            "position_5",
            id="vertical_numbered_position",
        ),
        pytest.param(
            {"af_vertical_swing": 1, "af_vertical_num_dir": 8},
            SERVICE_SET_SWING_MODE,
            {ATTR_SWING_MODE: "position_8"},
            [
                ("af_vertical_swing", 0, "boolean"),
                ("af_vertical_direction", 8, "integer"),
            ],
            ATTR_SWING_MODE,
            "position_8",
            id="vertical_numbered_last",
        ),
        pytest.param(
            {"af_vertical_swing": 1, "af_vertical_num_dir": 6},
            SERVICE_SET_SWING_MODE,
            {ATTR_SWING_MODE: "off"},
            [("af_vertical_swing", 0, "boolean")],
            ATTR_SWING_MODE,
            # The unit last reported direction 1.
            "position_1",
            id="vertical_off_numbered",
        ),
        pytest.param(
            {"af_horizontal_swing": 0},
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: "on"},
            [("af_horizontal_swing", 1, "boolean")],
            ATTR_SWING_HORIZONTAL_MODE,
            "on",
            id="horizontal_on",
        ),
        pytest.param(
            {"af_horizontal_swing": 1},
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: "off"},
            [("af_horizontal_swing", 0, "boolean")],
            ATTR_SWING_HORIZONTAL_MODE,
            "position_5",
            id="horizontal_off",
        ),
        pytest.param(
            {"af_horizontal_swing": 1},
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: "position_2"},
            [
                ("af_horizontal_swing", 0, "boolean"),
                ("af_horizontal_direction", 2, "integer"),
            ],
            ATTR_SWING_HORIZONTAL_MODE,
            "position_2",
            id="horizontal_position",
        ),
        pytest.param(
            {"af_horizontal_swing": 1, "af_horizontal_num_dir": 5},
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: "position_1"},
            [
                ("af_horizontal_swing", 0, "boolean"),
                ("af_horizontal_direction", 5, "integer"),
            ],
            ATTR_SWING_HORIZONTAL_MODE,
            "position_1",
            id="horizontal_from_right_leftmost",
        ),
        pytest.param(
            {"af_horizontal_swing": 1, "af_horizontal_num_dir": 5},
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: "position_2"},
            [
                ("af_horizontal_swing", 0, "boolean"),
                ("af_horizontal_direction", 4, "integer"),
            ],
            ATTR_SWING_HORIZONTAL_MODE,
            "position_2",
            id="horizontal_from_right_second",
        ),
        pytest.param(
            {"af_horizontal_swing": 1, "af_horizontal_num_dir": 5},
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: "position_5"},
            [
                ("af_horizontal_swing", 0, "boolean"),
                ("af_horizontal_direction", 1, "integer"),
            ],
            ATTR_SWING_HORIZONTAL_MODE,
            "position_5",
            id="horizontal_from_right_rightmost",
        ),
        pytest.param(
            {"af_horizontal_swing": 1, "af_horizontal_num_dir": 19},
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: "position_3"},
            [
                ("af_horizontal_swing", 0, "boolean"),
                ("af_horizontal_direction", 3, "integer"),
            ],
            ATTR_SWING_HORIZONTAL_MODE,
            "position_3",
            id="horizontal_from_left_three",
        ),
        pytest.param(
            {"af_horizontal_swing": 1, "af_horizontal_num_dir": 5},
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: "off"},
            [("af_horizontal_swing", 0, "boolean")],
            ATTR_SWING_HORIZONTAL_MODE,
            # Direction 5 is the leftmost when counted from the right.
            "position_1",
            id="horizontal_off_from_right",
        ),
    ],
)
async def test_set_swing_mode(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    before: dict[str, int],
    service: str,
    data: dict[str, str],
    writes: list[tuple[str, int, str]],
    attribute: str,
    after: str,
) -> None:
    """Swing on and off write the swing flag; a position stops swinging, then moves.

    The state follows straight away, ahead of the unit's read-back.
    """
    await unit.key_exchange()
    await unit.push_all({**UNIT_DATAPOINTS, **before})

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        service,
        {ATTR_ENTITY_ID: CLIMATE_ENTITY_ID, **data},
        blocking=True,
    )

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[attribute] == after
    assert [written(await unit.fetch_write()) for _ in writes] == writes
    assert read_resource(await unit.fetch_command()) == (
        f"property.json?name={PRIMED[0]}"
    )


@pytest.mark.parametrize(
    ("service", "data"),
    [
        pytest.param(
            SERVICE_SET_SWING_MODE, {ATTR_SWING_MODE: "vertical"}, id="old_vertical"
        ),
        pytest.param(
            SERVICE_SET_SWING_MODE,
            {ATTR_SWING_MODE: "horizontal"},
            id="old_horizontal",
        ),
        pytest.param(SERVICE_SET_SWING_MODE, {ATTR_SWING_MODE: "both"}, id="old_both"),
        pytest.param(
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: "both"},
            id="old_both_horizontal",
        ),
        pytest.param(
            SERVICE_SET_SWING_MODE,
            {ATTR_SWING_MODE: "on_right"},
            id="unknown_vertical",
        ),
        pytest.param(
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: "position_6"},
            id="beyond_horizontal_count",
        ),
        pytest.param(
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: "left"},
            id="old_named_horizontal_position",
        ),
        pytest.param(
            SERVICE_SET_SWING_MODE, {ATTR_SWING_MODE: "position_4"}, id="beyond_count"
        ),
        pytest.param(
            SERVICE_SET_SWING_MODE,
            {ATTR_SWING_MODE: "top"},
            id="old_named_position",
        ),
    ],
)
async def test_invalid_swing_mode_rejected(
    hass: HomeAssistant, unit: SimulatedUnit, service: str, data: dict[str, str]
) -> None:
    """Modes the unit does not offer are refused without writing anything."""
    await unit.key_exchange()
    await unit.push_all({**UNIT_DATAPOINTS, "af_vertical_num_dir": 3})

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            service,
            {ATTR_ENTITY_ID: CLIMATE_ENTITY_ID, **data},
            blocking=True,
        )

    assert read_resource(await unit.fetch_command()) == (
        f"property.json?name={PRIMED[0]}"
    )


@pytest.mark.parametrize(
    ("service", "data"),
    [
        pytest.param(
            SERVICE_SET_SWING_MODE, {ATTR_SWING_MODE: "position_1"}, id="vertical"
        ),
        pytest.param(
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: "position_1"},
            id="horizontal",
        ),
    ],
)
async def test_position_rejected_without_count(
    hass: HomeAssistant, unit: SimulatedUnit, service: str, data: dict[str, str]
) -> None:
    """A unit that reports no positions only offers swinging on and off."""
    await unit.key_exchange()
    await unit.push_all(
        {**UNIT_DATAPOINTS, "af_vertical_num_dir": 0, "af_horizontal_num_dir": 0}
    )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            service,
            {ATTR_ENTITY_ID: CLIMATE_ENTITY_ID, **data},
            blocking=True,
        )

    assert read_resource(await unit.fetch_command()) == (
        f"property.json?name={PRIMED[0]}"
    )


@pytest.mark.parametrize(
    ("count", "direction"),
    [
        pytest.param("af_vertical_num_dir", "af_vertical_direction", id="vertical"),
        pytest.param(
            "af_horizontal_num_dir", "af_horizontal_direction", id="horizontal"
        ),
    ],
)
async def test_count_read_before_direction(
    unit: SimulatedUnit, count: str, direction: str
) -> None:
    """A direction reads as off until the count says it exists."""
    await unit.key_exchange()

    resources = [read_resource(command) for command in await unit.drain()]

    assert resources.index(f"property.json?name={count}") < (
        resources.index(f"property.json?name={direction}")
    )


async def test_numbered_position_follows_late_count(
    hass: HomeAssistant, unit: SimulatedUnit
) -> None:
    """A position the count has not yet vouched for shows once the count arrives."""
    await unit.key_exchange()
    await unit.push_all(
        {**CAPABILITIES, "af_vertical_swing": 0, "af_vertical_direction": 6}
    )
    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[ATTR_SWING_MODE] == "off"

    await unit.push("af_vertical_num_dir", 6)

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[ATTR_SWING_MODE] == "position_6"
    assert state.attributes[ATTR_SWING_MODES] == [
        "on",
        "off",
        *POSITIONS[:6],
    ]


@pytest.mark.parametrize(
    ("attribute", "first"),
    [
        pytest.param(ATTR_SWING_MODE, "Position 1 (top)", id="vertical"),
        pytest.param(ATTR_SWING_HORIZONTAL_MODE, "Position 1 (left)", id="horizontal"),
    ],
)
async def test_positions_are_translated(
    hass: HomeAssistant, attribute: str, first: str
) -> None:
    """Every louvre position has a name, and the first says which end it is."""
    translations = await async_get_translations(hass, "en", "entity", [DOMAIN])

    prefix = (
        f"component.{DOMAIN}.entity.climate.air_conditioner"
        f".state_attributes.{attribute}.state"
    )
    assert {f"{prefix}.{position}" for position in POSITIONS} <= translations.keys()
    assert translations[f"{prefix}.position_1"] == first


@pytest.mark.parametrize(
    ("name", "value", "attribute"),
    [
        pytest.param("display_temperature", 65535, ATTR_CURRENT_TEMPERATURE, id="room"),
        pytest.param("fan_speed", 65535, ATTR_FAN_MODE, id="fan_sentinel"),
        pytest.param("fan_speed", 9, ATTR_FAN_MODE, id="fan_out_of_range"),
    ],
)
async def test_unreadable_values_are_unknown(
    hass: HomeAssistant, unit: SimulatedUnit, name: str, value: int, attribute: str
) -> None:
    """The not-applicable sentinel and unknown enum values read as None."""
    await unit.key_exchange()
    await unit.push_all(UNIT_DATAPOINTS)
    await unit.push(name, value)

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[attribute] is None


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(65535, id="sentinel"),
        pytest.param(7, id="out_of_range"),
        # ON has no HVAC mode of its own.
        pytest.param(1, id="on"),
    ],
)
async def test_unreadable_mode_is_unknown(
    hass: HomeAssistant, unit: SimulatedUnit, value: int
) -> None:
    """An operation mode the integration cannot map leaves the state unknown."""
    await unit.key_exchange()
    await unit.push_all(UNIT_DATAPOINTS)
    await unit.push("operation_mode", value)

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.state == STATE_UNKNOWN


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(0, id="off"),
        pytest.param(65535, id="sentinel"),
    ],
)
async def test_setpoint_kept_when_unreadable(
    hass: HomeAssistant, unit: SimulatedUnit, value: int
) -> None:
    """A unit turned off reports no setpoint, so the last real one stays."""
    await unit.key_exchange()
    # Not DEFAULT_SETPOINT, so keeping it is told apart from falling back.
    await unit.push_all({**UNIT_DATAPOINTS, "adjust_temperature": 250})
    await unit.push("operation_mode", 0)
    await unit.push("adjust_temperature", value)

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_TEMPERATURE] == 25.0


@pytest.mark.parametrize(
    "datapoints",
    [
        pytest.param({}, id="nothing_reported"),
        pytest.param(OFF_WITHOUT_SETPOINT, id="off"),
    ],
)
async def test_setpoint_defaults_until_reported(
    hass: HomeAssistant, unit: SimulatedUnit, datapoints: dict[str, int]
) -> None:
    """With no setpoint reported or restored, the default is shown."""
    await unit.key_exchange()
    await unit.push_all(datapoints)

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[ATTR_TEMPERATURE] == DEFAULT_SETPOINT


@pytest.mark.usefixtures("restored_setpoint")
@pytest.mark.parametrize(
    ("datapoints", "setpoint"),
    [
        pytest.param({}, RESTORED_SETPOINT, id="nothing_reported"),
        pytest.param(OFF_WITHOUT_SETPOINT, RESTORED_SETPOINT, id="off"),
        pytest.param(
            {**UNIT_DATAPOINTS, "adjust_temperature": 250}, 25.0, id="unit_reports"
        ),
    ],
)
async def test_setpoint_restored(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    datapoints: dict[str, int],
    setpoint: float,
) -> None:
    """The setpoint saved before a restart shows until the unit reports its own."""
    await unit.key_exchange()
    await unit.push_all(datapoints)

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[ATTR_TEMPERATURE] == setpoint


@pytest.mark.parametrize(
    ("units", "shown"),
    [
        pytest.param(METRIC_SYSTEM, 25.0, id="metric"),
        pytest.param(US_CUSTOMARY_SYSTEM, 77.0, id="us_customary"),
    ],
)
async def test_setpoint_saved_in_celsius(
    hass: HomeAssistant, unit: SimulatedUnit, units: UnitSystem, shown: float
) -> None:
    """The saved setpoint is the unit's °C, whatever unit the state shows."""
    hass.config.units = units
    await unit.key_exchange()
    await unit.push_all({**UNIT_DATAPOINTS, "adjust_temperature": 250})

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[ATTR_TEMPERATURE] == shown

    data = await async_mock_restore_state_shutdown_restart(hass)

    extra_data = data.last_states[CLIMATE_ENTITY_ID].extra_data
    assert extra_data is not None
    assert extra_data.as_dict() == {ATTR_TEMPERATURE: 25.0}
