"""Tests for Daikin One consumable alert binary sensors."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

from custom_components.daikinone import DOMAIN, DaikinOneData
from custom_components.daikinone.binary_sensor import (
    CONSUMABLE_ALERT_CONFIGS,
    DaikinOneConsumableAlertBinarySensor,
    async_setup_entry,
)
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


class TestConsumableAlertBinarySensorSetup:
    async def test_setup_entry_media_filter_and_service_guards(self, mock_data: DaikinOneData) -> None:
        """Verify dynamic discovery creates binary sensors only for configured hardware."""
        mainfloor = _create_mock_thermostat(
            id="dtst_mainfloor",
            name="MainFloor",
            num_media_filters=1,
            media_air_filter_days=105,
            media_air_filter_days_limit=186,
            service_days_limit=0,
            num_uv_bulbs=0,
        )
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
        consumable_binary_sensors = [e for e in added_entities if isinstance(e, DaikinOneConsumableAlertBinarySensor)]

        keys_mainfloor = [
            e.entity_description.key for e in consumable_binary_sensors if e._device.id == "dtst_mainfloor"
        ]
        keys_upstairs = [e.entity_description.key for e in consumable_binary_sensors if e._device.id == "dtst_upstairs"]

        assert keys_mainfloor == ["media_air_filter_replacement"]
        assert sorted(keys_upstairs) == sorted(["media_air_filter_replacement", "service_inspection_due"])


class TestConsumableAlertBinarySensorState:
    def test_state_normal_is_off(self, mock_data: DaikinOneData) -> None:
        """Verify is_on is False when days used is below limit and active flag is False."""
        t = _create_mock_thermostat(
            media_air_filter_days=105,
            media_air_filter_days_limit=186,
            media_air_filter_active=False,
        )
        cfg = next(c for c in CONSUMABLE_ALERT_CONFIGS if c.description.key == "media_air_filter_replacement")
        sensor = DaikinOneConsumableAlertBinarySensor(
            cfg.description, mock_data, t, cfg.active_key, cfg.days_key, cfg.limit_key
        )
        assert sensor.is_on is False

    def test_state_expired_days_trips_on(self, mock_data: DaikinOneData) -> None:
        """Verify is_on is True when days used meets or exceeds limit."""
        t = _create_mock_thermostat(
            media_air_filter_days=186,
            media_air_filter_days_limit=186,
            media_air_filter_active=False,
        )
        cfg = next(c for c in CONSUMABLE_ALERT_CONFIGS if c.description.key == "media_air_filter_replacement")
        sensor = DaikinOneConsumableAlertBinarySensor(
            cfg.description, mock_data, t, cfg.active_key, cfg.days_key, cfg.limit_key
        )
        assert sensor.is_on is True

    def test_state_expired_runtime_trips_on(self, mock_data: DaikinOneData) -> None:
        """Verify is_on is True when runtime used meets or exceeds runtime limit."""
        t = _create_mock_thermostat(
            media_air_filter_days=50,
            media_air_filter_days_limit=186,
            media_air_filter_runtime=1000,
            media_air_filter_runtime_limit=1000,
            media_air_filter_active=False,
        )
        cfg = next(c for c in CONSUMABLE_ALERT_CONFIGS if c.description.key == "media_air_filter_replacement")
        sensor = DaikinOneConsumableAlertBinarySensor(
            cfg.description,
            mock_data,
            t,
            cfg.active_key,
            cfg.days_key,
            cfg.limit_key,
            cfg.runtime_key,
            cfg.runtime_limit_key,
        )
        assert sensor.is_on is True

    def test_state_active_flag_trips_on_immediately(self, mock_data: DaikinOneData) -> None:
        """Verify is_on is True when cloud active flag is True regardless of day count."""
        t = _create_mock_thermostat(
            media_air_filter_days=10,
            media_air_filter_days_limit=186,
            media_air_filter_active=True,
        )
        cfg = next(c for c in CONSUMABLE_ALERT_CONFIGS if c.description.key == "media_air_filter_replacement")
        sensor = DaikinOneConsumableAlertBinarySensor(
            cfg.description, mock_data, t, cfg.active_key, cfg.days_key, cfg.limit_key
        )
        assert sensor.is_on is True


class TestConsumableAlertBinarySensorProperties:
    def test_entity_metadata(self, mock_data: DaikinOneData) -> None:
        """Verify device_class is PROBLEM and entity_category is DIAGNOSTIC."""
        t = _create_mock_thermostat()
        cfg = next(c for c in CONSUMABLE_ALERT_CONFIGS if c.description.key == "media_air_filter_replacement")
        sensor = DaikinOneConsumableAlertBinarySensor(
            cfg.description, mock_data, t, cfg.active_key, cfg.days_key, cfg.limit_key
        )
        assert sensor.device_class == BinarySensorDeviceClass.PROBLEM
        assert sensor.entity_category == EntityCategory.DIAGNOSTIC

    def test_unique_id_schema_v0(self) -> None:
        """Verify Schema v0 uses f'{device_id}-{name}'."""
        entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 0})
        data = DaikinOneData(_hass=None, entry=entry, daikin=MagicMock())  # type: ignore[arg-type]
        t = _create_mock_thermostat(id="dtst123")
        cfg = next(c for c in CONSUMABLE_ALERT_CONFIGS if c.description.key == "media_air_filter_replacement")
        sensor = DaikinOneConsumableAlertBinarySensor(
            cfg.description, data, t, cfg.active_key, cfg.days_key, cfg.limit_key
        )
        assert sensor.unique_id == "dtst123-Media air filter replacement"

    def test_unique_id_schema_v1(self) -> None:
        """Verify Schema v1 uses f'{device_id}-{key}'."""
        entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
        data = DaikinOneData(_hass=None, entry=entry, daikin=MagicMock())  # type: ignore[arg-type]
        t = _create_mock_thermostat(id="dtst123")
        cfg = next(c for c in CONSUMABLE_ALERT_CONFIGS if c.description.key == "media_air_filter_replacement")
        sensor = DaikinOneConsumableAlertBinarySensor(
            cfg.description, data, t, cfg.active_key, cfg.days_key, cfg.limit_key
        )
        assert sensor.unique_id == "dtst123-media_air_filter_replacement"
