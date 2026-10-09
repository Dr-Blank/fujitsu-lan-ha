"""Tests for the FGLair property encodings."""

from typing import Any

import pytest

from custom_components.fglair_local.properties import (
    decode_adapter_model,
    decode_error_code,
    decode_firmware_version,
    decode_sensed_temperature,
    decode_setpoint,
    encode_setpoint,
    raw_int,
)


@pytest.mark.parametrize(
    ("raw", "celsius"),
    [
        pytest.param(7850, 28.5, id="display"),
        pytest.param(8700, 37.0, id="outdoor"),
        pytest.param("8700", 37.0, id="string"),
        pytest.param(4500, -5.0, id="below_zero"),
        pytest.param(65535, None, id="not_applicable"),
        pytest.param(None, None, id="missing"),
        pytest.param("garbage", None, id="garbage"),
    ],
)
def test_decode_sensed_temperature(raw: Any, celsius: float | None) -> None:
    """Room and outdoor readings are offset by 5000 and scaled by 100."""
    assert decode_sensed_temperature(raw) == celsius


@pytest.mark.parametrize(
    ("raw", "celsius"),
    [
        pytest.param(240, 24.0, id="setpoint"),
        pytest.param(245, 24.5, id="half_degree"),
        pytest.param(65535, None, id="not_applicable"),
        pytest.param(0, None, id="off"),
        pytest.param(None, None, id="missing"),
        pytest.param([240], None, id="garbage"),
    ],
)
def test_decode_setpoint(raw: Any, celsius: float | None) -> None:
    """The setpoint is sent as tenths of a degree."""
    assert decode_setpoint(raw) == celsius


@pytest.mark.parametrize(
    ("celsius", "raw"),
    [
        pytest.param(24.0, 240, id="whole"),
        pytest.param(24.5, 245, id="half"),
        pytest.param(16, 160, id="int"),
    ],
)
def test_encode_setpoint(celsius: float, raw: int) -> None:
    """Encoding is the exact inverse of decoding for the setpoint."""
    assert encode_setpoint(celsius) == raw
    assert decode_setpoint(encode_setpoint(celsius)) == celsius


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(3, 3, id="int"),
        pytest.param("3", 3, id="string"),
        pytest.param(65535, None, id="not_applicable"),
        pytest.param(None, None, id="missing"),
        pytest.param("x", None, id="value_error"),
        pytest.param({}, None, id="type_error"),
    ],
)
def test_raw_int(value: Any, expected: int | None) -> None:
    """Raw integers parse leniently and drop the not-applicable sentinel."""
    assert raw_int(value) == expected


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        pytest.param(1, "01", id="one"),
        pytest.param(10, "0A", id="hex_letter_low"),
        pytest.param(11, "0b", id="lower_b"),
        pytest.param(13, "0d", id="lower_d"),
        pytest.param(0xBD, "bd", id="lower_both"),
        pytest.param(159, "9F", id="upper_f"),
        pytest.param(255, "FF", id="largest_short"),
        pytest.param(273, "11.1", id="smallest_long"),
        pytest.param(283, "11.C", id="glyph_c"),
        pytest.param(1574, "62.6", id="outdoor_pcb"),
        pytest.param("1574", "62.6", id="string"),
        pytest.param(0xA11, "A1.1", id="glyph_a"),
        pytest.param(0x100, "10.0", id="long_zero_nibbles"),
        pytest.param(4061, "UJ.J", id="glyph_u_and_j"),
        pytest.param(0xEBE, "PC.P", id="glyph_p"),
        pytest.param(4095, "UU.U", id="largest"),
        pytest.param(0, None, id="no_error"),
        pytest.param(-1, None, id="negative"),
        pytest.param(65535, None, id="not_applicable"),
        pytest.param(None, None, id="missing"),
        pytest.param("garbage", None, id="garbage"),
    ],
)
def test_decode_error_code(raw: Any, code: str | None) -> None:
    """Error codes read as the FGLair app shows them.

    Below 256, two hex digits; from 256, a 7-segment glyph per hex digit.
    """
    assert decode_error_code(raw) == code


@pytest.mark.parametrize(
    ("raw", "version"),
    [
        pytest.param("0.0.1,:,:,:,", "0.0.1", id="padded"),
        pytest.param("0.0.1", "0.0.1", id="bare"),
    ],
)
def test_decode_firmware_version(raw: str, version: str) -> None:
    """The unit pads its firmware version with separators."""
    assert decode_firmware_version(raw) == version


@pytest.mark.parametrize(
    ("model_name", "adapter"),
    [
        pytest.param("30KJTA-B : AP-WF3E", "AP-WF3E", id="indoor_and_adapter"),
        pytest.param("A : B : AP-WF3E ", "AP-WF3E", id="last_part_stripped"),
        pytest.param("E_2026-09-10", None, id="no_adapter"),
        pytest.param("X : ", None, id="blank_adapter"),
        pytest.param("", None, id="empty"),
        pytest.param(None, None, id="missing"),
    ],
)
def test_decode_adapter_model(model_name: str | None, adapter: str | None) -> None:
    """The Wi-Fi adapter is named after the last separator of `model_name`."""
    assert decode_adapter_model(model_name) == adapter
