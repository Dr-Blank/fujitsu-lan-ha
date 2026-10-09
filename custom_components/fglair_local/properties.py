"""Fujitsu FGLair property encodings.

Encode and decode are separate on purpose: every temperature bug in the
deiger/AirCon add-on came from one "precision" factor applied both ways.
"""

from dataclasses import dataclass
from enum import IntEnum, IntFlag
from typing import Any

NOT_APPLICABLE = 65535

OPERATION_MODE = "operation_mode"
ADJUST_TEMPERATURE = "adjust_temperature"
DISPLAY_TEMPERATURE = "display_temperature"
OUTDOOR_TEMPERATURE = "outdoor_temperature"
FAN_SPEED = "fan_speed"
VERTICAL_SWING = "af_vertical_swing"
HORIZONTAL_SWING = "af_horizontal_swing"
VERTICAL_DIRECTION = "af_vertical_direction"
HORIZONTAL_DIRECTION = "af_horizontal_direction"
VERTICAL_NUM_DIR = "af_vertical_num_dir"
HORIZONTAL_NUM_DIR = "af_horizontal_num_dir"
DEVICE_CAPABILITIES = "device_capabilities"
MODEL_NAME = "model_name"
MCU_FW_VERSION = "mcu_fw_version"
AC_INFO1 = "ac_info1"

ERROR_CODE = "error_code"
OPERATION_SOURCE_ID = "operation_source_id"
HUMAN_DETECTED = "human_det"
OP_STATUS = "op_status"
MONITOR1 = "monitor1"
POWERFUL_MODE = "powerful_mode"
# Set by the unit during a utility demand-response event; the app never writes it.
DEMAND_CONTROL = "demand_control"

# Up to 15 positions per axis, numbered from the top or the left.
# Vertical: AP-WF3E has 4, ASYG-KMCC 6. Horizontal: AP-WF3E has 5.
MAX_POSITIONS = 15
POSITIONS = tuple(f"position_{n}" for n in range(1, MAX_POSITIONS + 1))

# On/off settings. Tested on AP-WF3E: economy_mode, outdoor_low_noise,
# indoor_fan_control and human_det_auto_save.
TOGGLE_PROPERTIES = (
    "economy_mode",
    POWERFUL_MODE,
    "outdoor_low_noise",
    "min_heat",
    "coil_dry_mode",
    "human_det_auto_save",
    "human_det_auto_off",
    "human_det_auto_on_off",
    "wifi_led_enable",
    "indoor_fan_control",
    "external_thermostat_off",
)
# Write-only actions that idle at 0.
RESET_PROPERTIES = ("filter_sign_reset", "cleaning_reset", "side_fan_filter_reset")
# Read-only values the unit reports that nothing else maps.
INFO_PROPERTIES = (
    ERROR_CODE,
    OPERATION_SOURCE_ID,
    HUMAN_DETECTED,
    OP_STATUS,
    DEMAND_CONTROL,
    "system_type",
    "comm_version",
    "oem_host_version",
    "device_name",
    "building_name",
    "auto_save_time",
    "auto_save_set_time",
    "auto_on_off_set_time",
    "auto_off_time",
    "master_timer_on_off_1",
    "master_timer_on_off_2",
    "timer_setting_status_wr",
    "voice_type",
    "test_run",
    "service_function_number",
    "service_function_setting",
    "ota_status2",
    "ota_completed",
    MONITOR1,
    AC_INFO1,
)

# Written as booleans. The unit ignores swing written with any other base_type.
BOOLEAN_PROPERTIES = frozenset({VERTICAL_SWING, HORIZONTAL_SWING, *TOGGLE_PROPERTIES})

PRIME_PROPERTIES = (
    DEVICE_CAPABILITIES,
    MODEL_NAME,
    MCU_FW_VERSION,
    OPERATION_MODE,
    ADJUST_TEMPERATURE,
    DISPLAY_TEMPERATURE,
    OUTDOOR_TEMPERATURE,
    FAN_SPEED,
    VERTICAL_SWING,
    HORIZONTAL_SWING,
    # Before the direction, which reads as off until the count says it exists.
    VERTICAL_NUM_DIR,
    HORIZONTAL_NUM_DIR,
    VERTICAL_DIRECTION,
    HORIZONTAL_DIRECTION,
)
# Re-read after a write: the unit echoes a write only sometimes, and never what
# the write changed elsewhere.
LOUVRE_PROPERTIES = (
    VERTICAL_SWING,
    HORIZONTAL_SWING,
    VERTICAL_DIRECTION,
    HORIZONTAL_DIRECTION,
)
READ_BACK: dict[str, tuple[str, ...]] = {
    POWERFUL_MODE: (FAN_SPEED, ADJUST_TEMPERATURE, *LOUVRE_PROPERTIES),
    OPERATION_MODE: (POWERFUL_MODE, FAN_SPEED, ADJUST_TEMPERATURE, *LOUVRE_PROPERTIES),
    VERTICAL_DIRECTION: (VERTICAL_SWING,),
    HORIZONTAL_DIRECTION: (HORIZONTAL_SWING,),
}

# Read after the prime set, so the entities that matter fill first.
EXTRA_PROPERTIES = (*TOGGLE_PROPERTIES, *RESET_PROPERTIES, *INFO_PROPERTIES)
# Not pushed when they change, so polled. Candidates for what the unit is
# doing: monitor1 field 8 was 1 while the compressor ran (AP-WF3E, one sample).
STATUS_PROPERTIES = (OP_STATUS, MONITOR1)


class OpMode(IntEnum):
    """`operation_mode` values."""

    OFF = 0
    ON = 1
    AUTO = 2
    COOL = 3
    DRY = 4
    FAN = 5
    HEAT = 6


class FanSpeed(IntEnum):
    """`fan_speed` values."""

    QUIET = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    AUTO = 4


class Capability(IntFlag):
    """`device_capabilities` bits."""

    OP_COOL = 1
    OP_DRY = 1 << 1
    OP_FAN = 1 << 2
    OP_HEAT = 1 << 3
    OP_AUTO = 1 << 4
    FAN_AUTO = 1 << 5
    FAN_HIGH = 1 << 6
    FAN_MEDIUM = 1 << 7
    FAN_LOW = 1 << 8
    FAN_QUIET = 1 << 9
    SWING_VERTICAL = 1 << 10
    SWING_HORIZONTAL = 1 << 11
    ECO_MODE = 1 << 12
    OP_MIN_HEAT = 1 << 13
    ENERGY_SWING_FAN = 1 << 14
    POWERFUL_MODE = 1 << 16
    OUTDOOR_LOW_NOISE = 1 << 17
    COIL_DRY = 1 << 18


# Setpoint range in °C per mode, as the FGLair app limits it.
SETPOINT_LIMITS = {
    OpMode.AUTO: (18.0, 30.0),
    OpMode.COOL: (18.0, 30.0),
    OpMode.DRY: (18.0, 30.0),
    OpMode.HEAT: (16.0, 30.0),
}
# `ac_info1` field of each mode's minimum, followed by its maximum. Seen as
# 180,300,160,300,180,300 on AP-WF3E; only heat differs, so cool and auto may be swapped.
AC_INFO1_SETPOINT_FIELDS = {OpMode.COOL: 27, OpMode.HEAT: 29, OpMode.AUTO: 31}
# Highest plausible `ac_info1` limit, °C x 10; anything above is a bad field.
MAX_SETPOINT = 400

# Display glyph of each nibble of an error code from 256 up.
SEVEN_SEGMENT = "0123456789ACFJPU"


def is_reported(value: Any) -> bool:
    """Whether the unit gave a real value, not nothing or the sentinel."""
    return value is not None and str(value) != str(NOT_APPLICABLE)


def is_numeric(value: Any) -> bool:
    """Whether the unit gave a real integer value."""
    return raw_int(value) is not None


def raw_int(value: Any) -> int | None:
    """Parse a raw integer, mapping the not-applicable sentinel to None."""
    if value is None:
        return None
    try:
        parsed = int(value)
    except TypeError, ValueError:
        return None
    return None if parsed == NOT_APPLICABLE else parsed


def decode_sensed_temperature(value: Any) -> float | None:
    """Room and outdoor temperature: `(v - 5000) / 100` °C."""
    if (raw := raw_int(value)) is None:
        return None
    return (raw - 5000) / 100


def decode_setpoint(value: Any) -> float | None:
    """Setpoint: °C x 10."""
    # Units report 0 while off.
    if not (raw := raw_int(value)):
        return None
    return raw / 10


def encode_setpoint(celsius: float) -> int:
    """Setpoint to the wire: °C x 10."""
    return round(celsius * 10)


def decode_setpoint_limits(ac_info1: Any) -> dict[OpMode, tuple[float, float]]:
    """Setpoint range in °C per mode: the unit's own from `ac_info1`, else the app's."""
    limits = dict(SETPOINT_LIMITS)
    fields = [] if ac_info1 is None else str(ac_info1).split(",")
    for mode, index in AC_INFO1_SETPOINT_FIELDS.items():
        if index + 1 >= len(fields):
            continue
        low, high = raw_int(fields[index]), raw_int(fields[index + 1])
        if low is not None and high is not None and 0 < low < high <= MAX_SETPOINT:
            limits[mode] = (low / 10, high / 10)
    limits[OpMode.DRY] = limits[OpMode.COOL]
    return limits


def decode_error_code(value: Any) -> str | None:
    """Error code as the FGLair app shows it: 11 is `0b`, 1574 (0x626) is `62.6`.

    Below 256, two hex digits with b and d lower case. From 256, a 7-segment
    glyph per nibble, the last one after the dot. 0 means no error.
    """
    if (raw := raw_int(value)) is None or raw <= 0:
        return None
    if raw < 0x100:
        return f"{raw:02X}".replace("B", "b").replace("D", "d")
    return (
        f"{SEVEN_SEGMENT[(raw >> 8) & 0xF]}{SEVEN_SEGMENT[(raw >> 4) & 0xF]}"
        f".{SEVEN_SEGMENT[raw & 0xF]}"
    )


@dataclass(frozen=True)
class Positions:
    """Louvre positions in display order, and their `af_*_direction` values."""

    labels: tuple[str, ...] = ()
    # Direction 1 is the last label: horizontal louvres counted from the right.
    reverse: bool = False

    def label(self, direction: int | None) -> str | None:
        """Label of a direction value, None when out of range."""
        if direction is None or not 1 <= direction <= len(self.labels):
            return None
        return self.labels[-direction if self.reverse else direction - 1]

    def direction(self, label: str) -> int:
        """Direction value of a label."""
        index = self.labels.index(label)
        return len(self.labels) - index if self.reverse else index + 1


def decode_vertical_positions(num_dir: Any) -> Positions:
    """Vertical positions from `af_vertical_num_dir`: the count, from the top."""
    if (count := raw_int(num_dir)) is None or not 1 <= count <= MAX_POSITIONS:
        return Positions()
    return Positions(POSITIONS[:count])


def decode_horizontal_positions(num_dir: Any) -> Positions:
    """Horizontal positions from `af_horizontal_num_dir`, from the left.

    1-15: that many, direction 1 on the right. 17-31: n - 16, direction 1 on
    the left (AP-WF3E reports 21). Anything else: none.
    """
    if (raw := raw_int(num_dir)) is None:
        return Positions()
    if 1 <= raw <= MAX_POSITIONS:
        count, reverse = raw, True
    elif 17 <= raw <= 16 + MAX_POSITIONS:
        count, reverse = raw - 16, False
    else:
        return Positions()
    return Positions(POSITIONS[:count], reverse)


def decode_firmware_version(value: Any) -> str:
    """Firmware version, without the `,:,:,:,` padding the unit appends."""
    return str(value).rstrip(",:")


# Adapters seen to stop answering on the LAN until the unit is power-cycled.
HANGING_ADAPTERS = frozenset({"AP-WF3E"})


def decode_adapter_model(model_name: Any) -> str | None:
    """Wi-Fi adapter model, from a `model_name` such as `30KJTA-B : AP-WF3E`."""
    _, sep, adapter = str(model_name).rpartition(" : ")
    if not sep:
        return None
    return adapter.strip() or None
