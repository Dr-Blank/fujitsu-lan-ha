"""End-to-end tests of the climate entity, driven by a simulated unit."""

import pytest

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
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
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.translation import async_get_translations

from . import SimulatedUnit, read_resource, written
from .const import CLIMATE_ENTITY_ID, UNIT_DATAPOINTS
from custom_components.fglair_local.const import DOMAIN
from custom_components.fglair_local.properties import (
    EXTRA_PROPERTIES,
    HORIZONTAL_POSITIONS,
    NUMBERED_POSITIONS,
    PRIME_PROPERTIES,
    VERTICAL_POSITIONS,
)

PRIMED = (*PRIME_PROPERTIES, *EXTRA_PROPERTIES)
# Heat pump with both swing axes, from UNIT_DATAPOINTS.
CAPABILITIES = {"device_capabilities": 229375}
SWING_FEATURES = (
    ClimateEntityFeature.SWING_MODE | ClimateEntityFeature.SWING_HORIZONTAL_MODE
)
NO_SWING = ClimateEntityFeature(0)
VERTICAL_MODES = ["on", "off", "top", "upper_middle", "lower_middle", "bottom"]
HORIZONTAL_MODES = [
    "on",
    "off",
    "left",
    "left_center",
    "center",
    "right_center",
    "right",
]


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
    assert state.attributes[ATTR_SWING_HORIZONTAL_MODE] == "right"


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
        (SERVICE_SET_SWING_MODE, {ATTR_SWING_MODE: "bottom"}),
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
    assert state.attributes[ATTR_SWING_MODE] == "bottom"
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


@pytest.mark.parametrize(
    ("datapoints", "swing_modes", "swing_horizontal_modes", "features"),
    [
        pytest.param(
            {"device_capabilities": 0b1100_0000_0001},
            VERTICAL_MODES,
            HORIZONTAL_MODES,
            SWING_FEATURES,
            id="both_axes",
        ),
        pytest.param(
            {"device_capabilities": 0b0100_0000_0001},
            VERTICAL_MODES,
            None,
            ClimateEntityFeature.SWING_MODE,
            id="vertical_only",
        ),
        pytest.param(
            {"device_capabilities": 0b1000_0000_0001},
            None,
            HORIZONTAL_MODES,
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
            VERTICAL_MODES,
            None,
            ClimateEntityFeature.SWING_MODE,
            id="unknown_vertical_reported",
        ),
        pytest.param(
            {"af_horizontal_swing": 1},
            None,
            HORIZONTAL_MODES,
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
            VERTICAL_MODES,
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
    ("datapoints", "swing_modes"),
    [
        pytest.param({}, VERTICAL_MODES, id="no_count"),
        pytest.param({"af_vertical_num_dir": 4}, VERTICAL_MODES, id="four"),
        pytest.param(
            {"af_vertical_num_dir": 6},
            ["on", "off", *(f"position_{n}" for n in range(1, 7))],
            id="six",
        ),
        pytest.param(
            {"af_vertical_num_dir": 8},
            ["on", "off", *(f"position_{n}" for n in range(1, 9))],
            id="eight",
        ),
        pytest.param(
            {"af_vertical_num_dir": 3},
            ["on", "off", "position_1", "position_2", "position_3"],
            id="three",
        ),
        pytest.param({"af_vertical_num_dir": 1}, ["on", "off", "position_1"], id="one"),
        pytest.param({"af_vertical_num_dir": 0}, VERTICAL_MODES, id="zero"),
        pytest.param({"af_vertical_num_dir": -1}, VERTICAL_MODES, id="negative"),
        pytest.param({"af_vertical_num_dir": 9}, VERTICAL_MODES, id="too_many"),
        pytest.param({"af_vertical_num_dir": 65535}, VERTICAL_MODES, id="sentinel"),
        pytest.param(
            # The horizontal count is not the number of positions.
            {"af_horizontal_num_dir": 2},
            VERTICAL_MODES,
            id="horizontal_count_ignored",
        ),
    ],
)
async def test_positions_follow_count(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    datapoints: dict[str, int],
    swing_modes: list[str],
) -> None:
    """Vertical positions are numbered for a plausible count other than 4.

    Horizontal ones never follow a count.
    """
    await unit.key_exchange()
    await unit.push_all({**CAPABILITIES, **datapoints})

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[ATTR_SWING_MODES] == swing_modes
    assert state.attributes[ATTR_SWING_HORIZONTAL_MODES] == HORIZONTAL_MODES


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
            "upper_middle",
            "center",
            id="held",
        ),
        pytest.param(
            {
                "af_vertical_swing": 0,
                "af_vertical_direction": 4,
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 5,
            },
            "bottom",
            "right",
            id="held_at_last",
        ),
        pytest.param(
            {
                "af_vertical_swing": 0,
                "af_vertical_direction": 4,
                "af_vertical_num_dir": 3,
                "af_horizontal_swing": 0,
                "af_horizontal_direction": 5,
                "af_horizontal_num_dir": 2,
            },
            "off",
            "right",
            id="beyond_count",
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
            "bottom",
            "on",
            id="held_named_with_count",
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
    await unit.push_all({**CAPABILITIES, **datapoints})

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
            "top",
            id="vertical_off",
        ),
        pytest.param(
            {"af_vertical_swing": 1},
            SERVICE_SET_SWING_MODE,
            {ATTR_SWING_MODE: "lower_middle"},
            [
                ("af_vertical_swing", 0, "boolean"),
                ("af_vertical_direction", 3, "integer"),
            ],
            ATTR_SWING_MODE,
            "lower_middle",
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
            "right",
            id="horizontal_off",
        ),
        pytest.param(
            {"af_horizontal_swing": 1},
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: "left_center"},
            [
                ("af_horizontal_swing", 0, "boolean"),
                ("af_horizontal_direction", 2, "integer"),
            ],
            ATTR_SWING_HORIZONTAL_MODE,
            "left_center",
            id="horizontal_position",
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
            {ATTR_SWING_MODE: "left"},
            id="horizontal_position_on_vertical",
        ),
        pytest.param(
            SERVICE_SET_SWING_HORIZONTAL_MODE,
            {ATTR_SWING_HORIZONTAL_MODE: "top"},
            id="vertical_position_on_horizontal",
        ),
        pytest.param(
            SERVICE_SET_SWING_MODE, {ATTR_SWING_MODE: "position_4"}, id="beyond_count"
        ),
        pytest.param(
            SERVICE_SET_SWING_MODE,
            {ATTR_SWING_MODE: "top"},
            id="named_position_on_numbered",
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


async def test_count_read_before_direction(unit: SimulatedUnit) -> None:
    """A direction past 4 reads as off until the count says it exists."""
    await unit.key_exchange()

    resources = [read_resource(command) for command in await unit.drain()]

    assert resources.index("property.json?name=af_vertical_num_dir") < (
        resources.index("property.json?name=af_vertical_direction")
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
        *NUMBERED_POSITIONS[:6],
    ]


@pytest.mark.parametrize(
    ("attribute", "positions"),
    [
        pytest.param(ATTR_SWING_MODE, VERTICAL_POSITIONS, id="vertical"),
        pytest.param(ATTR_SWING_MODE, NUMBERED_POSITIONS, id="numbered"),
        pytest.param(ATTR_SWING_HORIZONTAL_MODE, HORIZONTAL_POSITIONS, id="horizontal"),
    ],
)
async def test_positions_are_translated(
    hass: HomeAssistant, attribute: str, positions: tuple[str, ...]
) -> None:
    """Every louvre position has a name to show."""
    translations = await async_get_translations(hass, "en", "entity", [DOMAIN])

    prefix = (
        f"component.{DOMAIN}.entity.climate.air_conditioner"
        f".state_attributes.{attribute}.state"
    )
    assert {f"{prefix}.{position}" for position in positions} <= translations.keys()


@pytest.mark.parametrize(
    ("name", "value", "attribute"),
    [
        pytest.param("display_temperature", 65535, ATTR_CURRENT_TEMPERATURE, id="room"),
        pytest.param("adjust_temperature", 65535, ATTR_TEMPERATURE, id="setpoint"),
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
