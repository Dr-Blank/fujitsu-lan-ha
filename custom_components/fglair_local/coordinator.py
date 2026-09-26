"""Holds the pushed state of one unit and fans updates out to entities."""

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
import time
from typing import Any

from aioayla_lan import AylaLanDevice, AylaLanServer, Datapoint, LanKey, WriteError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.typing import UNDEFINED, UndefinedType

from .const import (
    CONF_CALLBACK_HOST,
    CONF_CALLBACK_PORT,
    CONF_DSN,
    CONF_LANIP_KEY,
    CONF_LANIP_KEY_ID,
    DOMAIN,
)
from .properties import (
    BOOLEAN_PROPERTIES,
    DEVICE_CAPABILITIES,
    DISPLAY_TEMPERATURE,
    EXTRA_PROPERTIES,
    MCU_FW_VERSION,
    MODEL_NAME,
    PRIME_PROPERTIES,
    READ_BACK,
    decode_firmware_version,
    is_reported,
)
from .redact import redact_key_in_logs

_LOGGER = logging.getLogger(__name__)

# From the ack: the unit echoes a write only sometimes, and never what the
# write changed elsewhere, such as swing stopping for a fixed position.
READ_BACK_DELAY = 2.0
# A healthy unit fetches a queued command within a second of being notified,
# and the library notifies again after 3 s of silence.
COMMAND_TIMEOUT = 15.0
# However often writes keep coming, read back at least this often.
READ_BACK_MAX_DELAY = 60.0
# An idle unit is asked for something now and then, so a hung one is noticed.
PROBE_INTERVAL = 60.0
WATCHDOG_INTERVAL = timedelta(seconds=5)
# Survive a lost session: fixed for the unit, and re-read only at startup.
STATIC_PROPERTIES = frozenset({DEVICE_CAPABILITIES, MODEL_NAME, MCU_FW_VERSION})

type FglairLocalConfigEntry = ConfigEntry[FglairLocalDevice]


class FglairLocalDevice:
    """One air conditioner reached over Ayla LAN mode."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FglairLocalConfigEntry,
        server: AylaLanServer,
    ) -> None:
        """Initialise from a config entry."""
        self._hass = hass
        self._entry = entry
        self.dsn: str = entry.data[CONF_DSN]
        # Entries added with a pasted key are titled by DSN, not a room name.
        self.name = entry.title if entry.title != self.dsn else "Air conditioner"
        self.values: dict[str, Any] = {}
        self._server = server
        self._listeners: list[Callable[[], None]] = []
        self._read_back: set[str] = set()
        # The unit's own value under each optimistic one, to restore if a write fails.
        self._confirmed: dict[str, Any] = {}
        self._cancel_read_back: CALLBACK_TYPE | None = None
        self._read_back_deadline: float | None = None
        self._was_available = False
        redact_key_in_logs(entry.data[CONF_LANIP_KEY])
        self.lan = AylaLanDevice(
            async_get_clientsession(hass),
            entry.data[CONF_HOST],
            self.dsn,
            LanKey(entry.data[CONF_LANIP_KEY], entry.data[CONF_LANIP_KEY_ID]),
            entry.data[CONF_CALLBACK_HOST],
            entry.data[CONF_CALLBACK_PORT],
            on_datapoint=self._on_datapoint,
            on_connection_change=self._on_connection_change,
            prime_properties=(*PRIME_PROPERTIES, *EXTRA_PROPERTIES),
        )
        server.add_device(self.lan)

    @property
    def available(self) -> bool:
        """Whether a LAN session is up and the unit collects what we queue."""
        return self.lan.connected and not self._stalled()

    def _stalled(self) -> bool:
        if (queued := self.lan.pending_since) is None:
            return False
        # A long-idle session has an old last_seen; count from the queueing.
        since = max(self.lan.last_seen or 0.0, queued)
        return time.monotonic() - since > COMMAND_TIMEOUT

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        """Watch for a unit that stops collecting commands. Returns a stop callback."""
        cancel_watchdog = async_track_time_interval(
            self._hass, self._watchdog, WATCHDOG_INTERVAL
        )

        @callback
        def stop() -> None:
            cancel_watchdog()
            if self._cancel_read_back:
                self._cancel_read_back()
                self._cancel_read_back = None

        return stop

    @callback
    def _watchdog(self, _now: datetime | None = None) -> None:
        if (
            self.lan.connected
            and not self.lan.pending
            and time.monotonic() - (self.lan.last_seen or 0.0) > PROBE_INTERVAL
        ):
            self.lan.request_properties((DISPLAY_TEMPERATURE,))
        if self.available != self._was_available:
            self._notify()

    def detach(self) -> None:
        """Stop accepting callbacks for this unit and stop updating entities."""
        self._server.remove_device(self.lan)
        self._listeners.clear()

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        """Call `update` on every change. Returns an unsubscribe callback."""
        self._listeners.append(update)

        @callback
        def remove() -> None:
            # detach() may have cleared the list already.
            if update in self._listeners:
                self._listeners.remove(update)

        return remove

    def set_property(
        self,
        name: str,
        value: int,
        optimistic: bool = True,
        base_type: str | None = None,
        notify: bool = True,
    ) -> None:
        """Write a property, showing it straight away when `optimistic`.

        Pass `notify=False` for all but the last of several writes made together.
        """
        if base_type is None:
            base_type = "boolean" if name in BOOLEAN_PROPERTIES else "integer"
        self._entry.async_create_background_task(
            self._hass,
            self._async_write(name, value, base_type),
            f"fglair_local write {name}",
        )
        # Only over a value the unit reported: a guess must not create entities.
        if optimistic and is_reported(self.values.get(name)):
            self._confirmed.setdefault(name, self.values[name])
            self.values[name] = value
        if notify:
            self._notify()

    async def _async_write(self, name: str, value: int, base_type: str) -> None:
        try:
            await self.lan.async_set_property(name, value, base_type)
        except WriteError as err:
            _LOGGER.warning(
                "%s: could not set %s to %s: %s", self.dsn, name, value, err
            )
            self._revert(name, value)
        else:
            if self.values.get(name) == value:
                self._confirmed.pop(name, None)
            elif name in self._confirmed:
                self._confirmed[name] = value
        self._schedule_read_back((name, *READ_BACK.get(name, ())))

    def _revert(self, name: str, value: int) -> None:
        # Unless a newer write or a pushed value replaced the guess; the
        # read-back still follows, as a missing ack does not prove it failed.
        if name not in self._confirmed or self.values.get(name) != value:
            return
        self.values[name] = self._confirmed.pop(name)
        self._notify()

    def request_all(self) -> None:
        """Re-read every known property."""
        self.lan.request_properties((*PRIME_PROPERTIES, *EXTRA_PROPERTIES))

    def _schedule_read_back(self, names: tuple[str, ...]) -> None:
        # One read per name however many writes land before the delay ends.
        self._read_back.update(names)
        if self._cancel_read_back:
            self._cancel_read_back()
        now = time.monotonic()
        if self._read_back_deadline is None:
            self._read_back_deadline = now + READ_BACK_MAX_DELAY
        delay = min(READ_BACK_DELAY, max(0.0, self._read_back_deadline - now))
        self._cancel_read_back = async_call_later(
            self._hass, delay, self._read_back_now
        )

    @callback
    def _read_back_now(self, _now: datetime | None = None) -> None:
        self._cancel_read_back = None
        self._read_back_deadline = None
        names, self._read_back = sorted(self._read_back), set()
        self.lan.request_properties(names)

    @callback
    def _on_datapoint(self, datapoint: Datapoint) -> None:
        _LOGGER.debug("%s: %s = %s", self.dsn, datapoint.name, datapoint.value)
        self._confirmed.pop(datapoint.name, None)
        previous = self.values.get(datapoint.name)
        if previous == datapoint.value:
            return
        self.values[datapoint.name] = datapoint.value
        # A change made at the unit, e.g. by the IR remote, may have side
        # effects it does not push, as our own writes do.
        if is_reported(previous) and (linked := READ_BACK.get(datapoint.name)):
            self._schedule_read_back(linked)
        if datapoint.name == MODEL_NAME:
            self._update_device_registry(model=str(datapoint.value))
        elif datapoint.name == MCU_FW_VERSION:
            self._update_device_registry(
                sw_version=decode_firmware_version(datapoint.value)
            )
        self._notify()

    def _update_device_registry(
        self,
        model: str | UndefinedType = UNDEFINED,
        sw_version: str | UndefinedType = UNDEFINED,
    ) -> None:
        # get_or_create: the value may arrive before any entity made the device.
        dr.async_get(self._hass).async_get_or_create(
            config_entry_id=self._entry.entry_id,
            identifiers={(DOMAIN, self.dsn)},
            model=model,
            sw_version=sw_version,
        )

    @callback
    def _on_connection_change(self, connected: bool) -> None:
        _LOGGER.debug("%s: connected=%s", self.dsn, connected)
        if not connected:
            self._confirmed.clear()
            # The unit may change state while unreachable; show unknown until re-read.
            self.values = {
                name: value
                for name, value in self.values.items()
                if name in STATIC_PROPERTIES
            }
        self._notify()

    def _notify(self) -> None:
        self._was_available = self.available
        for update in list(self._listeners):
            update()
