"""Tests for Daikin One consumable life and error history sensors."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.const import EntityCategory

from custom_components.daikinone import DOMAIN, DaikinOneData
from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.models import (
    DaikinEquipmentError,
    DaikinSystemError,
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
    ACTION_PROMPT_MESSAGE,
    CONSUMABLE_SENSOR_CONFIGS,
    DaikinOneConsumableLifeSensor,
    DaikinOneEquipmentErrorHistorySensor,
    DaikinOneScheduleResumeTimeSensor,
    DaikinOneScheduleStatusSensor,
    DaikinOneSystemErrorHistorySensor,
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
        "sched_resume_time": None,
        "sched_override_duration": None,
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


class TestErrorHistorySensors:
    """Tests for equipment and system error history timestamp sensors."""

    def test_equipment_error_sensor_state_and_top_3_attributes(self, mock_data: DaikinOneData) -> None:
        t = _create_mock_thermostat(
            equipment_errors=[
                DaikinEquipmentError(
                    timestamp=datetime(2026, 10, 16, 5, 25, 43, tzinfo=UTC),
                    code="14",
                    raw_code=20,
                    severity="minor",
                    level=1,
                    equipment_id=6,
                ),
                DaikinEquipmentError(
                    timestamp=datetime(2026, 10, 3, 9, 28, 38, tzinfo=UTC),
                    code="14",
                    raw_code=20,
                    severity="minor",
                    level=1,
                    equipment_id=6,
                ),
                DaikinEquipmentError(
                    timestamp=datetime(2026, 9, 16, 8, 43, 6, tzinfo=UTC),
                    code="B4",
                    raw_code=180,
                    severity="critical",
                    level=2,
                    equipment_id=3,
                ),
            ]
        )
        desc = SensorEntityDescription(
            key="last_equipment_error",
            name="Last equipment error",
            has_entity_name=True,
            device_class=SensorDeviceClass.TIMESTAMP,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:alert-circle-outline",
            translation_key="last_equipment_error",
        )
        sensor = DaikinOneEquipmentErrorHistorySensor(desc, mock_data, t)
        assert sensor.native_value == datetime(2026, 10, 16, 5, 25, 43, tzinfo=UTC)
        assert sensor.device_class == SensorDeviceClass.TIMESTAMP
        assert sensor.entity_category == EntityCategory.DIAGNOSTIC

        attrs = sensor.extra_state_attributes
        assert attrs["latest_code"] == "14"
        assert attrs["latest_raw_code"] == 20
        assert attrs["latest_severity"] == "minor"
        assert attrs["latest_level"] == 1
        assert attrs["latest_equipment_id"] == 6
        assert len(attrs["recent_errors"]) == 3
        assert attrs["recent_errors"][0] == {
            "timestamp": "2026-10-16T05:25:43+00:00",
            "code": "14",
            "raw_code": 20,
            "severity": "minor",
            "level": 1,
            "equipment_id": 6,
        }
        assert attrs["action_prompt"] == ACTION_PROMPT_MESSAGE

    def test_system_error_sensor_state_and_top_3_attributes(self, mock_data: DaikinOneData) -> None:
        t = _create_mock_thermostat(
            system_errors=[
                DaikinSystemError(
                    timestamp=datetime(2026, 7, 20, 20, 23, 40, tzinfo=UTC),
                    code="10",
                    raw_code=16,
                ),
                DaikinSystemError(
                    timestamp=datetime(2026, 7, 6, 4, 20, 41, tzinfo=UTC),
                    code="10",
                    raw_code=16,
                ),
                DaikinSystemError(
                    timestamp=datetime(2026, 6, 24, 22, 1, 51, tzinfo=UTC),
                    code="05",
                    raw_code=5,
                ),
            ]
        )
        desc = SensorEntityDescription(
            key="last_system_error",
            name="Last system error",
            has_entity_name=True,
            device_class=SensorDeviceClass.TIMESTAMP,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:alert-outline",
            translation_key="last_system_error",
        )
        sensor = DaikinOneSystemErrorHistorySensor(desc, mock_data, t)
        assert sensor.native_value == datetime(2026, 7, 20, 20, 23, 40, tzinfo=UTC)
        assert sensor.device_class == SensorDeviceClass.TIMESTAMP
        assert sensor.entity_category == EntityCategory.DIAGNOSTIC

        attrs = sensor.extra_state_attributes
        assert attrs["latest_code"] == "10"
        assert attrs["latest_raw_code"] == 16
        assert len(attrs["recent_errors"]) == 3
        assert attrs["recent_errors"][0] == {
            "timestamp": "2026-07-20T20:23:40+00:00",
            "code": "10",
            "raw_code": 16,
        }
        assert attrs["action_prompt"] == ACTION_PROMPT_MESSAGE

    def test_empty_error_history_returns_none_state(self, mock_data: DaikinOneData) -> None:
        t = _create_mock_thermostat(equipment_errors=[], system_errors=[])
        eq_desc = SensorEntityDescription(
            key="last_equipment_error",
            name="Last equipment error",
            has_entity_name=True,
            device_class=SensorDeviceClass.TIMESTAMP,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        sys_desc = SensorEntityDescription(
            key="last_system_error",
            name="Last system error",
            has_entity_name=True,
            device_class=SensorDeviceClass.TIMESTAMP,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        eq_sensor = DaikinOneEquipmentErrorHistorySensor(eq_desc, mock_data, t)
        sys_sensor = DaikinOneSystemErrorHistorySensor(sys_desc, mock_data, t)

        assert eq_sensor.native_value is None
        assert eq_sensor.extra_state_attributes["latest_code"] is None
        assert eq_sensor.extra_state_attributes["recent_errors"] == []

        assert sys_sensor.native_value is None
        assert sys_sensor.extra_state_attributes["latest_code"] is None
        assert sys_sensor.extra_state_attributes["recent_errors"] == []

    def test_unique_id_schema_v0_and_v1(self) -> None:
        t = _create_mock_thermostat(id="dtst123")
        eq_desc = SensorEntityDescription(
            key="last_equipment_error",
            name="Last equipment error",
            has_entity_name=True,
        )
        sys_desc = SensorEntityDescription(
            key="last_system_error",
            name="Last system error",
            has_entity_name=True,
        )

        entry_v0 = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 0})
        data_v0 = DaikinOneData(_hass=None, entry=entry_v0, daikin=MagicMock())  # type: ignore[arg-type]
        assert DaikinOneEquipmentErrorHistorySensor(eq_desc, data_v0, t).unique_id == "dtst123-Last equipment error"
        assert DaikinOneSystemErrorHistorySensor(sys_desc, data_v0, t).unique_id == "dtst123-Last system error"

        entry_v1 = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
        data_v1 = DaikinOneData(_hass=None, entry=entry_v1, daikin=MagicMock())  # type: ignore[arg-type]
        assert DaikinOneEquipmentErrorHistorySensor(eq_desc, data_v1, t).unique_id == "dtst123-last_equipment_error"
        assert DaikinOneSystemErrorHistorySensor(sys_desc, data_v1, t).unique_id == "dtst123-last_system_error"


class TestScheduleStatusSensor:
    def test_metadata_and_schema_v1_uid(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat()
        sensor = DaikinOneScheduleStatusSensor(data=mock_data, device=thermostat)

        assert sensor.unique_id == "device123-schedule_status"
        assert sensor.entity_description.key == "schedule_status"
        assert sensor.entity_description.name == "Schedule status"
        assert sensor.entity_description.device_class == SensorDeviceClass.ENUM
        assert sensor.entity_description.entity_category is None
        assert sensor.entity_description.options == [
            "using_schedule",
            "temporary_hold",
            "permanent_hold",
        ]

    def test_schema_v0_uid(self) -> None:
        thermostat = _create_mock_thermostat()
        entry_v0 = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 0})
        data_v0 = DaikinOneData(_hass=None, entry=entry_v0, daikin=MagicMock())  # type: ignore[arg-type]
        sensor = DaikinOneScheduleStatusSensor(data=data_v0, device=thermostat)

        assert sensor.unique_id == "device123-Schedule Status"

    def test_using_schedule_state_and_icon(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(schedule=DaikinThermostatSchedule(enabled=True, override=False))
        sensor = DaikinOneScheduleStatusSensor(data=mock_data, device=thermostat)

        assert sensor.native_value == "using_schedule"
        assert sensor.icon == "mdi:calendar-check"

    def test_temporary_hold_state_and_icon(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(schedule=DaikinThermostatSchedule(enabled=True, override=True))
        sensor = DaikinOneScheduleStatusSensor(data=mock_data, device=thermostat)

        assert sensor.native_value == "temporary_hold"
        assert sensor.icon == "mdi:calendar-clock"

    def test_permanent_hold_when_schedule_disabled(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(schedule=DaikinThermostatSchedule(enabled=False, override=False))
        sensor = DaikinOneScheduleStatusSensor(data=mock_data, device=thermostat)

        assert sensor.native_value == "permanent_hold"
        assert sensor.icon == "mdi:calendar-remove"

        thermostat_override_false = _create_mock_thermostat(
            schedule=DaikinThermostatSchedule(enabled=False, override=True)
        )
        sensor_override_false = DaikinOneScheduleStatusSensor(data=mock_data, device=thermostat_override_false)

        assert sensor_override_false.native_value == "permanent_hold"
        assert sensor_override_false.icon == "mdi:calendar-remove"

    async def test_async_get_device(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat()
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)  # type: ignore[method-assign]
        sensor = DaikinOneScheduleStatusSensor(data=mock_data, device=thermostat)

        dev = await sensor.async_get_device()
        assert dev.id == "device123"


class TestScheduleResumeTimeSensor:
    def test_metadata_and_schema_v1_uid(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat()
        sensor = DaikinOneScheduleResumeTimeSensor(data=mock_data, device=thermostat)

        assert sensor.unique_id == "device123-schedule_resume_time"
        assert sensor.entity_description.key == "schedule_resume_time"
        assert sensor.entity_description.name == "Schedule resume time"
        assert sensor.entity_description.device_class == SensorDeviceClass.TIMESTAMP
        assert sensor.entity_description.entity_category is None
        assert sensor.icon == "mdi:clock-end"

    def test_schema_v0_uid(self) -> None:
        thermostat = _create_mock_thermostat()
        entry_v0 = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 0})
        data_v0 = DaikinOneData(_hass=None, entry=entry_v0, daikin=MagicMock())  # type: ignore[arg-type]
        sensor = DaikinOneScheduleResumeTimeSensor(data=data_v0, device=thermostat)

        assert sensor.unique_id == "device123-Schedule Override Resume Time"

    def test_active_override_returns_timestamp(self, mock_data: DaikinOneData) -> None:
        resume_dt = datetime(2026, 10, 24, 18, 0, 0, tzinfo=UTC)
        thermostat = _create_mock_thermostat(
            schedule=DaikinThermostatSchedule(enabled=True, override=True),
            sched_resume_time=resume_dt,
        )
        sensor = DaikinOneScheduleResumeTimeSensor(data=mock_data, device=thermostat)

        assert sensor.native_value == resume_dt

    def test_no_override_returns_none(self, mock_data: DaikinOneData) -> None:
        resume_dt = datetime(2026, 10, 24, 18, 0, 0, tzinfo=UTC)
        thermostat = _create_mock_thermostat(
            schedule=DaikinThermostatSchedule(enabled=True, override=False),
            sched_resume_time=resume_dt,
        )
        sensor = DaikinOneScheduleResumeTimeSensor(data=mock_data, device=thermostat)

        assert sensor.native_value is None

    def test_schedule_disabled_returns_none(self, mock_data: DaikinOneData) -> None:
        resume_dt = datetime(2026, 10, 24, 18, 0, 0, tzinfo=UTC)
        thermostat = _create_mock_thermostat(
            schedule=DaikinThermostatSchedule(enabled=False, override=True),
            sched_resume_time=resume_dt,
        )
        sensor = DaikinOneScheduleResumeTimeSensor(data=mock_data, device=thermostat)

        assert sensor.native_value is None

    def test_none_resume_time_returns_none(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(
            schedule=DaikinThermostatSchedule(enabled=True, override=True),
            sched_resume_time=None,
        )
        sensor = DaikinOneScheduleResumeTimeSensor(data=mock_data, device=thermostat)

        assert sensor.native_value is None

    async def test_async_get_device(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat()
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)  # type: ignore[method-assign]
        sensor = DaikinOneScheduleResumeTimeSensor(data=mock_data, device=thermostat)

        dev = await sensor.async_get_device()
        assert dev.id == "device123"

    async def test_async_setup_entry_registers_schedule_sensors(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat()
        mock_data.daikin.get_thermostats = MagicMock(return_value={"device123": thermostat})  # type: ignore[method-assign]

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        added_entities: list = []

        def add_entities_callback(entities: list, update_before_add: bool = False) -> None:
            added_entities.extend(entities)

        await async_setup_entry(hass, mock_data.entry, add_entities_callback)

        status_sensors = [e for e in added_entities if isinstance(e, DaikinOneScheduleStatusSensor)]
        resume_sensors = [e for e in added_entities if isinstance(e, DaikinOneScheduleResumeTimeSensor)]

        assert len(status_sensors) == 1
        assert len(resume_sensors) == 1
        assert status_sensors[0].unique_id == "device123-schedule_status"
        assert resume_sensors[0].unique_id == "device123-schedule_resume_time"
