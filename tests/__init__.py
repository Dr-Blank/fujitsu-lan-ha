"""Tests for the Fujitsu FGLair Local integration."""

from typing import Any

from aioayla_lan import LAN_URI, SessionCrypto
from aiohttp.test_utils import TestClient
from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.core import HomeAssistant

from .const import LANIP_KEY, LANIP_KEY_ID

RANDOM_1 = "abcdefghijklmnop"
TIME_1 = 123456789
# 206 while commands are still queued, so the unit fetches again at once.
ACCEPTED = (200, 206)


class SimulatedUnit:
    """The air conditioner's side of the LAN session, driven over HTTP."""

    def __init__(self, client: TestClient) -> None:
        """Initialise without a session."""
        self.client = client
        self._crypto: SessionCrypto | None = None
        self._seq_no = 0

    async def key_exchange(self) -> dict[str, Any]:
        """Start a session as the unit does after registration."""
        resp = await self.client.post(
            f"{LAN_URI}/key_exchange.json",
            json={
                "key_exchange": {
                    "ver": 1,
                    "proto": 1,
                    "random_1": RANDOM_1,
                    "time_1": TIME_1,
                    "key_id": LANIP_KEY_ID,
                }
            },
        )
        assert resp.status == 200
        reply = await resp.json()
        # The unit's view of the session: its sending direction is ours reversed.
        self._crypto = SessionCrypto(
            LANIP_KEY, reply["random_2"], reply["time_2"], RANDOM_1, TIME_1
        )
        return reply

    def _require_session(self) -> SessionCrypto:
        assert self._crypto is not None, "call key_exchange() first"
        return self._crypto

    async def _post_datapoint(
        self, path: str, data: dict[str, Any], method: str = "POST"
    ) -> int:
        doc = self._require_session().encrypt_and_sign(
            {"seq_no": self._seq_no, "data": data}
        )
        self._seq_no += 1
        resp = await self.client.request(method, f"{LAN_URI}/{path}", json=doc)
        return resp.status

    async def push(self, name: str, value: Any, method: str = "POST") -> int:
        """Report one property value. Returns the HTTP status."""
        return await self._post_datapoint(
            "property/datapoint.json",
            {"name": name, "value": value, "base_type": "integer"},
            method,
        )

    async def ack(self, command: dict[str, Any], status: int = 200) -> int:
        """Acknowledge a collected write, as the unit does. Returns the HTTP status."""
        return await self._post_datapoint(
            "property/datapoint/ack.json",
            {
                "id": command["data"]["properties"][0]["property"]["id"],
                "ack_status": status,
                "ack_message": 0,
            },
        )

    async def fetch_command(self) -> dict[str, Any]:
        """Collect and decrypt the next queued command."""
        resp = await self.client.get(f"{LAN_URI}/commands.json")
        assert resp.status in ACCEPTED
        return self._require_session().decrypt_and_validate(await resp.json())

    async def fetch_write(self) -> dict[str, Any]:
        """Collect the next queued command, a write, and acknowledge it."""
        command = await self.fetch_command()
        assert await self.ack(command) in ACCEPTED
        return command

    async def drain(self) -> list[dict[str, Any]]:
        """Collect every queued command, as a responsive unit does."""
        commands = []
        while (command := await self.fetch_command())["data"]:
            commands.append(command)
        return commands

    async def push_all(self, datapoints: dict[str, Any]) -> None:
        """Report several property values, as the unit does after a session starts."""
        for name, value in datapoints.items():
            assert await self.push(name, value) in ACCEPTED


def written(command: dict[str, Any]) -> tuple[str, Any, str]:
    """Return the name, value and base_type a write command carries."""
    prop = command["data"]["properties"][0]["property"]
    return prop["name"], prop["value"], prop["base_type"]


def read_resource(command: dict[str, Any]) -> str:
    """Return the resource a read command asks for."""
    return command["data"]["cmds"][0]["cmd"]["resource"]


async def advance(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    """Move the clock on and run the timers that are now due."""
    freezer.tick(seconds)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
