"""Tests for the FGLair property encodings."""

from typing import Any

import pytest

from .const import AC_INFO1, AC_INFO1_FROM_20
from custom_components.fglair_local.properties import (
    OpMode,
    Positions,
    decode_adapter_model,
    decode_error_code,
    decode_firmware_version,
    decode_horizontal_positions,
    decode_sensed_temperature,
    decode_setpoint,
    decode_setpoint_limits,
    decode_vertical_positions,
    encode_setpoint,
    raw_int,
)

APP_LIMITS = {
    OpMode.AUTO: (18.0, 30.0),
    OpMode.COOL: (18.0, 30.0),
    OpMode.DRY: (18.0, 30.0),
    OpMode.HEAT: (16.0, 30.0),
}
FIVE = tuple(f"position_{n}" for n in range(1, 6))
THREE = FIVE[:3]


def with_limits(limits: str) -> str:
    """Return the AP-WF3E `ac_info1` with fields 27-32 replaced."""
    return AC_INFO1.replace("180,300,160,300,180,300", limits)


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
    ("ac_info1", "limits"),
    [
        pytest.param(None, APP_LIMITS, id="missing"),
        pytest.param(AC_INFO1, APP_LIMITS, id="ap_wf3e"),
        pytest.param(
            AC_INFO1_FROM_20,
            {
                OpMode.AUTO: (20.0, 30.0),
                OpMode.COOL: (20.0, 30.0),
                OpMode.DRY: (20.0, 30.0),
                OpMode.HEAT: (16.0, 30.0),
            },
            id="from_20",
        ),
        pytest.param(
            with_limits("170,310,150,320,190,290"),
            {
                OpMode.AUTO: (19.0, 29.0),
                OpMode.COOL: (17.0, 31.0),
                OpMode.DRY: (17.0, 31.0),
                OpMode.HEAT: (15.0, 32.0),
            },
            id="each_field",
        ),
        pytest.param(
            with_limits("65535,300,160,65535,200,300"),
            {**APP_LIMITS, OpMode.AUTO: (20.0, 30.0)},
            id="sentinel",
        ),
        pytest.param(
            with_limits("0,300,300,300,200,300"),
            {**APP_LIMITS, OpMode.AUTO: (20.0, 30.0)},
            id="zero_or_empty_range",
        ),
        pytest.param(
            with_limits("310,300,x,300,200,300"),
            {**APP_LIMITS, OpMode.AUTO: (20.0, 30.0)},
            id="inverted_or_garbage",
        ),
        pytest.param(
            with_limits("180,9999,160,400,200,300"),
            {**APP_LIMITS, OpMode.HEAT: (16.0, 40.0), OpMode.AUTO: (20.0, 30.0)},
            id="implausible_max",
        ),
        pytest.param(
            # Cut inside the heat range.
            ",".join(with_limits("200,300,170,300,190,300").split(",")[:30]),
            {**APP_LIMITS, OpMode.COOL: (20.0, 30.0), OpMode.DRY: (20.0, 30.0)},
            id="truncated",
        ),
        pytest.param("garbage", APP_LIMITS, id="garbage"),
    ],
)
def test_decode_setpoint_limits(
    ac_info1: str | None, limits: dict[OpMode, tuple[float, float]]
) -> None:
    """The unit's own range per mode, where valid, overrides the app's.

    Dry always follows cool.
    """
    assert decode_setpoint_limits(ac_info1) == limits


@pytest.mark.parametrize(
    ("num_dir", "labels"),
    [
        pytest.param(4, tuple(f"position_{n}" for n in range(1, 5)), id="four"),
        pytest.param(1, ("position_1",), id="one"),
        pytest.param(15, tuple(f"position_{n}" for n in range(1, 16)), id="fifteen"),
        pytest.param("6", tuple(f"position_{n}" for n in range(1, 7)), id="string"),
        pytest.param(0, (), id="zero"),
        pytest.param(-1, (), id="negative"),
        pytest.param(16, (), id="too_many"),
        pytest.param(65535, (), id="not_applicable"),
        pytest.param(None, (), id="missing"),
    ],
)
def test_decode_vertical_positions(num_dir: Any, labels: tuple[str, ...]) -> None:
    """Vertical positions are numbered from the top, up to 15 of them."""
    assert decode_vertical_positions(num_dir) == Positions(labels)


@pytest.mark.parametrize(
    ("num_dir", "positions"),
    [
        pytest.param(5, Positions(FIVE, reverse=True), id="five_from_right"),
        pytest.param(21, Positions(FIVE), id="five_from_left"),
        pytest.param(3, Positions(THREE, reverse=True), id="three_from_right"),
        pytest.param(19, Positions(THREE), id="three_from_left"),
        pytest.param(2, Positions(FIVE[:2], reverse=True), id="two_from_right"),
        pytest.param(
            31,
            Positions(tuple(f"position_{n}" for n in range(1, 16))),
            id="fifteen_from_left",
        ),
        pytest.param(0, Positions(), id="zero"),
        pytest.param(16, Positions(), id="sixteen"),
        pytest.param(32, Positions(), id="too_many"),
        pytest.param(-1, Positions(), id="negative"),
        pytest.param(65535, Positions(), id="not_applicable"),
        pytest.param(None, Positions(), id="missing"),
    ],
)
def test_decode_horizontal_positions(num_dir: Any, positions: Positions) -> None:
    """1-15 count from the right, 17-31 from the left; labels read left to right."""
    assert decode_horizontal_positions(num_dir) == positions


@pytest.mark.parametrize(
    ("positions", "direction", "label"),
    [
        pytest.param(Positions(FIVE), 1, "position_1", id="from_left_first"),
        pytest.param(Positions(FIVE), 5, "position_5", id="from_left_last"),
        pytest.param(
            Positions(FIVE, reverse=True), 1, "position_5", id="from_right_first"
        ),
        pytest.param(
            Positions(FIVE, reverse=True), 2, "position_4", id="from_right_second"
        ),
        pytest.param(
            Positions(FIVE, reverse=True), 5, "position_1", id="from_right_last"
        ),
        pytest.param(
            Positions(THREE, reverse=True), 3, "position_1", id="three_from_right"
        ),
    ],
)
def test_position_direction_round_trip(
    positions: Positions, direction: int, label: str
) -> None:
    """A direction value and its label map both ways."""
    assert positions.label(direction) == label
    assert positions.direction(label) == direction


@pytest.mark.parametrize(
    ("positions", "direction"),
    [
        pytest.param(Positions(FIVE), 0, id="zero"),
        pytest.param(Positions(FIVE), 6, id="beyond"),
        pytest.param(Positions(FIVE, reverse=True), 6, id="beyond_from_right"),
        pytest.param(Positions(FIVE), None, id="missing"),
        pytest.param(Positions(), 1, id="no_positions"),
    ],
)
def test_position_label_out_of_range(
    positions: Positions, direction: int | None
) -> None:
    """A direction with no position has no label."""
    assert positions.label(direction) is None


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
