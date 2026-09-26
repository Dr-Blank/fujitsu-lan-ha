"""Fixtures for the Fujitsu FGLair Local tests."""

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from aioayla_lan import AylaLanDevice, CloudDevice, LanKey
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import SimulatedUnit
from .const import (
    CALLBACK_HOST,
    CLOUD_HOST,
    DSN,
    ENTRY_DATA,
    LANIP_KEY,
    LANIP_KEY_ID,
    PRODUCT_NAME,
)
from custom_components.fglair_local import PLATFORMS
from custom_components.fglair_local.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Create every entity enabled, including those disabled by default."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
        new_callable=PropertyMock,
    ):
        yield


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for the unit."""
    return MockConfigEntry(domain=DOMAIN, title=DSN, unique_id=DSN, data=ENTRY_DATA)


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Stop a created entry from setting itself up."""
    with patch(
        "custom_components.fglair_local.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def mock_cloud_cls() -> Generator[MagicMock]:
    """Patch the FGLair cloud client class, whose account lists one unit."""
    with patch(
        "custom_components.fglair_local.config_flow.AylaCloud", autospec=True
    ) as mock_cls:
        cloud = mock_cls.return_value
        cloud.list_devices.return_value = [
            CloudDevice(
                dsn=DSN, product_name=PRODUCT_NAME, lan_ip=CLOUD_HOST, lan_enabled=True
            )
        ]
        cloud.get_lan_key.return_value = LanKey(LANIP_KEY, LANIP_KEY_ID)
        yield mock_cls


@pytest.fixture
def mock_cloud(mock_cloud_cls: MagicMock) -> MagicMock:
    """Return the FGLair cloud client the flow signs in with."""
    return mock_cloud_cls.return_value


@pytest.fixture
def mock_fetch_dsn() -> Generator[AsyncMock]:
    """Return the unit's DSN when it is probed on the LAN."""
    with patch(
        "custom_components.fglair_local.config_flow.fetch_dsn", return_value=DSN
    ) as mock_fetch:
        yield mock_fetch


@pytest.fixture
def mock_lan_register() -> Generator[AsyncMock]:
    """Let the unit accept the registration and callback address.

    Set `side_effect` on the returned mock to refuse it instead.
    """
    with patch(
        "custom_components.fglair_local.config_flow.AylaLanDevice.register",
        autospec=True,
    ) as mock_lan_register:
        yield mock_lan_register


@pytest.fixture
def mock_wait_verified() -> Generator[AsyncMock]:
    """Let the unit dial back and authenticate with the key.

    Set `side_effect` on the returned mock to fail the check instead.
    """
    outcome = AsyncMock(return_value=LANIP_KEY_ID)

    async def wait_verified(device: AylaLanDevice) -> int:
        # A real unit takes a while, so the flow shows its progress step.
        await asyncio.sleep(0)
        return await outcome(device)

    with patch(
        "custom_components.fglair_local.config_flow.AylaLanDevice.wait_verified",
        autospec=True,
        side_effect=wait_verified,
    ):
        yield outcome


@pytest.fixture
def mock_source_ip() -> Generator[AsyncMock]:
    """Return the address Home Assistant is reached at from the unit."""
    with patch(
        "custom_components.fglair_local.config_flow.async_get_source_ip",
        return_value=CALLBACK_HOST,
    ) as mock_source_ip:
        yield mock_source_ip


@pytest.fixture
def mock_register() -> Generator[AsyncMock]:
    """Keep the registration loop off the network."""
    with patch(
        "aioayla_lan.device.AylaLanDevice.run", new_callable=AsyncMock
    ) as mock_run:
        yield mock_run


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to set up."""
    return PLATFORMS


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_register: AsyncMock,
    platforms: list[Platform],
) -> MockConfigEntry:
    """Set the integration up and return its entry."""
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.fglair_local.PLATFORMS", platforms):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    return mock_config_entry


@pytest.fixture
async def unit(
    init_integration: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> SimulatedUnit:
    """Return a simulated unit connected to the integration's HTTP view."""
    return SimulatedUnit(await hass_client_no_auth())


@pytest.fixture(name="snapshot")
def snapshot_fixture(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Serialize registry entries without their volatile ids and timestamps."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)
