"""Fujitsu FGLair property encodings.

Encode and decode are separate on purpose: every temperature bug in the
deiger/AirCon add-on came from one "precision" factor applied both ways.
"""

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

ERROR_CODE = "error_code"
OPERATION_SOURCE_ID = "operation_source_id"
HUMAN_DETECTED = "human_det"
POWERFUL_MODE = "powerful_mode"

# Louvre positions by `af_*_direction` value, from 1. Tested on AP-WF3E; the
# unit's `af_horizontal_num_dir` (21) is not the position count.
# Vertical: 1 the highest. AP-WF3E reports 4 positions, ASYG-KMCC 6.
VERTICAL_POSITIONS = tuple(f"position_{n}" for n in range(1, 9))
HORIZONTAL_POSITIONS = ("left", "left_center", "center", "right_center", "right")

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
    "demand_control",
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
    "op_status",
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
    "monitor1",
    "ac_info1",
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
    if (raw := raw_int(value)) is None:
        return None
    return raw / 10


def encode_setpoint(celsius: float) -> int:
    """Setpoint to the wire: °C x 10."""
    return round(celsius * 10)


def decode_firmware_version(value: Any) -> str:
    """Firmware version, without the `,:,:,:,` padding the unit appends."""
    return str(value).rstrip(",:")
