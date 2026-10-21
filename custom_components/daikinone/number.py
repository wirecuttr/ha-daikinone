"""Number platform for Daikin One integration."""

import logging

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.daikinone import DOMAIN, DaikinOneData
from custom_components.daikinone.client.models import DaikinThermostat
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.entity import DaikinOneEntity

log = logging.getLogger(__name__)

AUX_HEAT_LOCKOUT_TEMP_DESCRIPTION = NumberEntityDescription(
    key="aux_heat_lockout_temperature",
    name="Aux heat lockout temperature",
    icon="mdi:thermometer",
    device_class=NumberDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    native_step=0.5,
    native_min_value=-23.0,
    native_max_value=22.0,
    entity_category=EntityCategory.CONFIG,
    has_entity_name=True,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Daikin One number entities."""
    data: DaikinOneData = hass.data[DOMAIN]
    thermostats = data.daikin.get_thermostats().values()

    entities: list[NumberEntity] = []
    for thermostat in thermostats:
        if thermostat.aux_heat_lockout_temp is not None:
            entities.append(DaikinOneAuxHeatLockoutTemperatureNumber(data, thermostat))

    async_add_entities(entities, True)


class DaikinOneAuxHeatLockoutTemperatureNumber(DaikinOneEntity[DaikinThermostat], NumberEntity):
    """Number entity to configure the auxiliary heat lockout balance point temperature."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_has_entity_name = True
    _attr_translation_key = "aux_heat_lockout_temperature"

    def __init__(
        self,
        data: DaikinOneData,
        thermostat: DaikinThermostat,
        description: NumberEntityDescription = AUX_HEAT_LOCKOUT_TEMP_DESCRIPTION,
    ) -> None:
        super().__init__(data, thermostat)
        self.entity_description = description

        name = self.entity_description.name or self.name
        match data.entry.data[CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY]:
            case 0:
                self._attr_unique_id = f"{self._device.id}-{name}"
            case 1:
                self._attr_unique_id = f"{self._device.id}-{self.entity_description.key}"
            case _:
                raise ValueError("unexpected entity uid schema version")

        self.update_entity_attributes()

    @property
    def device_name(self) -> str:
        return f"{self._device.name} Thermostat"

    async def async_get_device(self) -> DaikinThermostat:
        return self._data.daikin.get_thermostat(self._device.id)

    def update_entity_attributes(self) -> None:
        """Update the entity attributes."""
        self._attr_native_value = self._device.aux_heat_lockout_temp

    @property
    def native_value(self) -> float | None:
        """Return the auxiliary heat lockout balance point temperature."""
        return self._device.aux_heat_lockout_temp

    @property
    def native_min_value(self) -> float:
        """Return dynamic minimum value, expanding if current value is below lower bound."""
        if self._device.aux_heat_lockout_temp is not None and self._device.aux_heat_lockout_temp < -23.0:
            return self._device.aux_heat_lockout_temp
        return -23.0

    @property
    def native_max_value(self) -> float:
        """Return dynamic maximum value, expanding if current value is above upper bound."""
        if self._device.aux_heat_lockout_temp is not None and self._device.aux_heat_lockout_temp > 22.0:
            return self._device.aux_heat_lockout_temp
        return 22.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the auxiliary heat lockout balance point temperature."""
        self._device.aux_heat_lockout_temp = value
        self.async_write_ha_state()
        await self._data.daikin.set_thermostat_aux_heat_lockout_temp(self._device.id, value)
