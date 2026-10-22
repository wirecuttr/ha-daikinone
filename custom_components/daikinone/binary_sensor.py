"""Binary sensor platform for Daikin One integration."""

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.daikinone import DOMAIN, DaikinOneData
from custom_components.daikinone.client.models import DaikinThermostat
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.entity import DaikinOneEntity

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConsumableAlertConfig:
    description: BinarySensorEntityDescription
    active_key: str
    days_key: str
    limit_key: str
    runtime_key: str | None = None
    runtime_limit_key: str | None = None
    is_installed: Callable[[DaikinThermostat], bool] = lambda _: True


CONSUMABLE_ALERT_CONFIGS: list[ConsumableAlertConfig] = [
    ConsumableAlertConfig(
        description=BinarySensorEntityDescription(
            key="media_air_filter_replacement",
            name="Media air filter replacement",
            has_entity_name=True,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:air-filter",
            translation_key="media_air_filter_replacement",
        ),
        active_key="media_air_filter_active",
        days_key="media_air_filter_days",
        limit_key="media_air_filter_days_limit",
        runtime_key="media_air_filter_runtime",
        runtime_limit_key="media_air_filter_runtime_limit",
        is_installed=lambda t: bool(t.num_media_filters and t.num_media_filters > 0),
    ),
    ConsumableAlertConfig(
        description=BinarySensorEntityDescription(
            key="service_inspection_due",
            name="Service inspection due",
            has_entity_name=True,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:wrench-clock",
            translation_key="service_inspection_due",
        ),
        active_key="service_active",
        days_key="service_days",
        limit_key="service_days_limit",
        is_installed=lambda _: True,  # Thermostat system-level maintenance
    ),
    ConsumableAlertConfig(
        description=BinarySensorEntityDescription(
            key="humidifier_pad_replacement",
            name="Humidifier pad replacement",
            has_entity_name=True,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:water-alert",
            translation_key="humidifier_pad_replacement",
        ),
        active_key="hum_pad_active",
        days_key="hum_pad_days",
        limit_key="hum_pad_days_limit",
        runtime_key="hum_pad_runtime",
        runtime_limit_key="hum_pad_runtime_limit",
        is_installed=lambda t: bool(
            (t.ct_humidifier_num_pads and t.ct_humidifier_num_pads > 0) or t.aux_humidifier_status
        ),
    ),
    ConsumableAlertConfig(
        description=BinarySensorEntityDescription(
            key="uv_lamp_replacement",
            name="UV lamp replacement",
            has_entity_name=True,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:lightbulb-alert",
            translation_key="uv_lamp_replacement",
        ),
        active_key="uv_active",
        days_key="uv_days",
        limit_key="uv_days_limit",
        runtime_key="uv_runtime",
        runtime_limit_key="uv_runtime_limit",
        is_installed=lambda t: bool(t.num_uv_bulbs and t.num_uv_bulbs > 0),
    ),
    ConsumableAlertConfig(
        description=BinarySensorEntityDescription(
            key="hepa_filter_replacement",
            name="HEPA filter replacement",
            has_entity_name=True,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:air-filter",
            translation_key="hepa_filter_replacement",
        ),
        active_key="hepa_filter_active",
        days_key="hepa_filter_days",
        limit_key="hepa_filter_days_limit",
        runtime_key="hepa_filter_runtime",
        runtime_limit_key="hepa_filter_runtime_limit",
        is_installed=lambda t: bool(t.num_hepa_filters and t.num_hepa_filters > 0),
    ),
    ConsumableAlertConfig(
        description=BinarySensorEntityDescription(
            key="electronic_filter_replacement",
            name="Electronic filter replacement",
            has_entity_name=True,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:air-filter",
            translation_key="electronic_filter_replacement",
        ),
        active_key="electronic_filter_active",
        days_key="electronic_filter_days",
        limit_key="electronic_filter_days_limit",
        runtime_key="electronic_filter_runtime",
        runtime_limit_key="electronic_filter_runtime_limit",
        is_installed=lambda t: bool(t.num_electronic_filters and t.num_electronic_filters > 0),
    ),
    ConsumableAlertConfig(
        description=BinarySensorEntityDescription(
            key="dehumidifier_filter_replacement",
            name="Dehumidifier filter replacement",
            has_entity_name=True,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:air-filter",
            translation_key="dehumidifier_filter_replacement",
        ),
        active_key="dehum_filter_active",
        days_key="dehum_filter_days",
        limit_key="dehum_filter_days_limit",
        runtime_key="dehum_filter_runtime",
        runtime_limit_key="dehum_filter_runtime_limit",
        is_installed=lambda t: bool(t.aux_dehumidifier_status),
    ),
    ConsumableAlertConfig(
        description=BinarySensorEntityDescription(
            key="ventilator_core_replacement",
            name="Ventilator core replacement",
            has_entity_name=True,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:hvac",
            translation_key="ventilator_core_replacement",
        ),
        active_key="ventilation_active",
        days_key="ventilation_days",
        limit_key="ventilation_days_limit",
        is_installed=lambda t: bool(t.aux_ventilator_status or t.ct_system_cap_ventilation),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Daikin One binary sensor entities."""
    data: DaikinOneData = hass.data[DOMAIN]
    thermostats = data.daikin.get_thermostats().values()

    entities: list[BinarySensorEntity] = []
    for thermostat in thermostats:
        for cfg in CONSUMABLE_ALERT_CONFIGS:
            # Tier 1 Guard: Hardware Inventory
            if not cfg.is_installed(thermostat):
                continue

            # Tier 2 Guard: Configured Limits
            days_limit = getattr(thermostat, cfg.limit_key, None) or 0
            rt_limit = getattr(thermostat, cfg.runtime_limit_key, None) or 0 if cfg.runtime_limit_key else 0
            if days_limit <= 0 and rt_limit <= 0:
                continue

            entities.append(
                DaikinOneConsumableAlertBinarySensor(
                    description=cfg.description,
                    data=data,
                    thermostat=thermostat,
                    active_key=cfg.active_key,
                    days_key=cfg.days_key,
                    limit_key=cfg.limit_key,
                    runtime_key=cfg.runtime_key,
                    runtime_limit_key=cfg.runtime_limit_key,
                )
            )

    async_add_entities(entities, True)


class DaikinOneConsumableAlertBinarySensor(DaikinOneEntity[DaikinThermostat], BinarySensorEntity):
    """Binary sensor indicating when a consumable requires replacement or service."""

    def __init__(
        self,
        description: BinarySensorEntityDescription,
        data: DaikinOneData,
        thermostat: DaikinThermostat,
        active_key: str,
        days_key: str,
        limit_key: str,
        runtime_key: str | None = None,
        runtime_limit_key: str | None = None,
    ) -> None:
        """Initialize the consumable alert binary sensor."""
        super().__init__(data, thermostat)
        self.entity_description = description
        self._active_key = active_key
        self._days_key = days_key
        self._limit_key = limit_key
        self._runtime_key = runtime_key
        self._runtime_limit_key = runtime_limit_key

        match data.entry.data[CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY]:
            case 0:
                name = self.entity_description.name or self.name
                self._attr_unique_id = f"{self._device.id}-{name}"
            case 1:
                self._attr_unique_id = f"{self._device.id}-{self.entity_description.key}"
            case _:
                raise ValueError("unexpected entity uid schema version")

        self.update_entity_attributes()

    async def async_get_device(self) -> DaikinThermostat:
        """Fetch the latest state of the thermostat."""
        return self._data.daikin.get_thermostat(self._device.id)

    def update_entity_attributes(self) -> None:
        """Update binary sensor problem state based on active flag or threshold expiration."""
        active_flag = bool(getattr(self._device, self._active_key, False))
        days_used = getattr(self._device, self._days_key, None)
        days_limit = getattr(self._device, self._limit_key, None)

        days_expired = days_used is not None and days_limit is not None and days_limit > 0 and days_used >= days_limit

        rt_used = getattr(self._device, self._runtime_key, None) if self._runtime_key else None
        rt_limit = getattr(self._device, self._runtime_limit_key, None) if self._runtime_limit_key else None
        rt_expired = rt_used is not None and rt_limit is not None and rt_limit > 0 and rt_used >= rt_limit

        self._attr_is_on = active_flag or days_expired or rt_expired
