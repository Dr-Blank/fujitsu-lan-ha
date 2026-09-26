"""Tests for the Fujitsu FGLair Local diagnostics."""

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
from .const import UNIT_DATAPOINTS


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
