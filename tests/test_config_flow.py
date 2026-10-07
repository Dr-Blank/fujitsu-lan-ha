"""Tests for the Fujitsu FGLair Local config flow."""

import asyncio
from collections.abc import Awaitable, Callable, Generator
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from aioayla_lan import (
    AylaLanDevice,
    AylaLanError,
    CallbackRejectedError,
    CannotConnectError,
    CloudAuthError,
    CloudDevice,
    CloudError,
    InvalidKeyError,
    LanKey,
    NoCallbackError,
    SessionCrypto,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.http import ApiConfig
from homeassistant.config_entries import (
    SOURCE_DHCP,
    SOURCE_USER,
    ConfigEntryState,
    ConfigFlowResult,
)
from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD, CONF_REGION
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.setup import async_setup_component

from . import RANDOM_1, TIME_1, read_resource
from .const import (
    CALLBACK_HOST,
    CALLBACK_PORT,
    CLOUD_HOST,
    DSN,
    ENTRY_DATA,
    HOST,
    LANIP_KEY,
    LANIP_KEY_ID,
    PRODUCT_NAME,
)
from custom_components.fglair_local.const import (
    CONF_CALLBACK_HOST,
    CONF_CALLBACK_PORT,
    CONF_DSN,
    CONF_LANIP_KEY,
    CONF_LANIP_KEY_ID,
    DOMAIN,
    FGLAIR_APPS,
)
from custom_components.fglair_local.views import async_get_server

OTHER_DSN = "AC000W000000002"
THIRD_DSN = "AC000W000000003"
LOCAL_HOST = "192.0.2.11"
DISCOVERED_HOST = "192.0.2.20"
# The Docker host's LAN address, which the unit can reach but HA cannot detect.
HOST_LAN_IP = "192.0.2.3"
EMAIL = "user@example.com"
PASSWORD = "fake-password"
NEW_LANIP_KEY = "fedcba9876543210fedcba9876543210"
NEW_LANIP_KEY_ID = 5678

CLOUD_INPUT = {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD, CONF_REGION: "us"}
LOCAL_INPUT = {CONF_HOST: LOCAL_HOST, CONF_LANIP_KEY: LANIP_KEY}

DISCOVERY = DhcpServiceInfo(
    ip=DISCOVERED_HOST, hostname="ap-wf0000000001", macaddress="00005e005301"
)

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


@pytest.fixture
def mock_unload_entry() -> Generator[AsyncMock]:
    """Let a set-up entry unload without a running unit."""
    with patch(
        "custom_components.fglair_local.async_unload_entry", return_value=True
    ) as mock_unload:
        yield mock_unload


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_unload_entry: AsyncMock,
) -> MockConfigEntry:
    """Return the unit's entry, set up."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry


def _entry_data(host: str, **overrides: Any) -> dict[str, Any]:
    return {
        CONF_HOST: host,
        CONF_DSN: DSN,
        CONF_LANIP_KEY: LANIP_KEY,
        CONF_LANIP_KEY_ID: LANIP_KEY_ID,
        CONF_CALLBACK_HOST: CALLBACK_HOST,
        CONF_CALLBACK_PORT: 8123,
        **overrides,
    }


def _cloud_device(
    dsn: str = DSN,
    product_name: str | None = PRODUCT_NAME,
    lan_ip: str | None = CLOUD_HOST,
    lan_enabled: bool = True,
) -> CloudDevice:
    return CloudDevice(
        dsn=dsn, product_name=product_name, lan_ip=lan_ip, lan_enabled=lan_enabled
    )


def _suggested_values(result: ConfigFlowResult) -> dict[str, Any]:
    return {
        str(key): (key.description or {}).get("suggested_value")
        for key in result["data_schema"].schema
    }


def _callback_status(hass: HomeAssistant) -> int:
    """Return how the shared server answers a callback from the flow's unit."""
    return async_get_server(hass).handle(LOCAL_HOST, "GET", "commands.json", b"")[0]


async def _start(hass: HomeAssistant, menu_option: str) -> ConfigFlowResult:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": menu_option}
    )


async def _finish_verify(
    hass: HomeAssistant, result: ConfigFlowResult
) -> ConfigFlowResult:
    """Let the unit dial back, then take the step that follows the check."""
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert result["step_id"] == "verify"
    assert result["progress_action"] == "verify"
    await hass.async_block_till_done()
    return await hass.config_entries.flow.async_configure(result["flow_id"])


async def test_user_menu(hass: HomeAssistant) -> None:
    """The user picks between the cloud sign-in and a known LAN key."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "user"
    assert result["menu_options"] == ["cloud", "local"]


@pytest.mark.usefixtures("mock_lan_register", "mock_wait_verified")
async def test_cloud_flow(
    hass: HomeAssistant,
    mock_cloud_cls: MagicMock,
    mock_cloud: MagicMock,
    mock_source_ip: AsyncMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Signing in fetches the unit's key and address, then checks them."""
    result = await _start(hass, "cloud")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "cloud"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CLOUD_INPUT
    )
    assert result["description_placeholders"] == {
        "host": CLOUD_HOST,
        "callback": f"{CALLBACK_HOST}:8123",
    }
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == PRODUCT_NAME
    assert result["data"] == _entry_data(CLOUD_HOST)
    assert result["result"].unique_id == DSN
    mock_cloud_cls.assert_called_once_with(
        async_get_clientsession(hass), *FGLAIR_APPS["us"], "us"
    )
    mock_cloud.sign_in.assert_awaited_once_with(EMAIL, PASSWORD)
    mock_cloud.get_lan_key.assert_awaited_once_with(DSN)
    mock_source_ip.assert_awaited_once_with(hass, target_ip=CLOUD_HOST)
    mock_setup_entry.assert_awaited_once()


@pytest.mark.parametrize(
    ("country", "region"),
    [
        pytest.param("US", "us", id="americas"),
        pytest.param("AU", "us", id="oceania"),
        pytest.param(None, "us", id="unset"),
        pytest.param("DE", "eu", id="europe"),
        pytest.param("GB", "eu", id="united_kingdom"),
        pytest.param("CN", "cn", id="china"),
    ],
)
async def test_cloud_default_region(
    hass: HomeAssistant, country: str | None, region: str
) -> None:
    """The region is preselected from the country Home Assistant is set to."""
    hass.config.country = country

    result = await _start(hass, "cloud")

    assert (
        next(
            key for key in result["data_schema"].schema if key == CONF_REGION
        ).default()
        == region
    )


@pytest.mark.usefixtures(
    "mock_cloud", "mock_source_ip", "mock_lan_register", "mock_wait_verified"
)
@pytest.mark.parametrize("region", ["eu", "cn"])
async def test_cloud_region(
    hass: HomeAssistant, mock_cloud_cls: MagicMock, region: str
) -> None:
    """The client is built with the chosen region's app credentials."""
    result = await _start(hass, "cloud")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CLOUD_INPUT, CONF_REGION: region}
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    mock_cloud_cls.assert_called_once_with(
        async_get_clientsession(hass), *FGLAIR_APPS[region], region
    )


@pytest.mark.usefixtures("mock_source_ip", "mock_lan_register", "mock_wait_verified")
@pytest.mark.parametrize(
    ("method", "exception", "error"),
    [
        pytest.param("sign_in", CloudAuthError, "invalid_auth", id="invalid_auth"),
        pytest.param("sign_in", CloudError, "cloud_error", id="sign_in_failed"),
        pytest.param("list_devices", CloudError, "cloud_error", id="list_failed"),
    ],
)
async def test_cloud_errors(
    hass: HomeAssistant,
    mock_cloud: MagicMock,
    method: str,
    exception: type[Exception],
    error: str,
) -> None:
    """A failed sign-in keeps the typed values, and a retry goes through."""
    result = await _start(hass, "cloud")
    getattr(mock_cloud, method).side_effect = exception

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CLOUD_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "cloud"
    assert result["errors"] == {"base": error}
    assert _suggested_values(result) == CLOUD_INPUT

    getattr(mock_cloud, method).side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CLOUD_INPUT
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_source_ip", "mock_lan_register", "mock_wait_verified")
async def test_cloud_pick_device(
    hass: HomeAssistant, mock_cloud: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """Units already set up are left out when choosing among several."""
    mock_config_entry.add_to_hass(hass)
    mock_cloud.list_devices.return_value = [
        _cloud_device(),
        _cloud_device(OTHER_DSN, "Bedroom", "192.0.2.12"),
        _cloud_device(THIRD_DSN, None, None),
    ]
    result = await _start(hass, "cloud")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CLOUD_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pick_device"
    assert result["data_schema"].schema["device"].config["options"] == [
        {"value": OTHER_DSN, "label": "Bedroom (192.0.2.12)"},
        {"value": THIRD_DSN, "label": f"{THIRD_DSN} ({THIRD_DSN})"},
    ]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device": OTHER_DSN}
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Bedroom"
    assert result["data"] == _entry_data("192.0.2.12", **{CONF_DSN: OTHER_DSN})
    mock_cloud.get_lan_key.assert_awaited_once_with(OTHER_DSN)


async def test_cloud_pick_device_added_meanwhile(
    hass: HomeAssistant, mock_cloud: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    """A unit set up by another flow while the list was shown is not added twice."""
    mock_cloud.list_devices.return_value = [
        _cloud_device(),
        _cloud_device(OTHER_DSN, "Bedroom", "192.0.2.12"),
    ]
    result = await _start(hass, "cloud")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CLOUD_INPUT
    )
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device": DSN}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_cloud.get_lan_key.assert_not_awaited()


@pytest.mark.parametrize(
    ("devices", "reason"),
    [
        pytest.param([], "no_devices", id="empty_account"),
        pytest.param([_cloud_device()], "no_devices", id="all_configured"),
        pytest.param(
            [_cloud_device(OTHER_DSN, lan_enabled=False)],
            "lan_disabled",
            id="lan_disabled",
        ),
        pytest.param(
            [_cloud_device(OTHER_DSN, lan_ip=HOST)],
            "already_configured",
            id="address_configured",
        ),
    ],
)
async def test_cloud_abort(
    hass: HomeAssistant,
    mock_cloud: MagicMock,
    mock_config_entry: MockConfigEntry,
    devices: list[CloudDevice],
    reason: str,
) -> None:
    """The flow ends when the account has no unit that can be added."""
    mock_config_entry.add_to_hass(hass)
    mock_cloud.list_devices.return_value = devices
    result = await _start(hass, "cloud")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CLOUD_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason


async def test_cloud_lan_key_error(hass: HomeAssistant, mock_cloud: MagicMock) -> None:
    """A unit whose LAN key cannot be fetched ends the flow."""
    mock_cloud.get_lan_key.side_effect = CloudError
    result = await _start(hass, "cloud")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CLOUD_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cloud_error"


@pytest.mark.usefixtures("mock_source_ip", "mock_lan_register", "mock_wait_verified")
async def test_cloud_without_address(
    hass: HomeAssistant, mock_cloud: MagicMock, mock_fetch_dsn: AsyncMock
) -> None:
    """When the cloud does not know the address, it is asked for with the key kept."""
    mock_cloud.list_devices.return_value = [_cloud_device(lan_ip=None)]
    result = await _start(hass, "cloud")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CLOUD_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "local"
    assert result["errors"] == {"base": "no_address"}
    assert _suggested_values(result) == {CONF_HOST: None, CONF_LANIP_KEY: LANIP_KEY}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], LOCAL_INPUT
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == PRODUCT_NAME
    assert result["data"] == _entry_data(LOCAL_HOST)
    mock_fetch_dsn.assert_awaited_once_with(async_get_clientsession(hass), LOCAL_HOST)


@pytest.mark.usefixtures("mock_source_ip", "mock_lan_register", "mock_wait_verified")
async def test_local_flow(
    hass: HomeAssistant, mock_fetch_dsn: AsyncMock, mock_setup_entry: AsyncMock
) -> None:
    """A unit added with a kept LAN key is stored under the DSN it reports."""
    result = await _start(hass, "local")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "local"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: f" {LOCAL_HOST} ", CONF_LANIP_KEY: f" {LANIP_KEY}\n"},
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == DSN
    assert result["data"] == _entry_data(LOCAL_HOST)
    assert result["result"].unique_id == DSN
    mock_fetch_dsn.assert_awaited_once_with(async_get_clientsession(hass), LOCAL_HOST)
    mock_setup_entry.assert_awaited_once()


@pytest.mark.usefixtures("mock_source_ip", "mock_lan_register", "mock_wait_verified")
@pytest.mark.parametrize(
    ("user_input", "fetch_error", "errors", "probes"),
    [
        pytest.param(
            {**LOCAL_INPUT, CONF_HOST: "aircon.local"},
            None,
            {CONF_HOST: "invalid_ip"},
            0,
            id="hostname",
        ),
        pytest.param(
            {**LOCAL_INPUT, CONF_LANIP_KEY: " \n"},
            None,
            {CONF_LANIP_KEY: "key_required"},
            0,
            id="blank_key",
        ),
        pytest.param(
            LOCAL_INPUT,
            CannotConnectError,
            {"base": "cannot_connect"},
            1,
            id="no_answer",
        ),
        pytest.param(LOCAL_INPUT, AylaLanError, {"base": "not_ayla"}, 1, id="not_ayla"),
    ],
)
async def test_local_errors(
    hass: HomeAssistant,
    mock_fetch_dsn: AsyncMock,
    user_input: dict[str, str],
    fetch_error: type[Exception] | None,
    errors: dict[str, str],
    probes: int,
) -> None:
    """Bad input is refused with the typed values kept, then the flow recovers.

    Input that is wrong on its face is refused without probing the unit.
    """
    mock_fetch_dsn.side_effect = fetch_error
    result = await _start(hass, "local")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "local"
    assert result["errors"] == errors
    assert _suggested_values(result) == user_input
    assert mock_fetch_dsn.await_count == probes

    mock_fetch_dsn.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], LOCAL_INPUT
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == _entry_data(LOCAL_HOST)


@pytest.mark.usefixtures("mock_source_ip", "mock_lan_register", "mock_wait_verified")
async def test_local_input_is_trimmed(
    hass: HomeAssistant, mock_fetch_dsn: AsyncMock
) -> None:
    """Whitespace picked up when pasting the address or key is not stored."""
    result = await _start(hass, "local")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: f" {LOCAL_HOST} ", CONF_LANIP_KEY: f"{LANIP_KEY}\n"},
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == _entry_data(LOCAL_HOST)
    mock_fetch_dsn.assert_awaited_once_with(async_get_clientsession(hass), LOCAL_HOST)


@pytest.mark.parametrize(
    ("host", "dsn"),
    [
        pytest.param(HOST, OTHER_DSN, id="address"),
        pytest.param(LOCAL_HOST, DSN, id="dsn"),
    ],
)
async def test_local_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_fetch_dsn: AsyncMock,
    host: str,
    dsn: str,
) -> None:
    """Callbacks are routed by address, so neither the address nor the DSN is reused."""
    mock_config_entry.add_to_hass(hass)
    mock_fetch_dsn.return_value = dsn
    result = await _start(hass, "local")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**LOCAL_INPUT, CONF_HOST: host}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("mock_fetch_dsn", "mock_source_ip", "mock_wait_verified")
async def test_register_callback_rejected(
    hass: HomeAssistant, mock_lan_register: AsyncMock
) -> None:
    """A refused callback address is asked for again at once, without the spinner."""
    mock_lan_register.side_effect = CallbackRejectedError
    result = await _start(hass, "local")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], LOCAL_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "callback"
    assert result["errors"] == {"base": "callback_rejected"}
    assert result["description_placeholders"] == {
        "host": LOCAL_HOST,
        "callback": f"{CALLBACK_HOST}:8123",
    }
    assert _suggested_values(result) == {
        CONF_CALLBACK_HOST: CALLBACK_HOST,
        CONF_CALLBACK_PORT: 8123,
    }
    assert _callback_status(hass) == 403

    mock_lan_register.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CALLBACK_HOST: HOST_LAN_IP, CONF_CALLBACK_PORT: 8124}
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == _entry_data(
        LOCAL_HOST, **{CONF_CALLBACK_HOST: HOST_LAN_IP, CONF_CALLBACK_PORT: 8124}
    )
    assert mock_lan_register.await_count == 2


@pytest.mark.usefixtures("mock_fetch_dsn", "mock_source_ip", "mock_wait_verified")
async def test_register_cannot_connect(
    hass: HomeAssistant, mock_lan_register: AsyncMock
) -> None:
    """A unit that does not answer the registration returns to the address form."""
    mock_lan_register.side_effect = CannotConnectError
    result = await _start(hass, "local")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], LOCAL_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "local"
    assert result["errors"] == {"base": "cannot_connect"}
    assert _suggested_values(result) == LOCAL_INPUT
    assert _callback_status(hass) == 403

    mock_lan_register.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], LOCAL_INPUT
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == _entry_data(LOCAL_HOST)
    assert mock_lan_register.await_count == 2


@pytest.mark.usefixtures("mock_fetch_dsn", "mock_source_ip", "mock_wait_verified")
@pytest.mark.parametrize(
    "exception",
    [
        pytest.param(CallbackRejectedError, id="callback_rejected"),
        pytest.param(CannotConnectError, id="cannot_connect"),
    ],
)
async def test_register_failure_frees_the_address(
    hass: HomeAssistant, mock_lan_register: AsyncMock, exception: type[Exception]
) -> None:
    """The probe answers callbacks only while registering, then leaves the server."""
    statuses_while_registering: list[int] = []

    async def refuse(_: AylaLanDevice) -> None:
        statuses_while_registering.append(_callback_status(hass))
        raise exception

    mock_lan_register.side_effect = refuse
    result = await _start(hass, "local")

    await hass.config_entries.flow.async_configure(result["flow_id"], LOCAL_INPUT)

    # Registered but without a session, so the request is malformed, not refused.
    assert statuses_while_registering == [400]
    assert _callback_status(hass) == 403


@pytest.mark.usefixtures("mock_fetch_dsn", "mock_source_ip", "mock_lan_register")
async def test_verify_invalid_key(
    hass: HomeAssistant, mock_wait_verified: AsyncMock
) -> None:
    """A unit that dials back but rejects the key returns to the key form."""
    mock_wait_verified.side_effect = InvalidKeyError
    result = await _start(hass, "local")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], LOCAL_INPUT
    )

    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "local"
    assert result["errors"] == {"base": "invalid_key"}
    assert _suggested_values(result) == LOCAL_INPUT
    assert _callback_status(hass) == 403

    mock_wait_verified.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], LOCAL_INPUT
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == _entry_data(LOCAL_HOST)
    assert mock_wait_verified.await_count == 2
    assert _callback_status(hass) == 403


@pytest.mark.usefixtures("mock_fetch_dsn", "mock_source_ip", "mock_lan_register")
async def test_verify_asks_for_a_value(
    hass: HomeAssistant, mock_wait_verified: AsyncMock
) -> None:
    """Only a pushed value proves the key, so the unit is asked for one."""
    commands: list[dict[str, Any]] = []

    async def dial_back(_: AylaLanDevice) -> int:
        server = async_get_server(hass)
        key_exchange = {
            "ver": 1,
            "proto": 1,
            "random_1": RANDOM_1,
            "time_1": TIME_1,
            "key_id": LANIP_KEY_ID,
        }
        _, reply = server.handle(
            LOCAL_HOST,
            "POST",
            "key_exchange.json",
            json.dumps({"key_exchange": key_exchange}).encode(),
        )
        crypto = SessionCrypto(
            LANIP_KEY, reply["random_2"], reply["time_2"], RANDOM_1, TIME_1
        )
        _, command = server.handle(LOCAL_HOST, "GET", "commands.json", b"")
        commands.append(crypto.decrypt_and_validate(command))
        return LANIP_KEY_ID

    mock_wait_verified.side_effect = dial_back
    result = await _start(hass, "local")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], LOCAL_INPUT
    )

    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert [read_resource(command) for command in commands] == [
        "property.json?name=operation_mode"
    ]


@pytest.mark.usefixtures("mock_fetch_dsn", "mock_source_ip", "mock_lan_register")
async def test_verify_no_callback(
    hass: HomeAssistant, mock_wait_verified: AsyncMock
) -> None:
    """When the unit never dials back, the callback address is asked for."""
    mock_wait_verified.side_effect = NoCallbackError
    result = await _start(hass, "local")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], LOCAL_INPUT
    )

    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "callback"
    assert result["errors"] == {"base": "no_callback"}
    assert result["description_placeholders"] == {
        "host": LOCAL_HOST,
        "callback": f"{CALLBACK_HOST}:8123",
    }
    assert _suggested_values(result) == {
        CONF_CALLBACK_HOST: CALLBACK_HOST,
        CONF_CALLBACK_PORT: 8123,
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CALLBACK_HOST: "homeassistant.local", CONF_CALLBACK_PORT: 8124},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "callback"
    assert result["errors"] == {CONF_CALLBACK_HOST: "invalid_ip"}

    mock_wait_verified.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CALLBACK_HOST: f" {HOST_LAN_IP}\n", CONF_CALLBACK_PORT: 8124},
    )
    assert result["description_placeholders"]["callback"] == f"{HOST_LAN_IP}:8124"
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == _entry_data(
        LOCAL_HOST, **{CONF_CALLBACK_HOST: HOST_LAN_IP, CONF_CALLBACK_PORT: 8124}
    )


@pytest.mark.usefixtures("mock_fetch_dsn", "mock_lan_register", "mock_wait_verified")
@pytest.mark.parametrize(
    ("internal_url", "callback_host", "callback_port", "source_ip_awaits"),
    [
        pytest.param(
            f"http://{HOST_LAN_IP}:8124", HOST_LAN_IP, 8124, 0, id="http_ip_with_port"
        ),
        pytest.param(f"http://{HOST_LAN_IP}", HOST_LAN_IP, 8123, 0, id="http_ip"),
        pytest.param(
            f"https://{HOST_LAN_IP}:8124", CALLBACK_HOST, 8123, 1, id="https_ip"
        ),
        pytest.param(
            "http://homeassistant.local:8124",
            CALLBACK_HOST,
            8123,
            1,
            id="http_hostname",
        ),
        pytest.param(None, CALLBACK_HOST, 8123, 1, id="unset"),
    ],
)
async def test_callback_from_internal_url(
    hass: HomeAssistant,
    mock_source_ip: AsyncMock,
    internal_url: str | None,
    callback_host: str,
    callback_port: int,
    source_ip_awaits: int,
) -> None:
    """A plain HTTP local network URL with an IP overrides the detected address."""
    hass.config.internal_url = internal_url
    result = await _start(hass, "local")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], LOCAL_INPUT
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CALLBACK_HOST] == callback_host
    assert result["data"][CONF_CALLBACK_PORT] == callback_port
    assert mock_source_ip.await_count == source_ip_awaits


@pytest.mark.usefixtures("mock_fetch_dsn", "mock_lan_register", "mock_wait_verified")
async def test_source_ip_unknown(
    hass: HomeAssistant, mock_source_ip: AsyncMock
) -> None:
    """Without a route to the unit, the callback address is asked for up front."""
    mock_source_ip.side_effect = HomeAssistantError
    result = await _start(hass, "local")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], LOCAL_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "callback"
    assert result["errors"] == {}
    assert _suggested_values(result) == {
        CONF_CALLBACK_HOST: None,
        CONF_CALLBACK_PORT: 8123,
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CALLBACK_HOST: CALLBACK_HOST, CONF_CALLBACK_PORT: 8123},
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == _entry_data(LOCAL_HOST)
    mock_source_ip.assert_awaited_once()


@pytest.mark.usefixtures("mock_fetch_dsn", "mock_source_ip", "mock_wait_verified")
async def test_https_asks_for_plain_http_callback(
    hass: HomeAssistant, mock_lan_register: AsyncMock
) -> None:
    """The unit cannot dial an HTTPS server, so a plain-HTTP address is asked for.

    An address the user enters is trusted, even on Home Assistant's own port.
    """
    result = await _start(hass, "local")
    # Set once `http`, a dependency, has set itself up.
    hass.config.api = ApiConfig(HOST, HOST, 8123, True)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], LOCAL_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "callback"
    assert result["errors"] == {"base": "https_only"}
    assert _suggested_values(result) == {
        CONF_CALLBACK_HOST: CALLBACK_HOST,
        CONF_CALLBACK_PORT: 8123,
    }
    mock_lan_register.assert_not_awaited()

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CALLBACK_HOST: HOST_LAN_IP, CONF_CALLBACK_PORT: 8123}
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == _entry_data(
        LOCAL_HOST, **{CONF_CALLBACK_HOST: HOST_LAN_IP}
    )
    mock_lan_register.assert_awaited_once()


@pytest.mark.usefixtures(
    "mock_fetch_dsn", "mock_source_ip", "mock_lan_register", "mock_wait_verified"
)
@pytest.mark.parametrize(
    ("use_ssl", "internal_url", "callback_host", "callback_port"),
    [
        pytest.param(False, None, CALLBACK_HOST, 8123, id="plain_http"),
        pytest.param(
            True, f"http://{HOST_LAN_IP}:8124", HOST_LAN_IP, 8124, id="http_proxy"
        ),
    ],
)
async def test_plain_http_callback_guessed(
    hass: HomeAssistant,
    use_ssl: bool,
    internal_url: str | None,
    callback_host: str,
    callback_port: int,
) -> None:
    """A guess the unit can dial over plain HTTP is used without asking."""
    hass.config.internal_url = internal_url
    result = await _start(hass, "local")
    hass.config.api = ApiConfig(HOST, HOST, 8123, use_ssl)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], LOCAL_INPUT
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CALLBACK_HOST] == callback_host
    assert result["data"][CONF_CALLBACK_PORT] == callback_port


@pytest.mark.usefixtures(
    "mock_fetch_dsn", "mock_source_ip", "mock_lan_register", "mock_wait_verified"
)
async def test_callback_port(hass: HomeAssistant) -> None:
    """The unit is told to dial Home Assistant's own web server port."""
    assert await async_setup_component(hass, "http", {})

    with patch.object(hass.http, "server_port", 8124):
        result = await _start(hass, "local")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], LOCAL_INPUT
        )
        result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CALLBACK_PORT] == 8124


@pytest.mark.usefixtures("mock_fetch_dsn", "mock_source_ip", "mock_lan_register")
async def test_flow_closed_during_verify(
    hass: HomeAssistant, mock_wait_verified: AsyncMock
) -> None:
    """Closing the flow stops waiting for the unit."""
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def wait_forever(*_: Any) -> int:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return LANIP_KEY_ID

    mock_wait_verified.side_effect = wait_forever
    result = await _start(hass, "local")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], LOCAL_INPUT
    )
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    await started.wait()

    hass.config_entries.flow.async_abort(result["flow_id"])
    await hass.async_block_till_done()

    assert cancelled.is_set()
    assert not hass.config_entries.flow.async_progress()
    assert _callback_status(hass) == 403


async def test_dhcp_discovery(hass: HomeAssistant, mock_fetch_dsn: AsyncMock) -> None:
    """A discovered unit is named by its DSN and offers both ways in."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DISCOVERY
    )

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "discovery_confirm"
    assert result["menu_options"] == ["cloud", "local"]
    assert result["description_placeholders"] == {
        "host": DISCOVERED_HOST,
        "dsn": DSN,
    }
    flow = hass.config_entries.flow.async_get(result["flow_id"])
    assert flow["context"]["unique_id"] == DSN
    assert flow["context"]["title_placeholders"] == {"name": DSN}
    mock_fetch_dsn.assert_awaited_once_with(
        async_get_clientsession(hass), DISCOVERED_HOST
    )


@pytest.mark.usefixtures(
    "mock_fetch_dsn", "mock_source_ip", "mock_lan_register", "mock_wait_verified"
)
async def test_dhcp_cloud(hass: HomeAssistant, mock_cloud: MagicMock) -> None:
    """Signing in after discovery picks the discovered unit at its seen address."""
    mock_cloud.list_devices.return_value = [
        _cloud_device(OTHER_DSN, "Bedroom", "192.0.2.12"),
        _cloud_device(),
    ]
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DISCOVERY
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "cloud"}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CLOUD_INPUT
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == PRODUCT_NAME
    assert result["data"] == _entry_data(DISCOVERED_HOST)
    mock_cloud.get_lan_key.assert_awaited_once_with(DSN)


@pytest.mark.usefixtures("mock_fetch_dsn")
async def test_dhcp_cloud_not_on_account(
    hass: HomeAssistant, mock_cloud: MagicMock
) -> None:
    """Signing in to an account without the discovered unit ends the flow."""
    mock_cloud.list_devices.return_value = [
        _cloud_device(OTHER_DSN, "Bedroom", "192.0.2.12")
    ]
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DISCOVERY
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "cloud"}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CLOUD_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_on_account"


@pytest.mark.usefixtures(
    "mock_fetch_dsn", "mock_source_ip", "mock_lan_register", "mock_wait_verified"
)
async def test_dhcp_local(hass: HomeAssistant) -> None:
    """Choosing a kept key after discovery prefills the discovered address."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DISCOVERY
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "local"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "local"
    assert _suggested_values(result) == {
        CONF_HOST: DISCOVERED_HOST,
        CONF_LANIP_KEY: None,
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**LOCAL_INPUT, CONF_HOST: DISCOVERED_HOST}
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == _entry_data(DISCOVERED_HOST)


@pytest.mark.usefixtures("mock_fetch_dsn")
async def test_dhcp_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Rediscovering a configured unit at a new address moves the entry there."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DISCOVERY
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_HOST] == DISCOVERED_HOST


async def test_dhcp_known_address(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_fetch_dsn: AsyncMock
) -> None:
    """A configured unit seen at its known address is not probed again."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**ENTRY_DATA, CONF_HOST: DISCOVERED_HOST}
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DISCOVERY
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_fetch_dsn.assert_not_awaited()


async def test_dhcp_cannot_connect(
    hass: HomeAssistant, mock_fetch_dsn: AsyncMock
) -> None:
    """A device that does not report a DSN is not offered."""
    mock_fetch_dsn.side_effect = AylaLanError

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DISCOVERY
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def _start_reconfigure(
    hass: HomeAssistant, entry: MockConfigEntry, menu_option: str
) -> ConfigFlowResult:
    result = await entry.start_reconfigure_flow(hass)
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": menu_option}
    )


async def test_reconfigure_menu(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Reconfiguring offers the unit's address and key, the cloud, or the callback."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reconfigure_flow(hass)

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "reconfigure"
    assert result["menu_options"] == ["unit", "cloud", "callback"]
    assert result["description_placeholders"] == {"host": HOST, "dsn": DSN}


@pytest.mark.usefixtures("mock_wait_verified")
async def test_reconfigure(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    mock_lan_register: AsyncMock,
    mock_setup_entry: AsyncMock,
    mock_unload_entry: AsyncMock,
) -> None:
    """A new callback address is checked with the unit, then saved."""
    states: list[ConfigEntryState] = []
    # The entry's session holds the unit's slot, so it must be gone first.
    mock_lan_register.side_effect = lambda _: states.append(loaded_entry.state)

    result = await _start_reconfigure(hass, loaded_entry, "callback")

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "callback"
    assert _suggested_values(result) == {
        CONF_CALLBACK_HOST: CALLBACK_HOST,
        CONF_CALLBACK_PORT: CALLBACK_PORT,
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CALLBACK_HOST: HOST_LAN_IP, CONF_CALLBACK_PORT: 8124},
    )
    result = await _finish_verify(hass, result)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert states == [ConfigEntryState.NOT_LOADED]
    assert loaded_entry.data == {
        **ENTRY_DATA,
        CONF_CALLBACK_HOST: HOST_LAN_IP,
        CONF_CALLBACK_PORT: 8124,
    }
    assert loaded_entry.state is ConfigEntryState.LOADED
    assert mock_unload_entry.await_count == 1
    assert mock_setup_entry.await_count == 2


@pytest.mark.usefixtures("mock_lan_register", "mock_wait_verified")
async def test_reconfigure_not_loaded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
) -> None:
    """An entry that is not set up is saved and set up."""
    mock_config_entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, mock_config_entry, "callback")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CALLBACK_HOST: HOST_LAN_IP, CONF_CALLBACK_PORT: CALLBACK_PORT},
    )
    result = await _finish_verify(hass, result)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_CALLBACK_HOST] == HOST_LAN_IP
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_setup_entry.await_count == 1


@pytest.mark.usefixtures("mock_lan_register")
@pytest.mark.parametrize(
    ("user_input", "data"),
    [
        pytest.param(
            {CONF_HOST: f" {LOCAL_HOST} ", CONF_LANIP_KEY: f" {NEW_LANIP_KEY}\n"},
            {CONF_HOST: LOCAL_HOST, CONF_LANIP_KEY: NEW_LANIP_KEY},
            id="new_host_and_key",
        ),
        pytest.param(
            {CONF_HOST: LOCAL_HOST, CONF_LANIP_KEY: " \n"},
            {CONF_HOST: LOCAL_HOST},
            id="blank_key",
        ),
        pytest.param({CONF_HOST: LOCAL_HOST}, {CONF_HOST: LOCAL_HOST}, id="no_key"),
        pytest.param(
            {CONF_HOST: HOST, CONF_LANIP_KEY: NEW_LANIP_KEY},
            {CONF_LANIP_KEY: NEW_LANIP_KEY},
            id="same_host",
        ),
    ],
)
async def test_reconfigure_unit(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    mock_fetch_dsn: AsyncMock,
    mock_wait_verified: AsyncMock,
    mock_source_ip: AsyncMock,
    user_input: dict[str, str],
    data: dict[str, str],
) -> None:
    """A new address or key is checked with the unit, then saved.

    A blank key keeps the current one, and the callback stays as it was.
    """
    mock_wait_verified.return_value = NEW_LANIP_KEY_ID
    result = await _start_reconfigure(hass, loaded_entry, "unit")

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "unit"
    assert result["errors"] == {}
    assert result["description_placeholders"] == {"dsn": DSN}
    assert _suggested_values(result) == {CONF_HOST: HOST, CONF_LANIP_KEY: None}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    result = await _finish_verify(hass, result)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert loaded_entry.data == {
        **ENTRY_DATA,
        CONF_LANIP_KEY_ID: NEW_LANIP_KEY_ID,
        **data,
    }
    assert loaded_entry.state is ConfigEntryState.LOADED
    mock_fetch_dsn.assert_awaited_once_with(
        async_get_clientsession(hass), user_input[CONF_HOST].strip()
    )
    mock_source_ip.assert_not_awaited()


@pytest.mark.usefixtures("mock_lan_register", "mock_wait_verified")
@pytest.mark.parametrize(
    ("user_input", "fetch_dsn", "errors"),
    [
        pytest.param(
            {CONF_HOST: "aircon.local"},
            {"return_value": DSN},
            {CONF_HOST: "invalid_ip"},
            id="hostname",
        ),
        pytest.param(
            {CONF_HOST: LOCAL_HOST},
            {"side_effect": CannotConnectError},
            {"base": "cannot_connect"},
            id="no_answer",
        ),
        pytest.param(
            {CONF_HOST: LOCAL_HOST},
            {"side_effect": AylaLanError},
            {"base": "not_ayla"},
            id="not_ayla",
        ),
        pytest.param(
            {CONF_HOST: LOCAL_HOST},
            {"return_value": OTHER_DSN},
            {"base": "wrong_device"},
            id="wrong_device",
        ),
    ],
)
async def test_reconfigure_unit_errors(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    mock_fetch_dsn: AsyncMock,
    user_input: dict[str, str],
    fetch_dsn: dict[str, Any],
    errors: dict[str, str],
) -> None:
    """Bad input is refused with the typed address kept, then the flow recovers."""
    mock_fetch_dsn.configure_mock(**fetch_dsn)
    result = await _start_reconfigure(hass, loaded_entry, "unit")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "unit"
    assert result["errors"] == errors
    assert _suggested_values(result) == {**user_input, CONF_LANIP_KEY: None}
    # Nothing is unloaded before the unit is known to be this one.
    assert loaded_entry.state is ConfigEntryState.LOADED

    mock_fetch_dsn.configure_mock(side_effect=None, return_value=DSN)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: LOCAL_HOST}
    )
    result = await _finish_verify(hass, result)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert loaded_entry.data == {**ENTRY_DATA, CONF_HOST: LOCAL_HOST}


async def test_reconfigure_unit_already_configured(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    mock_fetch_dsn: AsyncMock,
) -> None:
    """An address another entry uses is not taken over."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=OTHER_DSN,
        data=_entry_data(LOCAL_HOST, **{CONF_DSN: OTHER_DSN}),
    ).add_to_hass(hass)
    result = await _start_reconfigure(hass, loaded_entry, "unit")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: LOCAL_HOST}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_fetch_dsn.assert_not_awaited()
    assert loaded_entry.data == ENTRY_DATA


async def _refused_at_once(
    hass: HomeAssistant, result: ConfigFlowResult
) -> ConfigFlowResult:
    """A refused registration is answered without a progress step."""
    return result


@pytest.mark.usefixtures("mock_fetch_dsn")
@pytest.mark.parametrize(
    (
        "menu_option",
        "user_input",
        "register_error",
        "verify_error",
        "settle",
        "error",
    ),
    [
        pytest.param(
            "unit",
            {CONF_HOST: LOCAL_HOST},
            CannotConnectError,
            None,
            _refused_at_once,
            "cannot_connect",
            id="unit_cannot_connect",
        ),
        pytest.param(
            "callback",
            {CONF_CALLBACK_HOST: HOST_LAN_IP, CONF_CALLBACK_PORT: CALLBACK_PORT},
            CannotConnectError,
            None,
            _refused_at_once,
            "cannot_connect",
            id="callback_cannot_connect",
        ),
        pytest.param(
            "unit",
            {CONF_HOST: LOCAL_HOST, CONF_LANIP_KEY: NEW_LANIP_KEY},
            None,
            InvalidKeyError,
            _finish_verify,
            "invalid_key",
            id="unit_invalid_key",
        ),
        pytest.param(
            "callback",
            {CONF_CALLBACK_HOST: HOST_LAN_IP, CONF_CALLBACK_PORT: CALLBACK_PORT},
            None,
            InvalidKeyError,
            _finish_verify,
            "invalid_key",
            id="callback_invalid_key",
        ),
    ],
)
async def test_reconfigure_failed_check_returns_to_unit(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    mock_lan_register: AsyncMock,
    mock_wait_verified: AsyncMock,
    menu_option: str,
    user_input: dict[str, Any],
    register_error: type[Exception] | None,
    verify_error: type[Exception] | None,
    settle: Callable[[HomeAssistant, ConfigFlowResult], Awaitable[ConfigFlowResult]],
    error: str,
) -> None:
    """An unreachable unit or a rejected key asks for the address and key."""
    mock_lan_register.side_effect = register_error
    mock_wait_verified.side_effect = verify_error
    result = await _start_reconfigure(hass, loaded_entry, menu_option)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    result = await settle(hass, result)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "unit"
    assert result["errors"] == {"base": error}

    hass.config_entries.flow.async_abort(result["flow_id"])
    await hass.async_block_till_done()

    assert loaded_entry.data == ENTRY_DATA
    assert loaded_entry.state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("mock_fetch_dsn", "mock_lan_register")
@pytest.mark.parametrize(
    ("retry_key", "saved_key"),
    [
        pytest.param(NEW_LANIP_KEY, NEW_LANIP_KEY, id="new_key"),
        pytest.param("", ENTRY_DATA[CONF_LANIP_KEY], id="blank_keeps_entry_key"),
    ],
)
async def test_reconfigure_unit_retried_after_invalid_key(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    mock_wait_verified: AsyncMock,
    retry_key: str,
    saved_key: str,
) -> None:
    """After a rejected key, a blank key falls back to the entry's, not the rejected one."""
    mock_wait_verified.side_effect = InvalidKeyError
    result = await _start_reconfigure(hass, loaded_entry, "unit")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_LANIP_KEY: "f" * 32}
    )
    result = await _finish_verify(hass, result)
    assert result["step_id"] == "unit"
    assert result["errors"] == {"base": "invalid_key"}

    mock_wait_verified.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_LANIP_KEY: retry_key}
    )
    result = await _finish_verify(hass, result)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert loaded_entry.data == {**ENTRY_DATA, CONF_LANIP_KEY: saved_key}
    assert loaded_entry.state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("mock_lan_register")
async def test_reconfigure_closed_after_no_callback(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    mock_wait_verified: AsyncMock,
) -> None:
    """Giving up after a failed check brings the entry back unchanged."""
    mock_wait_verified.side_effect = NoCallbackError

    result = await _start_reconfigure(hass, loaded_entry, "callback")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CALLBACK_HOST: HOST_LAN_IP, CONF_CALLBACK_PORT: CALLBACK_PORT},
    )
    result = await _finish_verify(hass, result)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "callback"
    assert result["errors"] == {"base": "no_callback"}
    # Left unloaded while the user corrects the address.
    assert loaded_entry.state is ConfigEntryState.NOT_LOADED

    hass.config_entries.flow.async_abort(result["flow_id"])
    await hass.async_block_till_done()

    assert loaded_entry.data == ENTRY_DATA
    assert loaded_entry.state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("mock_lan_register")
@pytest.mark.parametrize(
    ("cloud_ip", "saved_host"),
    [
        pytest.param(CLOUD_HOST, CLOUD_HOST, id="cloud_address"),
        pytest.param(None, ENTRY_DATA[CONF_HOST], id="no_cloud_address"),
    ],
)
async def test_reconfigure_cloud(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    mock_cloud: MagicMock,
    mock_wait_verified: AsyncMock,
    mock_source_ip: AsyncMock,
    cloud_ip: str | None,
    saved_host: str,
) -> None:
    """Signing in fetches the unit's current key, and its address when the cloud knows it."""
    mock_cloud.list_devices.return_value = [
        _cloud_device(OTHER_DSN, lan_ip=LOCAL_HOST),
        _cloud_device(lan_ip=cloud_ip),
    ]
    mock_cloud.get_lan_key.return_value = LanKey(NEW_LANIP_KEY, NEW_LANIP_KEY_ID)
    mock_wait_verified.return_value = NEW_LANIP_KEY_ID
    result = await _start_reconfigure(hass, loaded_entry, "cloud")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "cloud"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CLOUD_INPUT
    )
    result = await _finish_verify(hass, result)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert loaded_entry.data == {
        **ENTRY_DATA,
        CONF_HOST: saved_host,
        CONF_LANIP_KEY: NEW_LANIP_KEY,
        CONF_LANIP_KEY_ID: NEW_LANIP_KEY_ID,
    }
    assert loaded_entry.state is ConfigEntryState.LOADED
    mock_cloud.get_lan_key.assert_awaited_once_with(DSN)
    mock_source_ip.assert_not_awaited()


@pytest.mark.usefixtures("mock_fetch_dsn")
async def test_reconfigure_cloud_key_kept_after_cannot_connect(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    mock_cloud: MagicMock,
    mock_lan_register: AsyncMock,
    mock_wait_verified: AsyncMock,
) -> None:
    """A fetched key survives a wrong address: a blank key on the unit form keeps it."""
    mock_cloud.get_lan_key.return_value = LanKey(NEW_LANIP_KEY, NEW_LANIP_KEY_ID)
    mock_lan_register.side_effect = CannotConnectError
    mock_wait_verified.return_value = NEW_LANIP_KEY_ID
    result = await _start_reconfigure(hass, loaded_entry, "cloud")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CLOUD_INPUT
    )
    assert result["step_id"] == "unit"
    assert result["errors"] == {"base": "cannot_connect"}

    mock_lan_register.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: LOCAL_HOST, CONF_LANIP_KEY: ""}
    )
    result = await _finish_verify(hass, result)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert loaded_entry.data == {
        **ENTRY_DATA,
        CONF_HOST: LOCAL_HOST,
        CONF_LANIP_KEY: NEW_LANIP_KEY,
        CONF_LANIP_KEY_ID: NEW_LANIP_KEY_ID,
    }


async def test_reconfigure_cloud_not_on_account(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, mock_cloud: MagicMock
) -> None:
    """An account without this unit has no key for it."""
    mock_cloud.list_devices.return_value = [_cloud_device(OTHER_DSN)]
    result = await _start_reconfigure(hass, loaded_entry, "cloud")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CLOUD_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_on_account"
    assert loaded_entry.data == ENTRY_DATA
    mock_cloud.get_lan_key.assert_not_awaited()
