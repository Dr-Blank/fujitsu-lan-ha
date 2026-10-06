"""Tests that the LAN key never reaches the log."""

from collections.abc import Generator
import logging

import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .const import LANIP_KEY
from custom_components.fglair_local.const import CONF_LANIP_KEY, DOMAIN
from custom_components.fglair_local.redact import (
    KEY_FILTER,
    REDACTED,
    redact_key_in_logs,
)

LOGGERS = ["aioayla_lan.device", "custom_components.fglair_local.coordinator"]


@pytest.fixture(autouse=True)
def forget_keys() -> Generator[None]:
    """Start each test with no key known, as the filter is process-wide."""
    KEY_FILTER.keys.clear()
    yield
    KEY_FILTER.keys.clear()


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize("logger", LOGGERS)
def test_key_redacted_in_message(caplog: pytest.LogCaptureFixture, logger: str) -> None:
    """A key in a log line's arguments is replaced once its entry is set up."""
    with caplog.at_level(logging.DEBUG):
        logging.getLogger(logger).debug("key is %s", LANIP_KEY)

    assert LANIP_KEY not in caplog.text
    assert f"key is {REDACTED}" in caplog.text


@pytest.mark.usefixtures("init_integration")
def test_key_redacted_in_traceback(caplog: pytest.LogCaptureFixture) -> None:
    """A key carried by a logged exception is replaced in the traceback."""
    logging.getLogger("aioayla_lan.server").error(
        "failed", exc_info=ValueError(LANIP_KEY)
    )

    assert LANIP_KEY not in caplog.text
    assert f"ValueError: {REDACTED}" in caplog.text


def test_unknown_key_not_redacted(caplog: pytest.LogCaptureFixture) -> None:
    """Only keys Home Assistant was given are known; other text passes through."""
    logging.getLogger("aioayla_lan.server").warning("key is %s", LANIP_KEY)

    assert f"key is {LANIP_KEY}" in caplog.text


@pytest.mark.usefixtures(
    "mock_setup_entry",
    "mock_fetch_dsn",
    "mock_source_ip",
    "mock_lan_register",
    "mock_wait_verified",
)
async def test_key_redacted_while_verifying(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A key entered in the config flow is hidden before the unit is contacted."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "local"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.0.2.11", CONF_LANIP_KEY: LANIP_KEY}
    )
    assert result["type"] is FlowResultType.SHOW_PROGRESS

    logging.getLogger("aioayla_lan.device").warning("key is %s", LANIP_KEY)

    assert LANIP_KEY not in caplog.text
    assert f"key is {REDACTED}" in caplog.text


def test_empty_key_not_registered(caplog: pytest.LogCaptureFixture) -> None:
    """An empty key would match between every character of every line."""
    redact_key_in_logs("")

    logging.getLogger("aioayla_lan.device").warning("session established")

    assert KEY_FILTER.keys == set()
    assert "session established" in caplog.text
