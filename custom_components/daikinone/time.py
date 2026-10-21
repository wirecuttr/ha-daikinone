"""Time platform for Daikin One integration."""

import datetime
import logging

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.daikinone import DOMAIN, DaikinOneData
from custom_components.daikinone.client.models import DaikinThermostat
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.entity import DaikinOneEntity

log = logging.getLogger(__name__)


def _slot_to_time(val: int | None) -> datetime.time | None:
    """Convert a 15-minute slot index (0-95) to datetime.time."""
    if val is None or not (0 <= val <= 95):
        return None
    return datetime.time(hour=val * 15 // 60, minute=(val * 15) % 60)


def _time_to_slot(val: datetime.time) -> int:
    """Convert datetime.time to the nearest 15-minute slot index (0-95)."""
    return (val.hour * 60 + val.minute + 7) // 15 % 96


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Daikin One time entities."""
    data: DaikinOneData = hass.data[DOMAIN]
    thermostats = data.daikin.get_thermostats().values()

    entities: list[TimeEntity] = []
    for thermostat in thermostats:
        if thermostat.fan_circulate_start is not None and thermostat.fan_circulate_stop is not None:
            entities.append(
                DaikinOneFanCirculationStartTime(
                    description=TimeEntityDescription(
                        key="fan_circulation_start",
                        name="Fan Circulation Start Time",
                        icon="mdi:clock-start",
                        has_entity_name=True,
                        entity_category=EntityCategory.CONFIG,
                        translation_key="fan_circulation_start",
                    ),
                    data=data,
                    thermostat=thermostat,
                )
            )
            entities.append(
                DaikinOneFanCirculationStopTime(
                    description=TimeEntityDescription(
                        key="fan_circulation_stop",
                        name="Fan Circulation Stop Time",
                        icon="mdi:clock-end",
                        has_entity_name=True,
                        entity_category=EntityCategory.CONFIG,
                        translation_key="fan_circulation_stop",
                    ),
                    data=data,
                    thermostat=thermostat,
                )
            )

    async_add_entities(entities, True)


class DaikinOneFanCirculationStartTime(DaikinOneEntity[DaikinThermostat], TimeEntity):
    """Time entity to configure the fan circulation schedule start time."""

    def __init__(
        self,
        description: TimeEntityDescription,
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

    async def async_get_device(self) -> DaikinThermostat:
        return self._data.daikin.get_thermostat(self._device.id)

    def update_entity_attributes(self) -> None:
        self._attr_native_value = _slot_to_time(self._device.fan_circulate_start)

    async def async_set_value(self, value: datetime.time) -> None:
        """Set the start time."""
        slot = _time_to_slot(value)

        def update(t: DaikinThermostat) -> None:
            t.fan_circulate_start = slot

        await self.update_state_optimistically(
            operation=lambda: self._data.daikin.set_thermostat_fan_circulate_start(self._device.id, slot),
            optimistic_update=update,
            check=lambda t: t.fan_circulate_start == slot,
        )


class DaikinOneFanCirculationStopTime(DaikinOneEntity[DaikinThermostat], TimeEntity):
    """Time entity to configure the fan circulation schedule stop time."""

    def __init__(
        self,
        description: TimeEntityDescription,
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

    async def async_get_device(self) -> DaikinThermostat:
        return self._data.daikin.get_thermostat(self._device.id)

    def update_entity_attributes(self) -> None:
        self._attr_native_value = _slot_to_time(self._device.fan_circulate_stop)

    async def async_set_value(self, value: datetime.time) -> None:
        """Set the stop time."""
        slot = _time_to_slot(value)

        def update(t: DaikinThermostat) -> None:
            t.fan_circulate_stop = slot

        await self.update_state_optimistically(
            operation=lambda: self._data.daikin.set_thermostat_fan_circulate_stop(self._device.id, slot),
            optimistic_update=update,
            check=lambda t: t.fan_circulate_stop == slot,
        )
