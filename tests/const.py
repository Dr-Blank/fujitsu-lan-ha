"""Shared constants for the Fujitsu FGLair Local tests."""

from homeassistant.const import CONF_HOST

from custom_components.fglair_local.const import (
    CONF_CALLBACK_HOST,
    CONF_CALLBACK_PORT,
    CONF_DSN,
    CONF_LANIP_KEY,
    CONF_LANIP_KEY_ID,
)

DSN = "AC000W000000001"
LANIP_KEY = "0123456789abcdef0123456789abcdef"
LANIP_KEY_ID = 1234
# The aiohttp test client always connects from loopback, and the server only
# answers the configured unit's address.
HOST = "127.0.0.1"
CALLBACK_HOST = "192.0.2.2"
CALLBACK_PORT = 8123
# Where the cloud says the unit is, for config flow tests.
CLOUD_HOST = "192.0.2.10"
PRODUCT_NAME = "Living room"

ENTRY_DATA = {
    CONF_HOST: HOST,
    CONF_DSN: DSN,
    CONF_LANIP_KEY: LANIP_KEY,
    CONF_LANIP_KEY_ID: LANIP_KEY_ID,
    CONF_CALLBACK_HOST: CALLBACK_HOST,
    CONF_CALLBACK_PORT: CALLBACK_PORT,
}

CLIMATE_ENTITY_ID = "climate.air_conditioner"
OUTDOOR_ENTITY_ID = "sensor.air_conditioner_outdoor_temperature"
ECONOMY_ENTITY_ID = "switch.air_conditioner_economy"
REFRESH_ENTITY_ID = "button.air_conditioner_re_read_all_properties"
OCCUPANCY_ENTITY_ID = "binary_sensor.air_conditioner_occupancy"
PROBLEM_ENTITY_ID = "binary_sensor.air_conditioner_problem"
ERROR_CODE_ENTITY_ID = "sensor.air_conditioner_error_code"

# Raw values from a live capture of a unit cooling at 24 °C.
UNIT_DATAPOINTS = {
    "operation_mode": 3,
    "adjust_temperature": 240,
    "display_temperature": 7850,
    "outdoor_temperature": 8700,
    "fan_speed": 4,
    "device_capabilities": 229375,
    "af_vertical_swing": 1,
    "af_horizontal_swing": 0,
    "af_vertical_direction": 1,
    "af_vertical_num_dir": 4,
    "af_horizontal_direction": 5,
    "af_horizontal_num_dir": 21,
    "economy_mode": 0,
    "powerful_mode": 0,
    "outdoor_low_noise": 0,
    "min_heat": 0,
    "human_det": 1,
    "filter_sign_reset": 0,
    "error_code": 0,
    "operation_source_id": 2,
    # Not applicable to this model, so no entity is created for it.
    "anti_freeze": 65535,
}
