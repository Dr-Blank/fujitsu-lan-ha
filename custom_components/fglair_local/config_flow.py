"""Config flow for Fujitsu FGLair Local.

A unit is added either by signing in to FGLair once, which fetches its LAN key,
or by pasting a LAN key kept from before. Either way the flow then registers
with the unit and waits for it to dial back, which proves the address, the
callback path and the key before the entry is created.
"""

import asyncio
from typing import Any

from aioayla_lan import (
    AylaCloud,
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
    fetch_dsn,
)
import voluptuous as vol
from yarl import URL

from homeassistant.components.network import async_get_source_ip
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD, CONF_REGION
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.util.network import is_ip_address

from .const import (
    CONF_CALLBACK_HOST,
    CONF_CALLBACK_PORT,
    CONF_DSN,
    CONF_LANIP_KEY,
    CONF_LANIP_KEY_ID,
    DOMAIN,
    FGLAIR_APPS,
)
from .properties import OPERATION_MODE
from .redact import redact_key_in_logs
from .views import async_get_server

CONF_DEVICE = "device"
MENU = ["cloud", "local"]

# Accounts made in the European FGLair app live on the EU cloud.
EU_COUNTRIES = frozenset(
    {
        "AD", "AL", "AT", "BA", "BE", "BG", "CH", "CY", "CZ", "DE", "DK", "EE",
        "ES", "FI", "FO", "FR", "GB", "GI", "GR", "HR", "HU", "IE", "IS", "IT",
        "LI", "LT", "LU", "LV", "MC", "MD", "ME", "MK", "MT", "NL", "NO", "PL",
        "PT", "RO", "RS", "SE", "SI", "SK", "SM", "UA", "VA", "XK",
    }
)  # fmt: skip

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class FglairLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a unit through the FGLair cloud or with a known LAN key."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise."""
        self._host: str | None = None
        self._dsn: str | None = None
        self._lan_key: str | None = None
        self._title: str | None = None
        self._callback_host: str | None = None
        self._callback_port: int | None = None
        self._callback_entered = False
        self._cloud: AylaCloud | None = None
        self._cloud_devices: dict[str, CloudDevice] = {}
        self._verify_task: asyncio.Task[int] | None = None
        self._key_id: int | None = None
        self._error: str | None = None
        self._unloaded_entry_id: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer the cloud sign-in or a known LAN key."""
        return self.async_show_menu(step_id="user", menu_options=MENU)

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Identify a unit seen on the network by its DSN."""
        self._async_abort_entries_match({CONF_HOST: discovery_info.ip})
        try:
            dsn = await fetch_dsn(async_get_clientsession(self.hass), discovery_info.ip)
        except AylaLanError:
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(dsn)
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})
        self._host = discovery_info.ip
        self._dsn = dsn
        self.context["title_placeholders"] = {"name": dsn}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer the same two ways in for a discovered unit."""
        return self.async_show_menu(
            step_id="discovery_confirm",
            menu_options=MENU,
            description_placeholders={"host": str(self._host), "dsn": str(self._dsn)},
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Sign in to FGLair and list the account's units."""
        errors: dict[str, str] = {}
        if user_input is not None:
            region = user_input[CONF_REGION]
            cloud = AylaCloud(
                async_get_clientsession(self.hass), *FGLAIR_APPS[region], region
            )
            try:
                await cloud.sign_in(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
                devices = await cloud.list_devices()
            except CloudAuthError:
                errors["base"] = "invalid_auth"
            except CloudError:
                errors["base"] = "cloud_error"
            else:
                return await self._async_use_cloud(cloud, devices)

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
                vol.Required(CONF_REGION, default=self._default_region()): (
                    SelectSelector(
                        SelectSelectorConfig(
                            options=list(FGLAIR_APPS), translation_key=CONF_REGION
                        )
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="cloud",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    def _default_region(self) -> str:
        country = self.hass.config.country
        if country == "CN":
            return "cn"
        return "eu" if country in EU_COUNTRIES else "us"

    async def _async_use_cloud(
        self, cloud: AylaCloud, devices: list[CloudDevice]
    ) -> ConfigFlowResult:
        configured = self._async_current_ids(include_ignore=False)
        self._cloud = cloud
        self._cloud_devices = {
            device.dsn: device
            for device in devices
            if device.dsn not in configured
            and (self._dsn is None or device.dsn == self._dsn)
        }
        if not self._cloud_devices:
            return self.async_abort(
                reason="not_on_account" if self._dsn else "no_devices"
            )
        if len(self._cloud_devices) == 1:
            return await self._async_fetch_key(next(iter(self._cloud_devices.values())))
        return await self.async_step_pick_device()

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose one of several units on the account."""
        if user_input is not None:
            return await self._async_fetch_key(
                self._cloud_devices[user_input[CONF_DEVICE]]
            )
        options = [
            SelectOptionDict(
                value=device.dsn,
                label=f"{device.product_name or device.dsn} ({device.lan_ip or device.dsn})",
            )
            for device in self._cloud_devices.values()
        ]
        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE): SelectSelector(
                        SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def _async_fetch_key(self, device: CloudDevice) -> ConfigFlowResult:
        assert self._cloud is not None
        await self.async_set_unique_id(device.dsn)
        self._abort_if_unique_id_configured()
        if not device.lan_enabled:
            return self.async_abort(reason="lan_disabled")
        try:
            lan_key = await self._cloud.get_lan_key(device.dsn)
        except CloudError:
            return self.async_abort(reason="cloud_error")
        self._dsn = device.dsn
        self._lan_key = lan_key.key
        self._title = device.product_name
        self._host = self._host or device.lan_ip
        if self._host is None:
            self._error = "no_address"
            return await self.async_step_local()
        return await self.async_step_verify()

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Take the unit's address and a LAN key kept from before."""
        if self.source == SOURCE_RECONFIGURE:
            # Only the callback is reconfigured; the address and key are the entry's.
            return self.async_abort(reason=self._error or "cannot_connect")
        errors: dict[str, str] = {}
        if self._error:
            errors["base"], self._error = self._error, None
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            lan_key = user_input[CONF_LANIP_KEY].strip()
            if not is_ip_address(host):
                errors[CONF_HOST] = "invalid_ip"
            elif not lan_key:
                errors[CONF_LANIP_KEY] = "key_required"
            else:
                self._async_abort_entries_match({CONF_HOST: host})
                try:
                    dsn = await fetch_dsn(async_get_clientsession(self.hass), host)
                except CannotConnectError:
                    errors["base"] = "cannot_connect"
                except AylaLanError:
                    errors["base"] = "not_ayla"
                else:
                    await self.async_set_unique_id(dsn)
                    self._abort_if_unique_id_configured()
                    self._host = host
                    self._dsn = dsn
                    self._lan_key = lan_key
                    return await self.async_step_verify()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_LANIP_KEY): PASSWORD_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="local",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                user_input or {CONF_HOST: self._host, CONF_LANIP_KEY: self._lan_key},
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address the unit dials Home Assistant back at."""
        entry = self._get_reconfigure_entry()
        self._host = entry.data[CONF_HOST]
        self._dsn = entry.data[CONF_DSN]
        self._lan_key = entry.data[CONF_LANIP_KEY]
        self._callback_host = entry.data[CONF_CALLBACK_HOST]
        self._callback_port = entry.data[CONF_CALLBACK_PORT]
        return await self.async_step_callback()

    async def async_step_callback(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask how the unit reaches Home Assistant, when the guess did not work."""
        errors: dict[str, str] = {}
        if self._error:
            errors["base"], self._error = self._error, None
        if user_input is not None:
            callback_host = user_input[CONF_CALLBACK_HOST].strip()
            if not is_ip_address(callback_host):
                errors[CONF_CALLBACK_HOST] = "invalid_ip"
            else:
                self._callback_host = callback_host
                self._callback_port = user_input[CONF_CALLBACK_PORT]
                self._callback_entered = True
                return await self.async_step_verify()

        schema = vol.Schema(
            {
                vol.Required(CONF_CALLBACK_HOST): str,
                vol.Required(CONF_CALLBACK_PORT): cv.port,
            }
        )
        return self.async_show_form(
            step_id="callback",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                user_input
                or {
                    CONF_CALLBACK_HOST: self._callback_host,
                    CONF_CALLBACK_PORT: self._default_port(),
                },
            ),
            errors=errors,
            description_placeholders={
                "host": str(self._host),
                "callback": f"{self._callback_host}:{self._default_port()}",
            },
        )

    def _default_port(self) -> int:
        if self._callback_port is not None:
            return self._callback_port
        return self.hass.http.server_port

    async def _async_guess_callback(self) -> tuple[str, int]:
        """Pick the address the unit should dial.

        A local network URL set by the user wins: behind Docker's NAT it is the
        only way to learn the host's address. Otherwise use the address Home
        Assistant reaches the unit from.
        """
        if internal_url := self.hass.config.internal_url:
            url = URL(internal_url)
            if url.scheme == "http" and url.host and is_ip_address(url.host):
                return url.host, url.explicit_port or self.hass.http.server_port
        assert self._host is not None
        return (
            await async_get_source_ip(self.hass, target_ip=self._host),
            self.hass.http.server_port,
        )

    async def async_step_verify(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Register with the unit, then wait for it to dial back."""
        if self._verify_task is None:
            assert self._host and self._dsn and self._lan_key
            # The probe would take this host's slot on the shared callback server.
            if self.source == SOURCE_RECONFIGURE:
                await self._async_unload_reconfigured()
            else:
                self._async_abort_entries_match({CONF_HOST: self._host})
            # A guess depends on the unit's address, which may have changed.
            if not self._callback_entered:
                try:
                    (
                        self._callback_host,
                        self._callback_port,
                    ) = await self._async_guess_callback()
                except HomeAssistantError:
                    return await self.async_step_callback()
                # The unit only speaks plain HTTP; a proxy in front must be entered.
                if (
                    (api := self.hass.config.api) is not None
                    and api.use_ssl
                    and self._callback_port == api.port
                ):
                    self._error = "https_only"
                    return await self.async_step_callback()
            assert self._callback_host and self._callback_port
            redact_key_in_logs(self._lan_key)
            server = async_get_server(self.hass)
            device = AylaLanDevice(
                async_get_clientsession(self.hass),
                self._host,
                self._dsn,
                LanKey(self._lan_key),
                self._callback_host,
                self._callback_port,
                on_datapoint=lambda _: None,
                # Verifying needs a pushed value; this read asks for one.
                prime_properties=(OPERATION_MODE,),
            )
            server.add_device(device)
            # Refusals come back at once, so answer them here, not behind a spinner.
            try:
                await device.register()
            except CallbackRejectedError:
                server.remove_device(device)
                self._error = "callback_rejected"
                return await self.async_step_callback()
            except CannotConnectError:
                server.remove_device(device)
                self._error = "cannot_connect"
                return await self.async_step_local()
            self._verify_task = self.hass.async_create_task(
                self._async_wait_verified(device)
            )

        if not self._verify_task.done():
            return self.async_show_progress(
                step_id="verify",
                progress_action="verify",
                progress_task=self._verify_task,
                description_placeholders={
                    "host": str(self._host),
                    "callback": f"{self._callback_host}:{self._callback_port}",
                },
            )

        task, self._verify_task = self._verify_task, None
        try:
            self._key_id = task.result()
        except NoCallbackError:
            self._error = "no_callback"
            return self.async_show_progress_done(next_step_id="callback")
        except InvalidKeyError:
            self._error = "invalid_key"
            return self.async_show_progress_done(next_step_id="local")
        return self.async_show_progress_done(next_step_id="finish")

    async def _async_unload_reconfigured(self) -> None:
        entry = self._get_reconfigure_entry()
        if entry.state is ConfigEntryState.LOADED:
            await self.hass.config_entries.async_unload(entry.entry_id)
            self._unloaded_entry_id = entry.entry_id

    @callback
    def async_remove(self) -> None:
        """Bring back an entry unloaded by a reconfigure that did not finish."""
        if self._unloaded_entry_id:
            self.hass.config_entries.async_schedule_reload(self._unloaded_entry_id)

    async def _async_wait_verified(self, device: AylaLanDevice) -> int:
        try:
            return await device.wait_verified()
        finally:
            async_get_server(self.hass).remove_device(device)

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the entry for the verified unit."""
        assert self._dsn is not None
        if self.source == SOURCE_RECONFIGURE:
            # Reloaded here, so not again when the flow goes.
            self._unloaded_entry_id = None
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                data_updates={
                    CONF_LANIP_KEY_ID: self._key_id,
                    CONF_CALLBACK_HOST: self._callback_host,
                    CONF_CALLBACK_PORT: self._callback_port,
                },
            )
        return self.async_create_entry(
            title=self._title or self._dsn,
            data={
                CONF_HOST: self._host,
                CONF_DSN: self._dsn,
                CONF_LANIP_KEY: self._lan_key,
                CONF_LANIP_KEY_ID: self._key_id,
                CONF_CALLBACK_HOST: self._callback_host,
                CONF_CALLBACK_PORT: self._callback_port,
            },
        )
