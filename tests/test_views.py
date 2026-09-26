"""Tests for the `/local_lan` view the unit dials into."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import SimulatedUnit
from .const import LANIP_KEY_ID


async def test_key_exchange_reply(unit: SimulatedUnit) -> None:
    """The reply is unwrapped: a wrapped one makes the unit retry forever."""
    reply = await unit.key_exchange()

    assert set(reply) == {"random_2", "time_2"}


@pytest.mark.usefixtures("mock_register")
async def test_unknown_remote_is_refused(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """Only the configured unit's address may use the unauthenticated view."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, CONF_HOST: "192.0.2.10"}
    )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    resp = await client.post(
        "/local_lan/key_exchange.json",
        json={
            "key_exchange": {
                "ver": 1,
                "proto": 1,
                "random_1": "abcdefghijklmnop",
                "time_1": 1,
                "key_id": LANIP_KEY_ID,
            }
        },
    )

    assert resp.status == 403


@pytest.mark.parametrize(
    ("method", "path", "body", "status"),
    [
        pytest.param("GET", "commands.json", None, 400, id="commands_without_session"),
        pytest.param("GET", "unknown.json", None, 404, id="unknown_get"),
        pytest.param("POST", "datapoint.json", "not json", 400, id="malformed_json"),
        pytest.param(
            "POST",
            "key_exchange.json",
            '{"key_exchange": {"ver": 1, "proto": 1, "random_1": "a",'
            ' "time_1": 1, "key_id": 1}}',
            404,
            id="wrong_key_id",
        ),
    ],
)
async def test_rejected_requests(
    unit: SimulatedUnit, method: str, path: str, body: str | None, status: int
) -> None:
    """Requests from the unit's address that cannot be served are refused."""
    resp = await unit.client.request(method, f"/local_lan/{path}", data=body)

    assert resp.status == status


async def test_partial_content_while_commands_queued(unit: SimulatedUnit) -> None:
    """206 makes the unit fetch again at once, until nothing is left queued."""
    await unit.key_exchange()
    assert await unit.push("outdoor_temperature", 8700) == 206

    await unit.drain()

    assert await unit.push("outdoor_temperature", 8700) == 200


async def test_forged_datapoint_is_refused(unit: SimulatedUnit) -> None:
    """A datapoint that fails the HMAC check is not applied."""
    await unit.key_exchange()
    forged = {"enc": "AAAAAAAAAAAAAAAAAAAAAA==", "sign": "AAAA"}

    resp = await unit.client.post("/local_lan/property/datapoint.json", json=forged)

    assert resp.status == 400
