from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.daikinone import DOMAIN, DaikinOneData
from custom_components.daikinone.climate import DaikinOneThermostatFanSpeed
from custom_components.daikinone.client.models import (
    DaikinThermostat,
    DaikinThermostatFanCirculateDuration,
    DaikinThermostatFanSpeed,
)
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.entity import DaikinOneEntity

DUAL_FUEL_PRIORITY_COMFORT = "Comfort"
DUAL_FUEL_PRIORITY_EFFICIENCY = "Efficiency"

DUAL_FUEL_PRIORITY_OPTIONS = [
    DUAL_FUEL_PRIORITY_COMFORT,
    DUAL_FUEL_PRIORITY_EFFICIENCY,
]

FAN_CIRCULATE_DUTY_CYCLE_OPTIONS: dict[str, DaikinThermostatFanCirculateDuration] = {
    "Continuous": DaikinThermostatFanCirculateDuration.CONTINUOUS,
    "5 min/hr": DaikinThermostatFanCirculateDuration.MIN_5,
    "15 min/hr": DaikinThermostatFanCirculateDuration.MIN_15,
    "30 min/hr": DaikinThermostatFanCirculateDuration.MIN_30,
    "45 min/hr": DaikinThermostatFanCirculateDuration.MIN_45,
}

DUTY_CYCLE_TO_OPTION: dict[DaikinThermostatFanCirculateDuration, str] = {
    v: k for k, v in FAN_CIRCULATE_DUTY_CYCLE_OPTIONS.items()
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Daikin One select entities"""
    data: DaikinOneData = hass.data[DOMAIN]
    thermostats = data.daikin.get_thermostats().values()

    entities: list[SelectEntity] = []
    for thermostat in thermostats:
        entities.append(
            DaikinOneFanSpeedSelect(
                description=SelectEntityDescription(
                    key="fan_speed",
                    name="Fan circulation speed",
                    has_entity_name=True,
                    icon="mdi:fan",
                    entity_category=EntityCategory.CONFIG,
                    options=[speed.name.capitalize() for speed in DaikinOneThermostatFanSpeed],
                    translation_key="fan_speed",
                ),
                data=data,
                thermostat=thermostat,
            )
        )
        if thermostat.fan_circulate_duration is not None:
            entities.append(
                DaikinOneFanCirculationDutyCycleSelect(
                    description=SelectEntityDescription(
                        key="fan_circulation_duty_cycle",
                        name="Fan Circulation Duty Cycle",
                        has_entity_name=True,
                        icon="mdi:fan-clock",
                        entity_category=EntityCategory.CONFIG,
                        options=list(FAN_CIRCULATE_DUTY_CYCLE_OPTIONS.keys()),
                        translation_key="fan_circulation_duty_cycle",
                    ),
                    data=data,
                    thermostat=thermostat,
                )
            )
        if thermostat.dual_fuel_furnace_lockout_enable is not None:
            entities.append(
                DaikinOneDualFuelPrioritySelect(
                    description=SelectEntityDescription(
                        key="dual_fuel_priority",
                        name="Dual Fuel Priority",
                        has_entity_name=True,
                        icon="mdi:leaf",
                        options=DUAL_FUEL_PRIORITY_OPTIONS,
                        entity_category=EntityCategory.CONFIG,
                    ),
                    data=data,
                    thermostat=thermostat,
                )
            )

    async_add_entities(entities, True)


class DaikinOneFanSpeedSelect(DaikinOneEntity[DaikinThermostat], SelectEntity):
    def __init__(self, description: SelectEntityDescription, data: DaikinOneData, thermostat: DaikinThermostat):
        super().__init__(data, thermostat)

        self.entity_description = description

        match data.entry.data[CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY]:
            case 0 | 1:
                self._attr_unique_id = f"{self._device.id}-{self.entity_description.key}"
            case _:
                raise ValueError("unexpected entity uid schema version")

        self.update_entity_attributes()

    @property
    def device_name(self) -> str:
        return f"{self._device.name} Thermostat"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        target_fan_speed: DaikinThermostatFanSpeed
        match option.upper():
            case DaikinOneThermostatFanSpeed.LOW.name:
                target_fan_speed = DaikinThermostatFanSpeed.LOW
            case DaikinOneThermostatFanSpeed.MEDIUM.name:
                target_fan_speed = DaikinThermostatFanSpeed.MEDIUM
            case DaikinOneThermostatFanSpeed.HIGH.name:
                target_fan_speed = DaikinThermostatFanSpeed.HIGH
            case _:
                raise ValueError(f"Attempted to set unsupported fan speed: {option}")

        # update fan speed optimistically
        def update(t: DaikinThermostat):
            t.fan_speed = target_fan_speed

        await self.update_state_optimistically(
            operation=lambda: self._data.daikin.set_thermostat_fan_speed(self._device.id, target_fan_speed),
            optimistic_update=update,
            check=lambda t: t.fan_speed == target_fan_speed,
        )

    async def async_get_device(self) -> DaikinThermostat:
        return self._data.daikin.get_thermostat(self._device.id)

    def update_entity_attributes(self) -> None:
        self._attr_current_option = self._device.fan_speed.name.capitalize()


class DaikinOneDualFuelPrioritySelect(DaikinOneEntity[DaikinThermostat], SelectEntity):
    """Select entity to configure dual-fuel priority (Comfort vs. Efficiency)."""

    def __init__(
        self,
        description: SelectEntityDescription,
        data: DaikinOneData,
        thermostat: DaikinThermostat,
    ):
        super().__init__(data, thermostat)

        self.entity_description = description

        match data.entry.data[CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY]:
            case 0 | 1:
                self._attr_unique_id = f"{self._device.id}-{self.entity_description.key}"
            case _:
                raise ValueError("unexpected entity uid schema version")

        self.update_entity_attributes()

    @property
    def device_name(self) -> str:
        return f"{self._device.name} Thermostat"

    async def async_select_option(self, option: str) -> None:
        """Change the selected dual fuel priority."""
        if option == DUAL_FUEL_PRIORITY_EFFICIENCY:
            target_enabled = True
        elif option == DUAL_FUEL_PRIORITY_COMFORT:
            target_enabled = False
        else:
            raise ValueError(f"Attempted to set unsupported dual fuel priority: {option}")

        def update(t: DaikinThermostat) -> None:
            t.dual_fuel_furnace_lockout_enable = target_enabled

        await self.update_state_optimistically(
            operation=lambda: self._data.daikin.set_dual_fuel_furnace_lockout_enable(self._device.id, target_enabled),
            optimistic_update=update,
            check=lambda t: t.dual_fuel_furnace_lockout_enable == target_enabled,
        )

    async def async_get_device(self) -> DaikinThermostat:
        return self._data.daikin.get_thermostat(self._device.id)

    def update_entity_attributes(self) -> None:
        if self._device.dual_fuel_furnace_lockout_enable is True:
            self._attr_current_option = DUAL_FUEL_PRIORITY_EFFICIENCY
        elif self._device.dual_fuel_furnace_lockout_enable is False:
            self._attr_current_option = DUAL_FUEL_PRIORITY_COMFORT
        else:
            self._attr_current_option = None


class DaikinOneFanCirculationDutyCycleSelect(DaikinOneEntity[DaikinThermostat], SelectEntity):
    """Select entity to configure fan circulation duty cycle duration."""

    def __init__(
        self,
        description: SelectEntityDescription,
        data: DaikinOneData,
        thermostat: DaikinThermostat,
    ):
        super().__init__(data, thermostat)

        self.entity_description = description

        match data.entry.data[CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY]:
            case 0 | 1:
                self._attr_unique_id = f"{self._device.id}-{self.entity_description.key}"
            case _:
                raise ValueError("unexpected entity uid schema version")

        self.update_entity_attributes()

    @property
    def device_name(self) -> str:
        return f"{self._device.name} Thermostat"

    async def async_select_option(self, option: str) -> None:
        """Change the selected fan circulation duty cycle."""
        if option not in FAN_CIRCULATE_DUTY_CYCLE_OPTIONS:
            raise ValueError(f"Attempted to set unsupported fan circulation duty cycle: {option}")

        target_duration = FAN_CIRCULATE_DUTY_CYCLE_OPTIONS[option]

        def update(t: DaikinThermostat) -> None:
            t.fan_circulate_duration = target_duration

        await self.update_state_optimistically(
            operation=lambda: self._data.daikin.set_thermostat_fan_circulate_duration(self._device.id, target_duration),
            optimistic_update=update,
            check=lambda t: t.fan_circulate_duration == target_duration,
        )

    async def async_get_device(self) -> DaikinThermostat:
        return self._data.daikin.get_thermostat(self._device.id)

    def update_entity_attributes(self) -> None:
        if self._device.fan_circulate_duration is not None:
            self._attr_current_option = DUTY_CYCLE_TO_OPTION.get(self._device.fan_circulate_duration)
        else:
            self._attr_current_option = None
