"""Switch platform for Daikin One."""

import logging
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

log = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Daikin One switch entities."""
    data: DaikinOneData = hass.data[DOMAIN][entry.entry_id]

    entities: list[SwitchEntity] = []

    for thermostat in data.daikin.get_thermostats().values():
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

    async_add_entities(entities, True)


class DaikinOneEmergencyHeatSwitch(DaikinOneEntity[DaikinThermostat], SwitchEntity):
    """Switch entity to enable or disable Emergency / Auxiliary Heat."""

    _attr_translation_key = "emergency_heat"

    def __init__(
        self,
        description: SwitchEntityDescription,
        data: DaikinOneData,
        thermostat: DaikinThermostat,
    ) -> None:
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
