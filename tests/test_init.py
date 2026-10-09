"""Tests for setting Fujitsu FGLair Local up and tearing it down."""

import asyncio
from unittest.mock import ANY, AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from . import SimulatedUnit
from .const import ECONOMY_ENTITY_ID, ENTRY_DATA, SETTINGS_SUPPORTED
from custom_components.fglair_local.const import CONF_DSN, DOMAIN
from custom_components.fglair_local.views import AylaLanView


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_register: AsyncMock
) -> None:
    """The entry loads, starts registering with the unit, then unloads."""
    assert init_integration.state is ConfigEntryState.LOADED
    mock_register.assert_awaited_once()

    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.NOT_LOADED


@pytest.mark.usefixtures("mock_register")
async def test_view_registered_once(hass: HomeAssistant) -> None:
    """Every unit shares one `/local_lan` view."""
    assert await async_setup_component(hass, "http", {})
    entries = [
        MockConfigEntry(
            domain=DOMAIN,
            unique_id=f"AC000W00000000{index}",
            data={
                **ENTRY_DATA,
                CONF_HOST: f"192.0.2.1{index}",
                CONF_DSN: f"AC000W00000000{index}",
            },
        )
        for index in (1, 2)
    ]

    with patch.object(
        hass.http, "register_view", wraps=hass.http.register_view
    ) as register_view:
        for entry in entries:
            entry.add_to_hass(hass)
            await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert [entry.state for entry in entries] == [ConfigEntryState.LOADED] * 2
    # `network` registers views of its own, so only count ours.
    assert [
        call.args[0]
        for call in register_view.call_args_list
        if isinstance(call.args[0], AylaLanView)
    ] == [ANY]


async def test_unload_stops_answering_the_unit(
    hass: HomeAssistant, init_integration: MockConfigEntry, unit: SimulatedUnit
) -> None:
    """After unload the view no longer accepts callbacks from the unit."""
    await unit.key_exchange()

    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    resp = await unit.client.get("/local_lan/commands.json")
    assert resp.status == 403


async def test_unload_detaches_before_platforms(
    hass: HomeAssistant, init_integration: MockConfigEntry, unit: SimulatedUnit
) -> None:
    """A value arriving while the platforms unload cannot add an entity to one."""
    await unit.key_exchange()
    await unit.push_all(SETTINGS_SUPPORTED)
    unload_platforms = hass.config_entries.async_unload_platforms
    statuses: list[int] = []

    async def push_then_unload(entry: ConfigEntry, platforms: list[Platform]) -> bool:
        statuses.append(await unit.push("economy_mode", 0))
        return await unload_platforms(entry, platforms)

    with patch.object(
        hass.config_entries, "async_unload_platforms", side_effect=push_then_unload
    ):
        await hass.config_entries.async_unload(init_integration.entry_id)
        await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.NOT_LOADED
    assert statuses == [403]
    assert hass.states.get(ECONOMY_ENTITY_ID) is None


@pytest.mark.parametrize("method", ["async_unload", "async_remove"])
async def test_unload_stops_registering(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
    mock_register: AsyncMock,
    method: str,
) -> None:
    """Unloading ends the registration loop and drops the unit from the server.

    The unit has no deregister endpoint and forgets clients that stop sending
    heartbeats, so cancelling the loop is how Home Assistant deregisters.
    """
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def register_forever() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    mock_register.side_effect = register_forever
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    await started.wait()
    unit = SimulatedUnit(await hass_client_no_auth())
    await unit.key_exchange()

    await getattr(hass.config_entries, method)(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert cancelled.is_set()
    resp = await unit.client.get("/local_lan/commands.json")
    assert resp.status == 403
