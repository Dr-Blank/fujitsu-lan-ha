"""HTTP endpoints the air conditioner dials back into, on HA's own server."""

from aioayla_lan import LAN_URI, AylaLanServer
from aiohttp import web

from homeassistant.core import HomeAssistant
from homeassistant.helpers.http import HomeAssistantView
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN

DATA_SERVER: HassKey[AylaLanServer] = HassKey(DOMAIN)


class AylaLanView(HomeAssistantView):
    """Serves `/local_lan/*` for every configured unit.

    The module cannot present a token. `AylaLanServer` only answers the IPs of
    configured units, and every payload is HMAC-signed with the per-device key.
    """

    url = f"{LAN_URI}/{{path:.+}}"
    name = f"api:{DOMAIN}:local_lan"
    requires_auth = False

    def __init__(self, server: AylaLanServer) -> None:
        """Initialise."""
        self._server = server

    async def _handle(self, request: web.Request, path: str) -> web.Response:
        status, body = self._server.handle(
            request.remote, request.method, path, await request.read()
        )
        return self.json(body, status)

    async def get(self, request: web.Request, path: str) -> web.Response:
        """Command fetch."""
        return await self._handle(request, path)

    async def post(self, request: web.Request, path: str) -> web.Response:
        """Key exchange and datapoints."""
        return await self._handle(request, path)

    async def put(self, request: web.Request, path: str) -> web.Response:
        """Datapoints, on some firmware."""
        return await self._handle(request, path)


def async_get_server(hass: HomeAssistant) -> AylaLanServer:
    """Return the shared router, registering the view on first use."""
    if (server := hass.data.get(DATA_SERVER)) is None:
        server = hass.data[DATA_SERVER] = AylaLanServer()
        hass.http.register_view(AylaLanView(server))
    return server
