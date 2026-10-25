"""Number platform for Daikin One thermostat configuration and calibration."""

import asyncio

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.daikinone import DOMAIN, DaikinOneData
from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.models import DaikinThermostat
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.entity import DaikinOneEntity

DEBOUNCE_DELAY = 0.8
MIN_BALANCE_POINT = -23.0
MAX_BALANCE_POINT = 22.0

DUAL_FUEL_BALANCE_POINT_DESCRIPTION = NumberEntityDescription(
    key="dual_fuel_balance_point",
    name="Dual fuel balance point",
    icon="mdi:thermometer",
    device_class=NumberDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    native_step=0.5,
    native_min_value=MIN_BALANCE_POINT,
    native_max_value=MAX_BALANCE_POINT,
    entity_category=EntityCategory.CONFIG,
    has_entity_name=True,
    mode=NumberMode.BOX,
)

TEMPERATURE_OFFSET_DESCRIPTION = NumberEntityDescription(
    key="temperature_offset",
    name="Temperature offset",
    icon="mdi:thermometer",
    device_class=NumberDeviceClass.TEMPERATURE_DELTA,
    entity_category=EntityCategory.CONFIG,
    has_entity_name=True,
    mode=NumberMode.BOX,
)

HUMIDITY_OFFSET_DESCRIPTION = NumberEntityDescription(
    key="humidity_offset",
    name="Humidity offset",
    icon="mdi:water-percent",
    device_class=NumberDeviceClass.HUMIDITY,
    native_unit_of_measurement=PERCENTAGE,
    native_min_value=-15.0,
    native_max_value=15.0,
    native_step=1.0,
    entity_category=EntityCategory.CONFIG,
    has_entity_name=True,
    mode=NumberMode.SLIDER,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Daikin One number entities."""
    data: DaikinOneData = hass.data[DOMAIN]
    entities: list[NumberEntity] = []

    for thermostat in data.daikin.get_thermostats().values():
        if thermostat.aux_heat_lockout_temp is not None:
            entities.append(DaikinOneDualFuelBalancePointNumber(data, thermostat))
        if thermostat.temp_offset is not None:
            entities.append(DaikinTemperatureOffsetNumber(data, thermostat))
        if thermostat.hum_offset is not None:
            entities.append(DaikinHumidityOffsetNumber(data, thermostat))

    async_add_entities(entities, True)


class DaikinOneDualFuelBalancePointNumber(DaikinOneEntity[DaikinThermostat], NumberEntity):
    """Control the auxiliary heat lockout balance point temperature."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_translation_key = "dual_fuel_balance_point"

    def __init__(
        self,
        data: DaikinOneData,
        thermostat: DaikinThermostat,
        description: NumberEntityDescription = DUAL_FUEL_BALANCE_POINT_DESCRIPTION,
    ) -> None:
        super().__init__(data, thermostat)
        self.entity_description = description
        self._debounce_timer: asyncio.TimerHandle | None = None
        self._target_value: float | None = None

        match data.entry.data[CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY]:
            case 0:
                legacy_name = self.entity_description.name or self.name
                self._attr_unique_id = f"{self._device.id}-{legacy_name}"
            case 1:
                self._attr_unique_id = f"{self._device.id}-{self.entity_description.key}"
            case _:
                raise ValueError("unexpected entity uid schema version")

        self.update_entity_attributes()

    @property
    def device_name(self) -> str:
        return f"{self._device.name} Thermostat"

    @property
    def native_value(self) -> float | None:
        return self._device.aux_heat_lockout_temp

    @property
    def native_min_value(self) -> float:
        value = self._device.aux_heat_lockout_temp
        return min(value, MIN_BALANCE_POINT) if value is not None else MIN_BALANCE_POINT

    @property
    def native_max_value(self) -> float:
        value = self._device.aux_heat_lockout_temp
        return max(value, MAX_BALANCE_POINT) if value is not None else MAX_BALANCE_POINT

    async def async_get_device(self) -> DaikinThermostat:
        return self._data.daikin.get_thermostat(self._device.id)

    def update_entity_attributes(self) -> None:
        self._attr_native_value = self._device.aux_heat_lockout_temp

    async def async_set_native_value(self, value: float) -> None:
        """Optimistically update the value and coalesce rapid changes into one API write."""
        self._device.aux_heat_lockout_temp = value
        self._target_value = value
        self.async_write_ha_state()

        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
        self._debounce_timer = self.hass.loop.call_later(
            DEBOUNCE_DELAY,
            lambda: self.hass.async_create_task(self._async_send_debounced_value()),
        )

    async def _async_send_debounced_value(self) -> None:
        """Send the latest balance point value after the debounce interval."""
        self._debounce_timer = None
        target = self._target_value
        if target is None:
            return

        def update(thermostat: DaikinThermostat) -> None:
            thermostat.aux_heat_lockout_temp = target

        await self.update_state_optimistically(
            operation=lambda: self._data.daikin.set_thermostat_aux_heat_lockout_temp(self._device.id, target),
            optimistic_update=update,
            check=lambda thermostat: thermostat.aux_heat_lockout_temp == target,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel an unsent update when the entity is removed."""
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
            self._debounce_timer = None
        await super().async_will_remove_from_hass()


class DaikinTemperatureOffsetNumber(DaikinOneEntity[DaikinThermostat], NumberEntity):
    """Control native hardware temperature calibration offset."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE_DELTA
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_translation_key = "temperature_offset"

    def __init__(
        self,
        data: DaikinOneData,
        thermostat: DaikinThermostat,
        description: NumberEntityDescription = TEMPERATURE_OFFSET_DESCRIPTION,
    ) -> None:
        super().__init__(data, thermostat)
        self.entity_description = description

        schema_version = data.entry.data.get(CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY, 1)
        match schema_version:
            case 0:
                self._attr_unique_id = f"{self._device.id}-Temperature Offset"
            case 1:
                self._attr_unique_id = f"{self._device.id}-{self.entity_description.key}"
            case _:
                raise ValueError("unexpected entity uid schema version")

        self.update_entity_attributes()

    @property
    def _client(self) -> DaikinOne:
        return self._data.daikin

    @property
    def device_name(self) -> str:
        return f"{self._device.name} Thermostat"

    async def async_get_device(self) -> DaikinThermostat:
        return self._data.daikin.get_thermostat(self._device.id)

    def update_entity_attributes(self) -> None:
        self._attr_native_value = self._device.temp_offset
        if self._device.units == 1:
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_native_min_value = -5.5
            self._attr_native_max_value = 5.5
            self._attr_native_step = 0.5
        else:
            self._attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
            self._attr_native_min_value = -10.0
            self._attr_native_max_value = 10.0
            self._attr_native_step = 1.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the temperature calibration offset."""

        def update(thermostat: DaikinThermostat) -> None:
            thermostat.temp_offset = value

        await self.update_state_optimistically(
            operation=lambda: self._client.set_temperature_offset(self._device.id, value),
            optimistic_update=update,
            check=lambda thermostat: thermostat.temp_offset == value,
        )


class DaikinHumidityOffsetNumber(DaikinOneEntity[DaikinThermostat], NumberEntity):
    """Control native hardware humidity calibration offset."""

    _attr_device_class = NumberDeviceClass.HUMIDITY
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_translation_key = "humidity_offset"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = -15.0
    _attr_native_max_value = 15.0
    _attr_native_step = 1.0

    def __init__(
        self,
        data: DaikinOneData,
        thermostat: DaikinThermostat,
        description: NumberEntityDescription = HUMIDITY_OFFSET_DESCRIPTION,
    ) -> None:
        super().__init__(data, thermostat)
        self.entity_description = description

        schema_version = data.entry.data.get(CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY, 1)
        match schema_version:
            case 0:
                self._attr_unique_id = f"{self._device.id}-Humidity Offset"
            case 1:
                self._attr_unique_id = f"{self._device.id}-{self.entity_description.key}"
            case _:
                raise ValueError("unexpected entity uid schema version")

        self.update_entity_attributes()

    @property
    def _client(self) -> DaikinOne:
        return self._data.daikin

    @property
    def device_name(self) -> str:
        return f"{self._device.name} Thermostat"

    async def async_get_device(self) -> DaikinThermostat:
        return self._data.daikin.get_thermostat(self._device.id)

    def update_entity_attributes(self) -> None:
        self._attr_native_value = float(self._device.hum_offset) if self._device.hum_offset is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the humidity calibration offset."""
        int_value = int(value)

        def update(thermostat: DaikinThermostat) -> None:
            thermostat.hum_offset = int_value

        await self.update_state_optimistically(
            operation=lambda: self._client.set_humidity_offset(self._device.id, int_value),
            optimistic_update=update,
            check=lambda thermostat: thermostat.hum_offset == int_value,
        )
