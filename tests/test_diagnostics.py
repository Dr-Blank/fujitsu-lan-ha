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

from . import SimulatedUnit
from .const import CALLBACK_HOST, DSN, HOST, LANIP_KEY, UNIT_DATAPOINTS


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
