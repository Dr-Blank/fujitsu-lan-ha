"""Climate entity for Fujitsu FGLair Local."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    SWING_HORIZONTAL_OFF,
    SWING_HORIZONTAL_ON,
    SWING_OFF,
    SWING_ON,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FglairLocalConfigEntry, FglairLocalDevice
from .entity import FglairLocalEntity
from .properties import (
    ADJUST_TEMPERATURE,
    DEVICE_CAPABILITIES,
    DISPLAY_TEMPERATURE,
    FAN_SPEED,
    HORIZONTAL_DIRECTION,
    HORIZONTAL_POSITIONS,
    HORIZONTAL_SWING,
    NUMBERED_POSITIONS,
    OPERATION_MODE,
    VERTICAL_DIRECTION,
    VERTICAL_NUM_DIR,
    VERTICAL_POSITIONS,
    VERTICAL_SWING,
    Capability,
    FanSpeed,
    OpMode,
    decode_sensed_temperature,
    decode_setpoint,
    encode_setpoint,
    raw_int,
)

FAN_QUIET = "quiet"

HVAC_TO_OP = {
    HVACMode.OFF: OpMode.OFF,
    HVACMode.COOL: OpMode.COOL,
    HVACMode.DRY: OpMode.DRY,
    HVACMode.FAN_ONLY: OpMode.FAN,
    HVACMode.HEAT: OpMode.HEAT,
    HVACMode.HEAT_COOL: OpMode.AUTO,
}
OP_TO_HVAC = {op: mode for mode, op in HVAC_TO_OP.items()}
HVAC_CAPABILITY = {
    HVACMode.COOL: Capability.OP_COOL,
    HVACMode.DRY: Capability.OP_DRY,
    HVACMode.FAN_ONLY: Capability.OP_FAN,
    HVACMode.HEAT: Capability.OP_HEAT,
    HVACMode.HEAT_COOL: Capability.OP_AUTO,
}

FAN_TO_SPEED = {
    FAN_QUIET: FanSpeed.QUIET,
    FAN_LOW: FanSpeed.LOW,
    FAN_MEDIUM: FanSpeed.MEDIUM,
    FAN_HIGH: FanSpeed.HIGH,
    FAN_AUTO: FanSpeed.AUTO,
}
SPEED_TO_FAN = {speed: fan for fan, speed in FAN_TO_SPEED.items()}
FAN_CAPABILITY = {
    FAN_QUIET: Capability.FAN_QUIET,
    FAN_LOW: Capability.FAN_LOW,
    FAN_MEDIUM: Capability.FAN_MEDIUM,
    FAN_HIGH: Capability.FAN_HIGH,
    FAN_AUTO: Capability.FAN_AUTO,
}

BASE_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)


@dataclass(frozen=True)
class Louvre:
    """One swing axis: swinging, or held at a numbered position."""

    swing: str
    direction: str
    positions: tuple[str, ...]
    capability: Capability
    on_mode: str
    off_mode: str
    # Property holding how many positions this model has, when it is truthful.
    count: str | None = None
    # Offered instead of `positions` for a plausible `count` other than theirs.
    numbered: tuple[str, ...] = ()


VERTICAL = Louvre(
    VERTICAL_SWING,
    VERTICAL_DIRECTION,
    VERTICAL_POSITIONS,
    Capability.SWING_VERTICAL,
    SWING_ON,
    SWING_OFF,
    VERTICAL_NUM_DIR,
    NUMBERED_POSITIONS,
)
HORIZONTAL = Louvre(
    HORIZONTAL_SWING,
    HORIZONTAL_DIRECTION,
    HORIZONTAL_POSITIONS,
    Capability.SWING_HORIZONTAL,
    SWING_HORIZONTAL_ON,
    SWING_HORIZONTAL_OFF,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FglairLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the climate entity."""
    async_add_entities([FglairLocalClimate(entry.runtime_data)])


class FglairLocalClimate(FglairLocalEntity, ClimateEntity):
    """The air conditioner."""

    _attr_name = None
    _attr_translation_key = "air_conditioner"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 16
    _attr_max_temp = 30

    def __init__(self, device: FglairLocalDevice) -> None:
        """Initialise."""
        super().__init__(device)
        self._attr_unique_id = device.dsn

    def _value(self, name: str) -> int | None:
        return raw_int(self.device.values.get(name))

    def _capabilities(self) -> Capability | None:
        raw = self._value(DEVICE_CAPABILITIES)
        return None if raw is None else Capability(raw)

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Modes the unit reports it supports."""
        caps = self._capabilities()
        return [HVACMode.OFF] + [
            mode for mode, bit in HVAC_CAPABILITY.items() if caps is None or bit in caps
        ]

    @property
    def fan_modes(self) -> list[str]:
        """Fan speeds the unit reports it supports."""
        caps = self._capabilities()
        return [
            fan for fan, bit in FAN_CAPABILITY.items() if caps is None or bit in caps
        ]

    def _has(self, louvre: Louvre) -> bool:
        if (caps := self._capabilities()) is None:
            # Unknown capabilities: offer only an axis the unit has reported.
            return self._value(louvre.swing) is not None
        return louvre.capability in caps

    def _positions(self, louvre: Louvre) -> tuple[str, ...]:
        if louvre.count is None:
            return louvre.positions
        count = self._value(louvre.count)
        if (
            count is None
            or count == len(louvre.positions)
            or not 1 <= count <= len(louvre.numbered)
        ):
            return louvre.positions
        return louvre.numbered[:count]

    def _modes(self, louvre: Louvre) -> list[str] | None:
        if not self._has(louvre):
            return None
        return [louvre.on_mode, louvre.off_mode, *self._positions(louvre)]

    def _louvre_mode(self, louvre: Louvre) -> str | None:
        if (swing := self._value(louvre.swing)) is None:
            return None
        if swing:
            return louvre.on_mode
        positions = self._positions(louvre)
        position = self._value(louvre.direction)
        if position is None or not 1 <= position <= len(positions):
            return louvre.off_mode
        return positions[position - 1]

    def _set_louvre(self, louvre: Louvre, mode: str) -> None:
        if mode == louvre.on_mode:
            self.device.set_property(louvre.swing, 1)
            return
        if mode == louvre.off_mode:
            self.device.set_property(louvre.swing, 0)
            return
        # Swing first: the position is where the louvre should end up.
        self.device.set_property(louvre.swing, 0, notify=False)
        self.device.set_property(
            louvre.direction, self._positions(louvre).index(mode) + 1
        )

    @property
    def swing_modes(self) -> list[str] | None:
        """Swing, stop, or hold a vertical position."""
        return self._modes(VERTICAL)

    @property
    def swing_horizontal_modes(self) -> list[str] | None:
        """Swing, stop, or hold a horizontal position."""
        return self._modes(HORIZONTAL)

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Swing is offered per axis the unit has."""
        features = BASE_FEATURES
        if self._has(VERTICAL):
            features |= ClimateEntityFeature.SWING_MODE
        if self._has(HORIZONTAL):
            features |= ClimateEntityFeature.SWING_HORIZONTAL_MODE
        return features

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Current mode."""
        if (raw := self._value(OPERATION_MODE)) is None:
            return None
        return OP_TO_HVAC.get(OpMode(raw)) if raw in OpMode else None

    @property
    def target_temperature(self) -> float | None:
        """Setpoint."""
        return decode_setpoint(self.device.values.get(ADJUST_TEMPERATURE))

    @property
    def current_temperature(self) -> float | None:
        """Room temperature."""
        return decode_sensed_temperature(self.device.values.get(DISPLAY_TEMPERATURE))

    @property
    def fan_mode(self) -> str | None:
        """Current fan speed."""
        raw = self._value(FAN_SPEED)
        if raw is None or raw not in FanSpeed:
            return None
        return SPEED_TO_FAN[FanSpeed(raw)]

    @property
    def swing_mode(self) -> str | None:
        """Vertical swing, or the vertical position."""
        return self._louvre_mode(VERTICAL)

    @property
    def swing_horizontal_mode(self) -> str | None:
        """Horizontal swing, or the horizontal position."""
        return self._louvre_mode(HORIZONTAL)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the mode."""
        self.device.set_property(OPERATION_MODE, HVAC_TO_OP[hvac_mode])

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the setpoint, and the mode when given."""
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self.async_handle_set_hvac_mode_service(hvac_mode)
        self.device.set_property(
            ADJUST_TEMPERATURE, encode_setpoint(kwargs[ATTR_TEMPERATURE])
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan speed."""
        self.device.set_property(FAN_SPEED, FAN_TO_SPEED[fan_mode])

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Swing vertically, or hold a vertical position."""
        self._set_louvre(VERTICAL, swing_mode)

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        """Swing horizontally, or hold a horizontal position."""
        self._set_louvre(HORIZONTAL, swing_horizontal_mode)

    async def async_turn_on(self) -> None:
        """Resume the last mode."""
        # ON has no HVAC mode; the unit pushes the mode it resumes.
        self.device.set_property(OPERATION_MODE, OpMode.ON, optimistic=False)
