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

from .const import ATTR_COMMAND_ID, ATTR_PIN, ATTR_VIN, DOMAIN, SERVICE_SEND_COMMAND
from .coordinator import CheryEuropeDataUpdateCoordinator
from .entity import CheryEuropeEntity
from .pin import resolve_pin

PARALLEL_UPDATES = 0

CLIMATE_COMMAND_ID = "ve_1104"
MIN_TEMPERATURE = 16
MAX_TEMPERATURE = 30
DEFAULT_TARGET_TEMPERATURE = 22

PIN_SCHEMA = cv.make_entity_service_schema(
    {vol.Optional(ATTR_PIN): vol.All(cv.string, vol.Length(min=1))}
)
TEMPERATURE_PIN_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Optional(ATTR_PIN): vol.All(cv.string, vol.Length(min=1)),
        vol.Required(ATTR_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=16, max=30)
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

    coordinator: CheryEuropeDataUpdateCoordinator = entry.runtime_data
    async_add_entities([CheryEuropeClimate(coordinator, CLIMATE_DESCRIPTION, entry)])


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
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{description.key}_climate"
        self._target_temperature = _api_value(self.chery_data, "target_temperature")
        self._hvac_mode = _initial_hvac_mode(self.chery_data)

    @property
    def min_temp(self) -> float:
        """Return the minimum HVAC temperature supported by the vehicle."""
        value = _api_value(self.chery_data, "min_temperature")
        return float(value) if value is not None else MIN_TEMPERATURE

    @property
    def max_temp(self) -> float:
        """Return the maximum HVAC temperature supported by the vehicle."""
        value = _api_value(self.chery_data, "max_temperature")
        return float(value) if value is not None else MAX_TEMPERATURE

    @property
    def entity_picture(self) -> str | None:
        """Return the vehicle picture from the vehicle list."""
        return self.chery_data.vehicle_picture_url

    def _handle_coordinator_update(self) -> None:
        """Sync local HVAC state when realtime feedback arrives."""
        enabled = _api_value(self.chery_data, "hvac_enabled")
        api_mode = _map_hvac_mode(_api_value(self.chery_data, "hvac_mode"))
        if api_mode is not None:
            self._hvac_mode = api_mode
        elif enabled is True:
            if self._hvac_mode in (None, HVACMode.OFF):
                self._hvac_mode = HVACMode.AUTO
        elif enabled is False:
            self._hvac_mode = HVACMode.OFF
        target = _api_value(self.chery_data, "target_temperature")
        if target is not None:
            self._target_temperature = target
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
        api_mode = _map_hvac_mode(_api_value(self.chery_data, "hvac_mode"))
        if api_mode is not None:
            return api_mode
        enabled = _api_value(self.chery_data, "hvac_enabled")
        if enabled is True:
            if self._hvac_mode in (HVACMode.HEAT, HVACMode.AUTO):
                return self._hvac_mode
            return HVACMode.AUTO
        if enabled is False:
            if self._hvac_mode in (HVACMode.HEAT, HVACMode.AUTO):
                return self._hvac_mode
            return HVACMode.OFF
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
        if self.hvac_mode == HVACMode.OFF:
            self._hvac_mode = HVACMode.AUTO
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on vehicle HVAC using the PIN from the service call."""
        pin = resolve_pin(self._entry, kwargs)
        temperature = self.target_temperature or DEFAULT_TARGET_TEMPERATURE
        await self._send_climate_command(pin, enabled=True, temperature=temperature)
        self._target_temperature = temperature
        self._hvac_mode = HVACMode.AUTO
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off vehicle HVAC using the PIN from the service call."""
        pin = resolve_pin(self._entry, kwargs)
        await self._send_climate_command(
            pin,
            enabled=False,
            temperature=self.target_temperature or DEFAULT_TARGET_TEMPERATURE,
        )
        self._hvac_mode = HVACMode.OFF
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode, **kwargs: Any) -> None:
        """Set HVAC mode using the PIN from the service call."""
        pin = resolve_pin(self._entry, kwargs)
        if hvac_mode == HVACMode.OFF:
            await self._send_climate_command(
                pin,
                enabled=False,
                hvac_mode=hvac_mode.value,
                temperature=self.target_temperature or DEFAULT_TARGET_TEMPERATURE,
            )
        elif hvac_mode in (HVACMode.HEAT, HVACMode.AUTO):
            temperature = self.target_temperature or DEFAULT_TARGET_TEMPERATURE
            await self._send_climate_command(
                pin,
                enabled=True,
                hvac_mode=hvac_mode.value,
                temperature=temperature,
            )
            self._target_temperature = temperature
        else:
            raise HomeAssistantError(f"Unsupported HVAC mode: {hvac_mode}")
        self._hvac_mode = hvac_mode
        self.async_write_ha_state()

    async def _send_climate_command(self, pin: str, **data: Any) -> None:
        """Call the Chery Europe command service without storing the PIN."""
        vin = self.chery_data.vin
        if not vin:
            raise HomeAssistantError("Vehicle VIN is unavailable")

        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_COMMAND,
            {
                ATTR_VIN: vin,
                ATTR_COMMAND_ID: CLIMATE_COMMAND_ID,
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


def _initial_hvac_mode(data: Any) -> HVACMode:
    """Derive the initial HVAC mode from normalized vehicle data."""
    api_mode = _map_hvac_mode(_api_value(data, "hvac_mode"))
    if api_mode is not None:
        return api_mode
    if _api_value(data, "hvac_enabled") is True:
        return HVACMode.AUTO
    return HVACMode.OFF
