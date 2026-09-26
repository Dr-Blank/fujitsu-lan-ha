"""Tests of the unit's state: optimistic writes, read-back and availability."""

from collections.abc import Awaitable, Callable
import logging
from unittest.mock import MagicMock

from aioayla_lan import device as ayla_device
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_MODES,
    ATTR_SWING_HORIZONTAL_MODE,
    ATTR_SWING_MODE,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import SimulatedUnit, advance, read_resource, written
from .const import (
    CLIMATE_ENTITY_ID,
    DSN,
    ECONOMY_ENTITY_ID,
    REFRESH_ENTITY_ID,
    UNIT_DATAPOINTS,
)
from custom_components.fglair_local.const import DOMAIN
from custom_components.fglair_local.coordinator import (
    COMMAND_TIMEOUT,
    PROBE_INTERVAL,
    READ_BACK_DELAY,
    READ_BACK_MAX_DELAY,
    WATCHDOG_INTERVAL,
    FglairLocalDevice,
)

WATCHDOG = WATCHDOG_INTERVAL.total_seconds()
FIRMWARE = {"model_name": "TESTMODEL01", "mcu_fw_version": "0.0.1,:,:,:,"}
COORDINATOR_LOGGER = "custom_components.fglair_local.coordinator"


def reads(*names: str) -> list[str]:
    """Return the resources read commands for `names` ask for."""
    return [f"property.json?name={name}" for name in names]


def state_of(hass: HomeAssistant, entity_id: str) -> str:
    """Return an entity's state, which must exist."""
    state = hass.states.get(entity_id)
    assert state is not None
    return state.state


@pytest.fixture
def device(init_integration: MockConfigEntry) -> FglairLocalDevice:
    """Return the set-up unit's state holder."""
    return init_integration.runtime_data


async def test_write_is_optimistic_over_reported_value(
    hass: HomeAssistant, unit: SimulatedUnit, device: FglairLocalDevice
) -> None:
    """A write to a value the unit reported shows at once."""
    await unit.key_exchange()
    await unit.push("economy_mode", 0)

    device.set_property("economy_mode", 1)

    assert device.values["economy_mode"] == 1
    assert state_of(hass, ECONOMY_ENTITY_ID) == "on"
    # Settled, so no library timer outlives the test.
    await unit.fetch_write()


@pytest.mark.parametrize(
    "datapoints",
    [
        pytest.param({}, id="never_reported"),
        pytest.param({"economy_mode": 65535}, id="sentinel"),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_write_to_unreported_property_creates_nothing(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    device: FglairLocalDevice,
    datapoints: dict[str, int],
) -> None:
    """A write is no evidence the unit has the property, so no entity appears."""
    await unit.key_exchange()
    await unit.push_all(datapoints)

    device.set_property("economy_mode", 1)
    await hass.async_block_till_done()

    assert written(await unit.fetch_write()) == ("economy_mode", 1, "boolean")
    assert device.values.get("economy_mode") == datapoints.get("economy_mode")
    assert hass.states.get(ECONOMY_ENTITY_ID) is None
    assert hass.states.get("sensor.air_conditioner_raw_economy_mode") is None


async def test_batched_writes_notify_once(
    unit: SimulatedUnit, device: FglairLocalDevice
) -> None:
    """Writes made together update entities once, after the last."""
    await unit.key_exchange()
    await unit.push_all(UNIT_DATAPOINTS)
    listener = MagicMock()
    device.async_add_listener(listener)

    device.set_property("af_vertical_swing", 0, notify=False)
    listener.assert_not_called()
    device.set_property("af_vertical_direction", 2)

    listener.assert_called_once_with()
    assert [written(await unit.fetch_write()) for _ in range(2)] == [
        ("af_vertical_swing", 0, "boolean"),
        ("af_vertical_direction", 2, "integer"),
    ]


@pytest.mark.parametrize(
    ("name", "names"),
    [
        pytest.param("economy_mode", ["economy_mode"], id="alone"),
        pytest.param(
            "af_vertical_direction",
            ["af_vertical_direction", "af_vertical_swing"],
            id="vertical_direction",
        ),
        pytest.param(
            "af_horizontal_direction",
            ["af_horizontal_direction", "af_horizontal_swing"],
            id="horizontal_direction",
        ),
        pytest.param(
            "powerful_mode",
            [
                "adjust_temperature",
                "af_horizontal_direction",
                "af_horizontal_swing",
                "af_vertical_direction",
                "af_vertical_swing",
                "fan_speed",
                "powerful_mode",
            ],
            id="powerful_mode",
        ),
        pytest.param(
            "operation_mode",
            [
                "adjust_temperature",
                "af_horizontal_direction",
                "af_horizontal_swing",
                "af_vertical_direction",
                "af_vertical_swing",
                "fan_speed",
                "operation_mode",
                "powerful_mode",
            ],
            id="operation_mode",
        ),
    ],
)
async def test_write_is_read_back(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    device: FglairLocalDevice,
    freezer: FrozenDateTimeFactory,
    name: str,
    names: list[str],
) -> None:
    """The unit does not push what it was sent, so it is read back once it acks.

    So is whatever else the write may have changed.
    """
    await unit.key_exchange()
    await unit.drain()

    device.set_property(name, 1)
    command = await unit.fetch_command()
    assert written(command)[:2] == (name, 1)
    await advance(hass, freezer, READ_BACK_DELAY)
    assert await unit.drain() == []

    await unit.ack(command)
    await advance(hass, freezer, READ_BACK_DELAY - 1)
    assert await unit.drain() == []

    await advance(hass, freezer, 1)
    assert [read_resource(command) for command in await unit.drain()] == reads(*names)


@pytest.mark.parametrize(
    ("name", "value", "names"),
    [
        pytest.param(
            "operation_mode",
            6,
            [
                "adjust_temperature",
                "af_horizontal_direction",
                "af_horizontal_swing",
                "af_vertical_direction",
                "af_vertical_swing",
                "fan_speed",
                "powerful_mode",
            ],
            id="operation_mode",
        ),
        pytest.param(
            "powerful_mode",
            1,
            [
                "adjust_temperature",
                "af_horizontal_direction",
                "af_horizontal_swing",
                "af_vertical_direction",
                "af_vertical_swing",
                "fan_speed",
            ],
            id="powerful_mode",
        ),
        pytest.param(
            "af_vertical_direction", 2, ["af_vertical_swing"], id="vertical_direction"
        ),
        pytest.param(
            "af_horizontal_direction",
            2,
            ["af_horizontal_swing"],
            id="horizontal_direction",
        ),
    ],
)
async def test_remote_change_is_read_back(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    freezer: FrozenDateTimeFactory,
    name: str,
    value: int,
    names: list[str],
) -> None:
    """A change made at the unit, e.g. by the IR remote, is pushed on its own.

    Whatever else it may have changed is read, once.
    """
    await unit.key_exchange()
    await unit.push_all(UNIT_DATAPOINTS)
    await unit.drain()

    await unit.push(name, value)
    await advance(hass, freezer, READ_BACK_DELAY - 1)
    assert await unit.drain() == []

    await advance(hass, freezer, 1)
    assert [read_resource(command) for command in await unit.drain()] == reads(*names)
    await advance(hass, freezer, READ_BACK_DELAY)
    assert await unit.drain() == []


@pytest.mark.parametrize(
    ("before", "name", "value"),
    [
        pytest.param({"operation_mode": 3}, "operation_mode", 3, id="unchanged"),
        pytest.param({}, "operation_mode", 3, id="first_report"),
        pytest.param({"operation_mode": 65535}, "operation_mode", 3, id="sentinel"),
        pytest.param({"fan_speed": 1}, "fan_speed", 2, id="nothing_linked"),
    ],
)
async def test_pushed_value_not_read_back(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    freezer: FrozenDateTimeFactory,
    before: dict[str, int],
    name: str,
    value: int,
) -> None:
    """Only a change from a reported value can have side effects to read."""
    await unit.key_exchange()
    await unit.push_all(before)
    await unit.drain()

    await unit.push(name, value)
    await advance(hass, freezer, READ_BACK_DELAY)

    assert await unit.drain() == []


@pytest.mark.parametrize(
    ("before", "pushed", "attribute", "shown", "swing", "after"),
    [
        pytest.param(
            {"af_vertical_swing": 1, "af_vertical_direction": 2},
            {"af_vertical_direction": 1},
            ATTR_SWING_MODE,
            "on",
            "af_vertical_swing",
            "top",
            id="vertical_direction_only",
        ),
        pytest.param(
            {"af_vertical_swing": 1, "af_vertical_direction": 2},
            {"af_vertical_direction": 1, "af_vertical_swing": 0},
            ATTR_SWING_MODE,
            "top",
            "af_vertical_swing",
            "top",
            id="vertical_both",
        ),
        pytest.param(
            {"af_horizontal_swing": 1, "af_horizontal_direction": 2},
            {"af_horizontal_direction": 1},
            ATTR_SWING_HORIZONTAL_MODE,
            "on",
            "af_horizontal_swing",
            "left",
            id="horizontal_direction_only",
        ),
        pytest.param(
            {"af_horizontal_swing": 1, "af_horizontal_direction": 2},
            {"af_horizontal_direction": 1, "af_horizontal_swing": 0},
            ATTR_SWING_HORIZONTAL_MODE,
            "left",
            "af_horizontal_swing",
            "left",
            id="horizontal_both",
        ),
    ],
)
async def test_remote_position_stops_swing(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    freezer: FrozenDateTimeFactory,
    before: dict[str, int],
    pushed: dict[str, int],
    attribute: str,
    shown: str,
    swing: str,
    after: str,
) -> None:
    """Picking a position on the remote stops the swing, which some units never push.

    Reading the swing back shows the held position.
    """
    await unit.key_exchange()
    await unit.push_all({**UNIT_DATAPOINTS, **before})
    await unit.drain()

    await unit.push_all(pushed)
    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[attribute] == shown

    await advance(hass, freezer, READ_BACK_DELAY)
    assert [read_resource(command) for command in await unit.drain()] == reads(swing)
    await unit.push(swing, 0)

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.attributes[attribute] == after


async def _reject(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, unit: SimulatedUnit
) -> None:
    await unit.ack(await unit.fetch_command(), 500)


async def _leave_unacked(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, unit: SimulatedUnit
) -> None:
    await unit.fetch_command()
    await advance(hass, freezer, ayla_device.ACK_TIMEOUT)


async def _leave_uncollected(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, unit: SimulatedUnit
) -> None:
    await advance(hass, freezer, ayla_device.WRITE_TTL + 1)
    # Dropped rather than applied late.
    assert (await unit.fetch_command())["data"] == {}


@pytest.mark.parametrize(
    ("fail", "error"),
    [
        pytest.param(_reject, "ack_status 500", id="rejected"),
        pytest.param(_leave_unacked, "was not acknowledged", id="unacked"),
        pytest.param(_leave_uncollected, "was not collected", id="expired"),
    ],
)
async def test_failed_write_is_read_back(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    device: FglairLocalDevice,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    fail: Callable[
        [HomeAssistant, FrozenDateTimeFactory, SimulatedUnit], Awaitable[None]
    ],
    error: str,
) -> None:
    """A write the unit does not confirm is logged and undone, then read back."""
    await unit.key_exchange()
    await unit.push("economy_mode", 0)
    await unit.drain()

    device.set_property("economy_mode", 1)
    assert state_of(hass, ECONOMY_ENTITY_ID) == "on"

    await fail(hass, freezer, unit)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert (
        COORDINATOR_LOGGER,
        logging.WARNING,
        f"{DSN}: could not set economy_mode to 1: {DSN}: economy_mode {error}",
    ) in caplog.record_tuples
    # Shown as the unit last reported, even if the read-back goes unanswered.
    assert state_of(hass, ECONOMY_ENTITY_ID) == "off"

    await advance(hass, freezer, READ_BACK_DELAY)
    assert [read_resource(command) for command in await unit.drain()] == reads(
        "economy_mode"
    )
    await unit.push("economy_mode", 1)
    assert state_of(hass, ECONOMY_ENTITY_ID) == "on"


async def test_failed_write_keeps_newer_guess(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    device: FglairLocalDevice,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed write does not undo a newer write that is still in flight."""
    await unit.key_exchange()
    await unit.push("fan_speed", 0)
    await unit.drain()

    device.set_property("fan_speed", 1)
    first = await unit.fetch_command()
    device.set_property("fan_speed", 2)
    await unit.ack(first, 500)
    await hass.async_block_till_done()
    assert device.values["fan_speed"] == 2

    await _leave_unacked(hass, freezer, unit)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert device.values["fan_speed"] == 0


async def test_failed_write_restores_acked_value(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    device: FglairLocalDevice,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed write falls back to the last value the unit acked, not an older one."""
    await unit.key_exchange()
    await unit.push("economy_mode", 0)
    await unit.drain()

    device.set_property("economy_mode", 1)
    first = await unit.fetch_command()
    device.set_property("economy_mode", 0)
    await unit.ack(first)
    await hass.async_block_till_done()
    assert state_of(hass, ECONOMY_ENTITY_ID) == "off"

    await _leave_unacked(hass, freezer, unit)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert state_of(hass, ECONOMY_ENTITY_ID) == "on"


async def test_read_back_is_debounced(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    device: FglairLocalDevice,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Writes close together share one read-back, of each name once."""
    await unit.key_exchange()
    await unit.drain()

    device.set_property("min_heat", 1)
    await unit.fetch_write()
    await advance(hass, freezer, READ_BACK_DELAY / 2)
    device.set_property("min_heat", 0)
    device.set_property("economy_mode", 1)
    assert [written(await unit.fetch_write())[0] for _ in range(2)] == [
        "min_heat",
        "economy_mode",
    ]
    assert await unit.drain() == []

    # Past the first write's read-back time, but not the last one's.
    await advance(hass, freezer, READ_BACK_DELAY - 1)
    assert await unit.drain() == []

    await advance(hass, freezer, 1)
    assert [read_resource(command) for command in await unit.drain()] == reads(
        "economy_mode", "min_heat"
    )
    await advance(hass, freezer, READ_BACK_MAX_DELAY)
    assert await unit.drain() == []


async def test_read_back_is_not_postponed_forever(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    device: FglairLocalDevice,
    freezer: FrozenDateTimeFactory,
) -> None:
    """However often writes keep coming, the first is read back within a minute."""
    await unit.key_exchange()
    await unit.drain()
    interval = READ_BACK_DELAY / 2

    # Each write lands before the previous one's read-back is due.
    for _ in range(int(READ_BACK_MAX_DELAY // interval) - 1):
        device.set_property("min_heat", 1)
        await unit.fetch_write()
        await advance(hass, freezer, interval)
        assert await unit.drain() == []
    # Its own read-back would be due past the cap.
    device.set_property("min_heat", 0)
    await unit.fetch_write()

    await advance(hass, freezer, interval)
    assert [read_resource(command) for command in await unit.drain()] == reads(
        "min_heat"
    )


async def test_unavailable_while_unit_does_not_collect(
    hass: HomeAssistant, unit: SimulatedUnit, freezer: FrozenDateTimeFactory
) -> None:
    """A unit that leaves queued commands uncollected is shown unavailable.

    It is available again once it collects something.
    """
    await unit.key_exchange()
    assert state_of(hass, CLIMATE_ENTITY_ID) == STATE_UNKNOWN

    await advance(hass, freezer, COMMAND_TIMEOUT - 1)
    assert state_of(hass, CLIMATE_ENTITY_ID) == STATE_UNKNOWN

    await advance(hass, freezer, 1 + WATCHDOG)
    assert state_of(hass, CLIMATE_ENTITY_ID) == STATE_UNAVAILABLE
    assert state_of(hass, REFRESH_ENTITY_ID) == STATE_UNAVAILABLE

    await unit.fetch_command()
    await advance(hass, freezer, WATCHDOG)
    assert state_of(hass, CLIMATE_ENTITY_ID) == STATE_UNKNOWN


async def test_stall_counted_from_queueing(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    device: FglairLocalDevice,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After a quiet spell, the unit gets the full timeout to collect a write."""
    await unit.key_exchange()
    await unit.push_all(UNIT_DATAPOINTS)
    await unit.drain()
    await advance(hass, freezer, PROBE_INTERVAL - WATCHDOG)

    device.set_property("fan_speed", 1)
    await advance(hass, freezer, COMMAND_TIMEOUT - 1)
    assert state_of(hass, CLIMATE_ENTITY_ID) == "cool"

    await advance(hass, freezer, 1 + WATCHDOG)
    assert state_of(hass, CLIMATE_ENTITY_ID) == STATE_UNAVAILABLE

    assert written(await unit.fetch_write())[:2] == ("fan_speed", 1)
    await advance(hass, freezer, WATCHDOG)
    assert state_of(hass, CLIMATE_ENTITY_ID) == "cool"


async def test_idle_unit_is_probed(
    hass: HomeAssistant,
    unit: SimulatedUnit,
    device: FglairLocalDevice,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A unit that has been quiet for a while is asked for the room temperature.

    One that never answers is shown unavailable.
    """
    await unit.key_exchange()
    await unit.push_all(UNIT_DATAPOINTS)
    await unit.drain()

    await advance(hass, freezer, PROBE_INTERVAL - 1)
    assert not device.lan.pending

    await advance(hass, freezer, 1 + WATCHDOG)
    assert device.lan.pending
    await advance(hass, freezer, COMMAND_TIMEOUT + WATCHDOG)
    assert state_of(hass, CLIMATE_ENTITY_ID) == STATE_UNAVAILABLE

    assert [read_resource(command) for command in await unit.drain()] == reads(
        "display_temperature"
    )


async def test_session_drop_forgets_changeable_values(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    unit: SimulatedUnit,
    device: FglairLocalDevice,
    device_registry: dr.DeviceRegistry,
) -> None:
    """The unit may change while unreachable; only what is fixed for it is kept."""
    await unit.key_exchange()
    await unit.push_all({**UNIT_DATAPOINTS, **FIRMWARE})

    # What the registration loop does once the unit stops answering; driving
    # the loop itself would tie the test to its timing.
    device.lan._drop_session()  # noqa: SLF001

    assert device.values == {
        "device_capabilities": UNIT_DATAPOINTS["device_capabilities"],
        **FIRMWARE,
    }
    assert state_of(hass, CLIMATE_ENTITY_ID) == STATE_UNAVAILABLE

    await unit.key_exchange()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state is not None
    assert state.state == STATE_UNKNOWN
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] is None
    assert state.attributes[ATTR_SWING_MODE] is None
    assert state.attributes[ATTR_HVAC_MODES] == [
        "off",
        "cool",
        "dry",
        "fan_only",
        "heat",
        "heat_cool",
    ]
    assert state_of(hass, ECONOMY_ENTITY_ID) == STATE_UNKNOWN
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, DSN), init_integration.entry_id
    )
    assert device_entry is not None
    assert device_entry.model == FIRMWARE["model_name"]


async def test_detach_stops_updates(
    unit: SimulatedUnit, device: FglairLocalDevice
) -> None:
    """A detached unit's values are refused and reach no listener."""
    await unit.key_exchange()
    listener = MagicMock()
    remove = device.async_add_listener(listener)

    device.detach()
    # Entities unsubscribe after the entry detached the unit.
    remove()

    assert await unit.push("outdoor_temperature", 8700) == 403
    listener.assert_not_called()
