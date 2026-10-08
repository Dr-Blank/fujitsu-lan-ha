"""Tests for the Fujitsu FGLair Local diagnostics."""

import json

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from . import SimulatedUnit, advance, read_resource
from .const import CALLBACK_HOST, DSN, HOST, LANIP_KEY, UNIT_DATAPOINTS
from custom_components.fglair_local.coordinator import STATUS_POLL_INTERVAL

# Shaped like what an AP-WF3E reports while off, shortened.
STATUS = {"op_status": 0, "monitor1": "65535,65535,0,0,:,65535"}


@pytest.fixture(autouse=True)
async def setup_diagnostics(hass: HomeAssistant) -> None:
    """Register the download view before the test client freezes the router."""
    assert await async_setup_component(hass, "diagnostics", {})


async def test_diagnostics(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    unit: SimulatedUnit,
    snapshot: SnapshotAssertion,
) -> None:
    """The dump carries the session state and values, but not the key or addresses."""
    await unit.key_exchange()
    await unit.push_all(UNIT_DATAPOINTS)
    freezer.tick(5)

    assert (
        await get_diagnostics_for_config_entry(hass, hass_client, init_integration)
        == snapshot
    )


async def test_diagnostics_before_unit_dials_in(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """With no session yet, nothing is known and no age is made up."""
    assert (
        await get_diagnostics_for_config_entry(hass, hass_client, init_integration)
        == snapshot
    )


async def test_diagnostics_hold_no_secrets(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    unit: SimulatedUnit,
) -> None:
    """Neither the key nor what identifies or locates the unit is anywhere in the dump."""
    await unit.key_exchange()
    await unit.push_all(UNIT_DATAPOINTS)

    dump = json.dumps(
        await get_diagnostics_for_config_entry(hass, hass_client, init_integration)
    )

    for secret in (LANIP_KEY, DSN, HOST, CALLBACK_HOST):
        assert secret not in dump


async def test_diagnostics_show_polled_status(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    unit: SimulatedUnit,
) -> None:
    """Status the unit gives only when asked shows once polled and answered."""
    await unit.key_exchange()
    await unit.drain()

    await advance(hass, freezer, STATUS_POLL_INTERVAL)
    assert [read_resource(command) for command in await unit.drain()] == [
        f"property.json?name={name}" for name in STATUS
    ]
    await unit.push_all(STATUS)

    assert init_integration.runtime_data.values == STATUS
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )
    assert diagnostics["values"] == STATUS
