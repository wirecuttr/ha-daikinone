"""Switch platform for Daikin One configuration controls."""

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.daikinone import DOMAIN, DaikinOneData
from custom_components.daikinone.client.models import (
    DaikinThermostat,
    DaikinThermostatCapability,
    DaikinThermostatMode,
)
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.entity import DaikinOneEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Daikin One switch entities"""
    data: DaikinOneData = hass.data[DOMAIN]
    thermostats = data.daikin.get_thermostats().values()

    entities: list[SwitchEntity] = []
    for thermostat in thermostats:
        entities.append(
            DaikinOneScheduleSwitch(
                description=SwitchEntityDescription(
                    key="schedule",
                    name="Schedule",
                    has_entity_name=True,
                    icon="mdi:calendar-sync",
                ),
                data=data,
                thermostat=thermostat,
            )
        )
        if thermostat.one_clean_fan_active is not None:
            entities.append(
                DaikinOneOneCleanFanSwitch(
                    description=SwitchEntityDescription(
                        key="one_clean_fan",
                        name="One Clean Fan",
                        has_entity_name=True,
                        icon="mdi:fan-auto",
                    ),
                    data=data,
                    thermostat=thermostat,
                )
            )
        if DaikinThermostatCapability.EMERGENCY_HEAT in thermostat.capabilities:
            entities.append(
                DaikinOneEmergencyHeatSwitch(
                    description=SwitchEntityDescription(
                        key="emergency_heat",
                        name="Emergency heat",
                        has_entity_name=True,
                        icon="mdi:radiator",
                        translation_key="emergency_heat",
                    ),
                    data=data,
                    thermostat=thermostat,
                )
            )
        if thermostat.night_mode_enabled is not None:
            entities.append(
                DaikinOneNightModeSwitch(
                    data,
                    thermostat,
                    SwitchEntityDescription(
                        key="night_mode",
                        name="Night mode",
                        icon="mdi:weather-night",
                        has_entity_name=True,
                        translation_key="night_mode",
                    ),
                )
            )

    async_add_entities(entities, True)


class DaikinOneScheduleSwitch(DaikinOneEntity[DaikinThermostat], SwitchEntity):
    """Switch entity to enable or disable the thermostat schedule."""

    def __init__(
        self,
        description: SwitchEntityDescription,
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

    @property
    def device_name(self) -> str:
        return f"{self._device.name} Thermostat"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable schedule on thermostat."""
        await self._set_schedule_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable schedule on thermostat (permanent manual hold)."""
        await self._set_schedule_enabled(False)

    async def _set_schedule_enabled(self, enabled: bool) -> None:
        def update(t: DaikinThermostat) -> None:
            t.schedule.enabled = enabled
            if not enabled:
                t.schedule.override = False

        await self.update_state_optimistically(
            operation=lambda: self._data.daikin.set_thermostat_schedule_enabled(self._device.id, enabled),
            optimistic_update=update,
            check=lambda t: t.schedule.enabled == enabled,
        )

    async def async_get_device(self) -> DaikinThermostat:
        return self._data.daikin.get_thermostat(self._device.id)

    def update_entity_attributes(self) -> None:
        self._attr_is_on = self._device.schedule.enabled


class DaikinOneOneCleanFanSwitch(DaikinOneEntity[DaikinThermostat], SwitchEntity):
    """Runs the One Clean cycle: the indoor fan at full speed for three hours."""

    def __init__(self, description: SwitchEntityDescription, data: DaikinOneData, thermostat: DaikinThermostat):
        super().__init__(data, thermostat)

        self.entity_description = description

        match data.entry.data[CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY]:
            case 0 | 1:
                self._attr_unique_id = f"{self._device.id}-{self.entity_description.key}"
            case _:
                raise ValueError("unexpected entity uid schema version")

    @property
    def device_name(self) -> str:
        return f"{self._device.name} Thermostat"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_active(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_active(False)

    async def _set_active(self, active: bool) -> None:
        def update(t: DaikinThermostat) -> None:
            t.one_clean_fan_active = active

        await self.update_state_optimistically(
            operation=lambda: self._data.daikin.set_one_clean_fan_active(self._device.id, active),
            optimistic_update=update,
            check=lambda t: t.one_clean_fan_active == active,
        )

    async def async_get_device(self) -> DaikinThermostat:
        return self._data.daikin.get_thermostat(self._device.id)

    def update_entity_attributes(self) -> None:
        self._attr_is_on = self._device.one_clean_fan_active


class DaikinOneEmergencyHeatSwitch(DaikinOneEntity[DaikinThermostat], SwitchEntity):
    """Switch entity to enable or disable Emergency / Auxiliary Heat."""

    _attr_translation_key = "emergency_heat"

    def __init__(
        self,
        description: SwitchEntityDescription,
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

    @property
    def is_on(self) -> bool:
        """Return true if emergency heat is on."""
        return self._device.mode == DaikinThermostatMode.AUX_HEAT

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on emergency heat (lock out heat pump compressor and force auxiliary heat)."""
        await self._set_emergency_heat(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off emergency heat (restore standard heat mode)."""
        await self._set_emergency_heat(False)

    async def _set_emergency_heat(self, enabled: bool) -> None:
        target_mode = DaikinThermostatMode.AUX_HEAT if enabled else DaikinThermostatMode.HEAT

        def update(t: DaikinThermostat) -> None:
            t.mode = target_mode

        await self.update_state_optimistically(
            operation=lambda: self._data.daikin.set_thermostat_mode(self._device.id, target_mode),
            optimistic_update=update,
            check=lambda t: t.mode == target_mode,
        )

    async def async_get_device(self) -> DaikinThermostat:
        return self._data.daikin.get_thermostat(self._device.id)

    def update_entity_attributes(self) -> None:
        self._attr_is_on = self._device.mode == DaikinThermostatMode.AUX_HEAT


class DaikinOneNightModeSwitch(DaikinOneEntity[DaikinThermostat], SwitchEntity):
    """Enable or disable thermostat night mode."""

    def __init__(
        self,
        data: DaikinOneData,
        thermostat: DaikinThermostat,
        description: SwitchEntityDescription,
    ) -> None:
        super().__init__(data, thermostat)
        self.entity_description = description
        match data.entry.data[CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY]:
            case 0 | 1:
                self._attr_unique_id = f"{self._device.id}-{description.key}"
            case _:
                raise ValueError("unexpected entity uid schema version")
        self.update_entity_attributes()

    @property
    def device_name(self) -> str:
        return f"{self._device.name} Thermostat"

    @property
    def is_on(self) -> bool:
        return bool(self._device.night_mode_enabled)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attributes: dict[str, Any] = {}
        if self._device.night_mode_active is not None:
            attributes["night_mode_active"] = self._device.night_mode_active
        if self._device.night_mode_light_bar_allowed is not None:
            attributes["light_bar_allowed"] = self._device.night_mode_light_bar_allowed
        return attributes

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_night_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_night_mode(False)

    async def _set_night_mode(self, enabled: bool) -> None:
        def update(thermostat: DaikinThermostat) -> None:
            thermostat.night_mode_enabled = enabled

        await self.update_state_optimistically(
            operation=lambda: self._data.daikin.set_thermostat_night_mode(self._device.id, enabled),
            optimistic_update=update,
            check=lambda thermostat: thermostat.night_mode_enabled == enabled,
        )

    async def async_get_device(self) -> DaikinThermostat:
        return self._data.daikin.get_thermostat(self._device.id)

    def update_entity_attributes(self) -> None:
        self._attr_is_on = self.is_on
        self._attr_extra_state_attributes = self.extra_state_attributes
