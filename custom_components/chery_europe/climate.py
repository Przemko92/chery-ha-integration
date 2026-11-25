import time
from typing import Any

import voluptuous as vol
from homeassistant.components.climate import ClimateEntity, ClimateEntityDescription
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback, async_get_current_platform

from .const import (
    ATTR_COMMAND_ID,
    ATTR_PIN,
    CLIMATE,
    DOMAIN,
    SERVICE_SEND_COMMAND,
)
from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import HI_SETPOINT, climate_at_hi
from .entity import (
    CheryEuropeEntity,
    async_remove_unsupported,
    control_permissions,
    iter_entry_coordinators,
    keep_feature,
    stable_unique_id,
    vehicle_uid,
)
from .permissions import allowed, category_denied
from .pin import resolve_pin

PARALLEL_UPDATES = 0

CLIMATE_COMMAND_ID = "ve_1104"
HEATING_COMMAND_ID = "ve_1110"
_HEATER_ATTRS: tuple[str, ...] = (
    "front_windshield_heating",
    "rear_window_defrost",
    "steering_wheel_heating",
    "driver_seat_heating",
    "passenger_seat_heating",
    "rear_left_seat_heating",
    "rear_right_seat_heating",
)
# 15 °C and 31 °C are the car's LO and HI setpoints. The vehicle list often
# reports a narrower everyday range (16–30); those two ends still work.
MIN_TEMPERATURE = 15
MAX_TEMPERATURE = 31
DEFAULT_TARGET_TEMPERATURE = 22
# Hold requested mode briefly while waiting for car telemetry to reflect it.
OPTIMISTIC_WINDOW_SECONDS = 45.0

PIN_SCHEMA = cv.make_entity_service_schema(
    {vol.Optional(ATTR_PIN): vol.All(cv.string, vol.Length(min=1))}
)
TEMPERATURE_PIN_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Optional(ATTR_PIN): vol.All(cv.string, vol.Length(min=1)),
        vol.Required(ATTR_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=MIN_TEMPERATURE, max=MAX_TEMPERATURE)
        ),
    }
)

CLIMATE_DESCRIPTION = ClimateEntityDescription(
    key="hvac",
    name="HVAC",
    translation_key="hvac",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Chery Europe climate entity from a config entry."""
    platform = async_get_current_platform()
    platform.async_register_entity_service(
        "set_temperature",
        TEMPERATURE_PIN_SCHEMA,
        "async_set_temperature",
        supports_response=SupportsResponse.NONE,
    )
    platform.async_register_entity_service(
        "turn_on",
        PIN_SCHEMA,
        "async_turn_on",
        supports_response=SupportsResponse.NONE,
    )
    platform.async_register_entity_service(
        "turn_off",
        PIN_SCHEMA,
        "async_turn_off",
        supports_response=SupportsResponse.NONE,
    )

    removed: list[str] = []
    entities = []
    for coordinator in iter_entry_coordinators(entry):
        perms = control_permissions(coordinator)
        vin = vehicle_uid(coordinator, entry)
        if keep_feature(perms, CLIMATE_DESCRIPTION.key, f"{vin}_hvac_climate", removed):
            entities.append(CheryEuropeClimate(coordinator, CLIMATE_DESCRIPTION, entry))
    async_add_entities(entities)
    async_remove_unsupported(hass, CLIMATE, removed)


class CheryEuropeClimate(CheryEuropeEntity, ClimateEntity):
    """Representation of Chery Europe vehicle HVAC."""

    entity_description: ClimateEntityDescription
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]
    _attr_min_temp = MIN_TEMPERATURE
    _attr_max_temp = MAX_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: ClimateEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, description, entry)
        self._attr_translation_key = description.translation_key
        self._attr_unique_id = stable_unique_id(entry, f"{description.key}_climate", coordinator)
        self._target_temperature = _api_value(self.chery_data, "target_temperature")
        self._auto_temperature = _non_hi_temperature(self._target_temperature)
        self._hvac_mode = _initial_hvac_mode(self.chery_data)
        self._optimistic_mode: HVACMode | None = None
        self._optimistic_until: float = 0.0
        self._optimistic_data: Any = None

    @property
    def min_temp(self) -> float:
        """Return LO, even when the vehicle list only advertises 16 °C."""
        value = _api_value(self.chery_data, "min_temperature")
        reported = float(value) if value is not None else MIN_TEMPERATURE
        return min(reported, float(MIN_TEMPERATURE))

    @property
    def max_temp(self) -> float:
        """Return HI, even when the vehicle list only advertises 30 °C."""
        value = _api_value(self.chery_data, "max_temperature")
        reported = float(value) if value is not None else MAX_TEMPERATURE
        return max(reported, float(MAX_TEMPERATURE))

    @property
    def entity_picture(self) -> str | None:
        """Return the vehicle picture from the vehicle list."""
        return self.chery_data.vehicle_picture_url

    def _set_optimistic_mode(self, mode: HVACMode) -> None:
        """Hold the requested mode briefly while waiting for car telemetry to catch up."""
        self._hvac_mode = mode
        self._optimistic_mode = mode
        self._optimistic_until = time.monotonic() + OPTIMISTIC_WINDOW_SECONDS
        self._optimistic_data = self.chery_data

    def _active_optimistic_mode(self, enabled: bool | None) -> HVACMode | None:
        """Return optimistic mode while active, clearing it once confirmed or expired."""
        if self._optimistic_mode is None:
            return None
        if time.monotonic() >= self._optimistic_until:
            self._optimistic_mode = None
            self._optimistic_data = None
            return None
        if self.chery_data is self._optimistic_data:
            return self._optimistic_mode
        if self._optimistic_mode == HVACMode.OFF:
            confirmed = enabled is False
        elif self._optimistic_mode == HVACMode.HEAT:
            confirmed = enabled is True and climate_at_hi(self.chery_data) is True
        else:
            confirmed = enabled is True and climate_at_hi(self.chery_data) is not True
        if confirmed:
            self._optimistic_mode = None
            self._optimistic_data = None
            return None
        return self._optimistic_mode

    def _handle_coordinator_update(self) -> None:
        """Sync local HVAC state when realtime feedback arrives."""
        enabled = _api_value(self.chery_data, "hvac_enabled")
        api_mode = _map_hvac_mode(_api_value(self.chery_data, "hvac_mode"))
        optimistic = self._active_optimistic_mode(enabled)
        if optimistic is not None:
            self._hvac_mode = optimistic
        elif enabled is False:
            self._hvac_mode = HVACMode.OFF
        elif enabled is True:
            if climate_at_hi(self.chery_data) is True:
                self._hvac_mode = HVACMode.HEAT
            elif api_mode in (HVACMode.HEAT, HVACMode.AUTO):
                self._hvac_mode = api_mode
            elif self._hvac_mode in (None, HVACMode.OFF):
                self._hvac_mode = HVACMode.AUTO
        elif api_mode is not None:
            self._hvac_mode = api_mode
        target = _api_value(self.chery_data, "target_temperature")
        if target is not None:
            self._target_temperature = target
            if float(target) < HI_SETPOINT - 0.5:
                self._auto_temperature = float(target)
        super()._handle_coordinator_update()

    @property
    def current_temperature(self) -> float | None:  # type: ignore[reportIncompatibleVariableOverride]
        """Return interior temperature from coordinator data."""
        return self.chery_data.interior_temperature

    @property
    def target_temperature(self) -> float | None:  # type: ignore[reportIncompatibleVariableOverride]
        """Return the target temperature from API data or last set value."""
        return _api_value(self.chery_data, "target_temperature") or self._target_temperature

    @property
    def hvac_mode(self) -> HVACMode:  # type: ignore[reportIncompatibleVariableOverride]
        """Return HVAC mode mapped from API data, falling back to last command."""
        enabled = _api_value(self.chery_data, "hvac_enabled")
        optimistic = self._active_optimistic_mode(enabled)
        if optimistic is not None:
            return optimistic
        if enabled is False:
            return HVACMode.OFF
        api_mode = _map_hvac_mode(_api_value(self.chery_data, "hvac_mode"))
        if enabled is True:
            if climate_at_hi(self.chery_data) is True:
                return HVACMode.HEAT
            if api_mode in (HVACMode.HEAT, HVACMode.AUTO):
                return api_mode
            if self._hvac_mode in (HVACMode.HEAT, HVACMode.AUTO):
                return self._hvac_mode
            return HVACMode.AUTO
        if api_mode is not None:
            return api_mode
        return self._hvac_mode or HVACMode.OFF

    @property
    def available(self) -> bool:  # type: ignore[reportIncompatibleVariableOverride]
        """Return if climate data is available."""
        return self.coordinator.data is not None and super().available

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set HVAC target temperature using the PIN from the service call."""
        pin = resolve_pin(self._entry, kwargs)
        temperature = float(kwargs[ATTR_TEMPERATURE])
        await self._send_climate_command(pin, temperature=temperature, enabled=True)
        self._target_temperature = temperature
        if temperature < HI_SETPOINT - 0.5:
            self._auto_temperature = temperature
        if self.hvac_mode == HVACMode.OFF:
            self._set_optimistic_mode(HVACMode.AUTO)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on vehicle HVAC using the PIN from the service call."""
        pin = resolve_pin(self._entry, kwargs)
        temperature = self._auto_temperature
        await self._send_climate_command(pin, enabled=True, temperature=temperature)
        self._target_temperature = temperature
        self._set_optimistic_mode(HVACMode.AUTO)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off vehicle HVAC and active cabin heaters/coolers."""
        pin = resolve_pin(self._entry, kwargs)
        await self._async_turn_off_all(pin, include_mode=False)
        self._set_optimistic_mode(HVACMode.OFF)
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode, **kwargs: Any) -> None:
        """Set HVAC mode using the PIN from the service call."""
        pin = resolve_pin(self._entry, kwargs)
        if hvac_mode == HVACMode.OFF:
            await self._async_turn_off_all(pin, include_mode=True)
        elif hvac_mode == HVACMode.HEAT:
            await self._send_climate_command(
                pin,
                command_id=HEATING_COMMAND_ID,
                enabled=True,
                hvac_mode=hvac_mode.value,
                temperature=self.max_temp,
            )
            self._target_temperature = self.max_temp
        elif hvac_mode == HVACMode.AUTO:
            temperature = self._auto_temperature
            perms = control_permissions(self.coordinator)
            any_heater_on = self.hvac_mode == HVACMode.HEAT or any(
                _api_value(self.chery_data, attr) is True for attr in _HEATER_ATTRS
            )
            use_heating_clear = (
                any_heater_on
                and not category_denied("heatingControl", perms)
                and allowed(perms, 2093)
            )
            await self._send_climate_command(
                pin,
                command_id=HEATING_COMMAND_ID if use_heating_clear else CLIMATE_COMMAND_ID,
                enabled=True,
                hvac_mode=hvac_mode.value,
                temperature=temperature,
            )
            self._target_temperature = temperature
        else:
            raise HomeAssistantError(f"Unsupported HVAC mode: {hvac_mode}")
        self._set_optimistic_mode(hvac_mode)
        self.async_write_ha_state()

    async def _async_turn_off_all(self, pin: str, *, include_mode: bool) -> None:
        """Turn off HVAC (and heaters via heatingControl when any heater is active)."""
        perms = control_permissions(self.coordinator)
        any_heater_on = self.hvac_mode == HVACMode.HEAT or any(
            _api_value(self.chery_data, attr) is True for attr in _HEATER_ATTRS
        )
        use_heating_off = (
            any_heater_on
            and not category_denied("heatingControl", perms)
            and allowed(perms, 2093)
        )
        extra: dict[str, Any] = {"hvac_mode": HVACMode.OFF.value} if include_mode else {}
        if use_heating_off:
            await self._send_climate_command(
                pin,
                command_id=HEATING_COMMAND_ID,
                enabled=False,
                temperature=self.max_temp,
                **extra,
            )
        else:
            await self._send_climate_command(
                pin,
                command_id=CLIMATE_COMMAND_ID,
                enabled=False,
                temperature=self.target_temperature or DEFAULT_TARGET_TEMPERATURE,
                **extra,
            )

    async def _send_climate_command(
        self,
        pin: str,
        *,
        command_id: str = CLIMATE_COMMAND_ID,
        **data: Any,
    ) -> None:
        """Call the Chery Europe command service without storing the PIN."""
        if not self.chery_data.vin:
            raise HomeAssistantError("Vehicle is unavailable")

        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_COMMAND,
            {
                ATTR_COMMAND_ID: command_id,
                ATTR_PIN: pin,
                **data,
            },
            blocking=True,
        )


def _api_value(data: Any, key: str) -> Any:
    """Return optional future API fields without requiring data model support yet."""
    return getattr(data, key, None)


def _map_hvac_mode(value: Any) -> HVACMode | None:
    """Map API HVAC values to Home Assistant modes."""
    if value is None:
        return None
    if isinstance(value, HVACMode):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"off", "false", "0", "disabled"}:
        return HVACMode.OFF
    if normalized in {"heat", "heating"}:
        return HVACMode.HEAT
    if normalized in {"auto", "on", "true", "1", "enabled"}:
        return HVACMode.AUTO
    return None


def _non_hi_temperature(value: Any) -> float:
    """Return a normal Auto setpoint, never carrying over HI (31 °C) from Heat."""
    if value is not None:
        try:
            temp = float(value)
        except (TypeError, ValueError):
            temp = float(DEFAULT_TARGET_TEMPERATURE)
        if temp < HI_SETPOINT - 0.5:
            return temp
    return float(DEFAULT_TARGET_TEMPERATURE)


def _active_hvac_mode(data: Any) -> HVACMode:
    """Return HEAT when telemetry shows HVAC running at HI, otherwise AUTO."""
    if data is not None and climate_at_hi(data) is True:
        return HVACMode.HEAT
    return HVACMode.AUTO


def _initial_hvac_mode(data: Any) -> HVACMode:
    """Derive the initial HVAC mode from normalized vehicle data."""
    api_mode = _map_hvac_mode(_api_value(data, "hvac_mode"))
    if api_mode is not None:
        return api_mode
    if _api_value(data, "hvac_enabled") is True:
        return _active_hvac_mode(data)
    return HVACMode.OFF
