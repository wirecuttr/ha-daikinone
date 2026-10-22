"""Tests for Daikin One consumable life sensors."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikinone import DOMAIN, DaikinOneData
from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.models import (
    DaikinThermostat,
    DaikinThermostatCapability,
    DaikinThermostatFanMode,
    DaikinThermostatFanSpeed,
    DaikinThermostatMode,
    DaikinThermostatSchedule,
    DaikinThermostatStatus,
)
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.sensor import (
    CONSUMABLE_SENSOR_CONFIGS,
    DaikinOneConsumableLifeSensor,
    async_setup_entry,
)
from custom_components.daikinone.utils import Temperature


def _create_mock_thermostat(**kwargs) -> DaikinThermostat:
    defaults = {
        "id": "device123",
        "location_id": "loc456",
        "name": "MainFloor",
        "model": "ONEPLUS",
        "firmware_version": "4.0.17",
        "online": True,
        "capabilities": {
            DaikinThermostatCapability.HEAT,
            DaikinThermostatCapability.COOL,
        },
        "mode": DaikinThermostatMode.HEAT,
        "status": DaikinThermostatStatus.IDLE,
        "fan_mode": DaikinThermostatFanMode.OFF,
        "fan_speed": DaikinThermostatFanSpeed.LOW,
        "schedule": DaikinThermostatSchedule(enabled=True, override=False),
        "indoor_temperature": Temperature.from_celsius(21.0),
        "indoor_humidity": 45,
        "set_point_heat": Temperature.from_celsius(20.0),
        "set_point_heat_min": Temperature.from_celsius(10.0),
        "set_point_heat_max": Temperature.from_celsius(30.0),
        "set_point_cool": Temperature.from_celsius(24.0),
        "set_point_cool_min": Temperature.from_celsius(18.0),
        "set_point_cool_max": Temperature.from_celsius(32.0),
        "outdoor_temperature": Temperature.from_celsius(10.0),
        "outdoor_humidity": 60,
        "air_quality_outdoor": None,
        "air_quality_indoor": None,
        "one_clean_fan_active": None,
        "dual_fuel_furnace_lockout_enable": None,
        "equipment": {},
    }
    defaults.update(kwargs)
    return DaikinThermostat(**defaults)


@pytest.fixture
def mock_data() -> DaikinOneData:
    entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
    client = MagicMock(spec=DaikinOne)
    client.get_thermostats = MagicMock(return_value={})
    data = DaikinOneData(_hass=None, entry=entry, daikin=client)  # type: ignore[arg-type]
    data.update = AsyncMock()  # type: ignore[method-assign]
    return data


class TestConsumableLifeSensorSetup:
    async def test_setup_entry_media_filter_and_service_guards(self, mock_data: DaikinOneData) -> None:
        """Verify dynamic discovery creates entities only for installed hardware with positive limits."""
        # MainFloor: Media filter installed & configured; service limit is 0
        mainfloor = _create_mock_thermostat(
            id="dtst_mainfloor",
            name="MainFloor",
            num_media_filters=1,
            media_air_filter_days=105,
            media_air_filter_days_limit=186,
            service_days_limit=0,
            num_uv_bulbs=0,
        )
        # Upstairs: Media filter installed & service configured with 372 limit
        upstairs = _create_mock_thermostat(
            id="dtst_upstairs",
            name="Upstairs",
            num_media_filters=1,
            media_air_filter_days=109,
            media_air_filter_days_limit=186,
            service_days=96,
            service_days_limit=372,
            num_uv_bulbs=0,
        )
        mock_data.daikin.get_thermostats.return_value = {
            mainfloor.id: mainfloor,
            upstairs.id: upstairs,
        }

        async_add_entities = MagicMock()
        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)

        added_entities = async_add_entities.call_args[0][0]
        consumable_sensors = [e for e in added_entities if isinstance(e, DaikinOneConsumableLifeSensor)]

        # MainFloor should have media filter life (1), Upstairs should have media filter and service life (2)
        keys_mainfloor = [e.entity_description.key for e in consumable_sensors if e._device.id == "dtst_mainfloor"]
        keys_upstairs = [e.entity_description.key for e in consumable_sensors if e._device.id == "dtst_upstairs"]

        assert keys_mainfloor == ["media_air_filter_life"]
        assert sorted(keys_upstairs) == sorted(["media_air_filter_life", "service_inspection_life"])

    async def test_setup_entry_rejects_uninstalled_accessories(self, mock_data: DaikinOneData) -> None:
        """Verify Tier 1 guard eliminates ghost entities when hardware count is 0 or uninstalled."""
        t = _create_mock_thermostat(
            num_media_filters=0,
            media_air_filter_days_limit=186,  # Limit configured, but hardware count is 0
            num_uv_bulbs=0,
            uv_days_limit=365,
            num_hepa_filters=0,
            hepa_filter_days_limit=365,
        )
        mock_data.daikin.get_thermostats.return_value = {t.id: t}

        async_add_entities = MagicMock()
        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)

        added_entities = async_add_entities.call_args[0][0]
        consumable_sensors = [e for e in added_entities if isinstance(e, DaikinOneConsumableLifeSensor)]
        assert len(consumable_sensors) == 0


class TestConsumableLifeSensorCalculations:
    def test_percentage_calculation_midlife(self, mock_data: DaikinOneData) -> None:
        """Verify live MainFloor formula: (186 - 105) / 186 * 100 = 43.5%."""
        t = _create_mock_thermostat(
            media_air_filter_days=105,
            media_air_filter_days_limit=186,
        )
        cfg = next(c for c in CONSUMABLE_SENSOR_CONFIGS if c.description.key == "media_air_filter_life")
        sensor = DaikinOneConsumableLifeSensor(cfg.description, mock_data, t, cfg.days_key, cfg.limit_key)
        assert sensor.native_value == 43.5
        assert sensor.extra_state_attributes["days_used"] == 105
        assert sensor.extra_state_attributes["days_limit"] == 186
        assert sensor.extra_state_attributes["days_remaining"] == 81

    def test_percentage_calculation_upstairs_service(self, mock_data: DaikinOneData) -> None:
        """Verify live Upstairs service formula: (372 - 96) / 372 * 100 = 74.2%."""
        t = _create_mock_thermostat(
            service_days=96,
            service_days_limit=372,
        )
        cfg = next(c for c in CONSUMABLE_SENSOR_CONFIGS if c.description.key == "service_inspection_life")
        sensor = DaikinOneConsumableLifeSensor(cfg.description, mock_data, t, cfg.days_key, cfg.limit_key)
        assert sensor.native_value == 74.2
        assert sensor.extra_state_attributes["days_remaining"] == 276

    def test_percentage_brand_new_clamps_to_100(self, mock_data: DaikinOneData) -> None:
        """Verify unused consumable reports 100.0%."""
        t = _create_mock_thermostat(
            media_air_filter_days=0,
            media_air_filter_days_limit=186,
        )
        cfg = next(c for c in CONSUMABLE_SENSOR_CONFIGS if c.description.key == "media_air_filter_life")
        sensor = DaikinOneConsumableLifeSensor(cfg.description, mock_data, t, cfg.days_key, cfg.limit_key)
        assert sensor.native_value == 100.0
        assert sensor.extra_state_attributes["days_remaining"] == 186

    def test_percentage_expired_clamps_to_zero(self, mock_data: DaikinOneData) -> None:
        """Verify overdue consumable clamps to 0.0% and days_remaining clamps to 0."""
        t = _create_mock_thermostat(
            media_air_filter_days=200,
            media_air_filter_days_limit=186,
        )
        cfg = next(c for c in CONSUMABLE_SENSOR_CONFIGS if c.description.key == "media_air_filter_life")
        sensor = DaikinOneConsumableLifeSensor(cfg.description, mock_data, t, cfg.days_key, cfg.limit_key)
        assert sensor.native_value == 0.0
        assert sensor.extra_state_attributes["days_remaining"] == 0

    def test_zero_or_none_limit_returns_none(self, mock_data: DaikinOneData) -> None:
        """Verify missing or zero limits safely return None without divide-by-zero errors."""
        t = _create_mock_thermostat(
            media_air_filter_days=10,
            media_air_filter_days_limit=0,
        )
        cfg = next(c for c in CONSUMABLE_SENSOR_CONFIGS if c.description.key == "media_air_filter_life")
        sensor = DaikinOneConsumableLifeSensor(cfg.description, mock_data, t, cfg.days_key, cfg.limit_key)
        assert sensor.native_value is None
        assert sensor.extra_state_attributes == {}


class TestConsumableLifeSensorUniqueIds:
    def test_unique_id_schema_v0(self) -> None:
        """Verify Schema v0 uses f'{device_id}-{name}'."""
        entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 0})
        data = DaikinOneData(_hass=None, entry=entry, daikin=MagicMock())  # type: ignore[arg-type]
        t = _create_mock_thermostat(id="dtst123")
        cfg = next(c for c in CONSUMABLE_SENSOR_CONFIGS if c.description.key == "media_air_filter_life")
        sensor = DaikinOneConsumableLifeSensor(cfg.description, data, t, cfg.days_key, cfg.limit_key)
        assert sensor.unique_id == "dtst123-Media air filter life"

    def test_unique_id_schema_v1(self) -> None:
        """Verify Schema v1 uses f'{device_id}-{key}'."""
        entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
        data = DaikinOneData(_hass=None, entry=entry, daikin=MagicMock())  # type: ignore[arg-type]
        t = _create_mock_thermostat(id="dtst123")
        cfg = next(c for c in CONSUMABLE_SENSOR_CONFIGS if c.description.key == "media_air_filter_life")
        sensor = DaikinOneConsumableLifeSensor(cfg.description, data, t, cfg.days_key, cfg.limit_key)
        assert sensor.unique_id == "dtst123-media_air_filter_life"
