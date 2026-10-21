"""Tests for Daikin One time platform (fan circulation start and stop times)."""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.time import TimeEntityDescription
from homeassistant.const import EntityCategory

from custom_components.daikinone import DOMAIN, DaikinOneData
from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.models import (
    DaikinThermostat,
    DaikinThermostatCapability,
    DaikinThermostatFanCirculateDuration,
    DaikinThermostatFanMode,
    DaikinThermostatFanSpeed,
    DaikinThermostatMode,
    DaikinThermostatSchedule,
    DaikinThermostatStatus,
)
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.time import (
    DaikinOneFanCirculationStartTime,
    DaikinOneFanCirculationStopTime,
    _slot_to_time,
    _time_to_slot,
    async_setup_entry,
)
from custom_components.daikinone.utils import Temperature


def _create_mock_thermostat(
    thermostat_id: str = "device123",
    name: str = "Mainfloor",
    fan_circulate_start: int | None = 32,
    fan_circulate_stop: int | None = 88,
    fan_circulate_duration: DaikinThermostatFanCirculateDuration | None = DaikinThermostatFanCirculateDuration.MIN_15,
) -> DaikinThermostat:
    return DaikinThermostat(
        id=thermostat_id,
        location_id="loc456",
        name=name,
        model="ONEPLUS",
        firmware_version="1.0.0",
        online=True,
        capabilities={DaikinThermostatCapability.HEAT, DaikinThermostatCapability.COOL},
        mode=DaikinThermostatMode.HEAT,
        status=DaikinThermostatStatus.IDLE,
        fan_mode=DaikinThermostatFanMode.SCHEDULED,
        fan_speed=DaikinThermostatFanSpeed.LOW,
        schedule=DaikinThermostatSchedule(enabled=True, override=False),
        indoor_temperature=Temperature.from_celsius(21.0),
        indoor_humidity=45,
        set_point_heat=Temperature.from_celsius(20.0),
        set_point_heat_min=Temperature.from_celsius(10.0),
        set_point_heat_max=Temperature.from_celsius(30.0),
        set_point_cool=Temperature.from_celsius(24.0),
        set_point_cool_min=Temperature.from_celsius(18.0),
        set_point_cool_max=Temperature.from_celsius(32.0),
        outdoor_temperature=Temperature.from_celsius(10.0),
        outdoor_humidity=60,
        air_quality_outdoor=None,
        air_quality_indoor=None,
        one_clean_fan_active=None,
        dual_fuel_furnace_lockout_enable=None,
        equipment={},
        away_mode=None,
        fan_circulate_start=fan_circulate_start,
        fan_circulate_stop=fan_circulate_stop,
        fan_circulate_duration=fan_circulate_duration,
    )


@pytest.fixture
def mock_data() -> DaikinOneData:
    entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
    client = MagicMock(spec=DaikinOne)
    client.set_thermostat_fan_circulate_start = AsyncMock()
    client.set_thermostat_fan_circulate_stop = AsyncMock()
    client.get_thermostats = MagicMock(return_value={})
    data = DaikinOneData(_hass=None, entry=entry, daikin=client)  # type: ignore[arg-type]
    data.update = AsyncMock()  # type: ignore[method-assign]
    return data


class TestSlotConversionHelpers:
    @pytest.mark.parametrize(
        ("slot", "expected_time"),
        [
            (0, datetime.time(0, 0)),
            (1, datetime.time(0, 15)),
            (4, datetime.time(1, 0)),
            (32, datetime.time(8, 0)),
            (88, datetime.time(22, 0)),
            (95, datetime.time(23, 45)),
        ],
    )
    def test_slot_to_time_valid(self, slot: int, expected_time: datetime.time) -> None:
        assert _slot_to_time(slot) == expected_time

    @pytest.mark.parametrize("invalid_slot", [-1, 96, 255, None])
    def test_slot_to_time_invalid_or_none(self, invalid_slot: int | None) -> None:
        assert _slot_to_time(invalid_slot) is None

    @pytest.mark.parametrize(
        ("input_time", "expected_slot"),
        [
            (datetime.time(0, 0), 0),
            (datetime.time(0, 7), 0),
            (datetime.time(0, 8), 1),
            (datetime.time(0, 15), 1),
            (datetime.time(8, 0), 32),
            (datetime.time(8, 7), 32),
            (datetime.time(8, 8), 33),
            (datetime.time(22, 0), 88),
            (datetime.time(23, 45), 95),
            (datetime.time(23, 52), 95),
            (datetime.time(23, 53), 0),  # wrap-around at midnight
        ],
    )
    def test_time_to_slot_rounding(self, input_time: datetime.time, expected_slot: int) -> None:
        assert _time_to_slot(input_time) == expected_slot


class TestTimePlatformSetup:
    async def test_setup_entry_creates_entities_when_supported(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(fan_circulate_start=32, fan_circulate_stop=88)
        mock_data.daikin.get_thermostats.return_value = {thermostat.id: thermostat}
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        added_entities = []

        def async_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)  # type: ignore[arg-type]

        start_entities = [e for e in added_entities if isinstance(e, DaikinOneFanCirculationStartTime)]
        stop_entities = [e for e in added_entities if isinstance(e, DaikinOneFanCirculationStopTime)]
        assert len(start_entities) == 1
        assert len(stop_entities) == 1

        start = start_entities[0]
        assert start.entity_description.key == "fan_circulation_start"
        assert start.entity_description.name == "Fan Circulation Start Time"
        assert start.entity_description.icon == "mdi:clock-start"
        assert start.entity_description.has_entity_name is True
        assert start.entity_description.entity_category == EntityCategory.CONFIG
        assert start.unique_id == "device123-fan_circulation_start"
        assert start.native_value == datetime.time(8, 0)

        stop = stop_entities[0]
        assert stop.entity_description.key == "fan_circulation_stop"
        assert stop.entity_description.name == "Fan Circulation Stop Time"
        assert stop.entity_description.icon == "mdi:clock-end"
        assert stop.entity_description.has_entity_name is True
        assert stop.entity_description.entity_category == EntityCategory.CONFIG
        assert stop.unique_id == "device123-fan_circulation_stop"
        assert stop.native_value == datetime.time(22, 0)

    async def test_setup_entry_omits_entities_when_fan_circulate_none(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(fan_circulate_start=None, fan_circulate_stop=None)
        mock_data.daikin.get_thermostats.return_value = {thermostat.id: thermostat}
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        added_entities = []

        def async_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)  # type: ignore[arg-type]

        assert len(added_entities) == 0


class TestTimeEntities:
    async def test_start_time_set_value_optimistic(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(fan_circulate_start=32, fan_circulate_stop=88)
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        start = DaikinOneFanCirculationStartTime(
            TimeEntityDescription(key="fan_circulation_start"), mock_data, thermostat
        )
        start.async_write_ha_state = MagicMock()

        await start.async_set_value(datetime.time(9, 15))
        # 9:15 is slot (9*60+15)/15 = 555/15 = 37
        mock_data.daikin.set_thermostat_fan_circulate_start.assert_called_once_with(thermostat.id, 37)
        assert start.native_value == datetime.time(9, 15)

    async def test_stop_time_set_value_optimistic(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(fan_circulate_start=32, fan_circulate_stop=88)
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        stop = DaikinOneFanCirculationStopTime(TimeEntityDescription(key="fan_circulation_stop"), mock_data, thermostat)
        stop.async_write_ha_state = MagicMock()

        await stop.async_set_value(datetime.time(21, 30))
        # 21:30 is slot (21*60+30)/15 = 1290/15 = 86
        mock_data.daikin.set_thermostat_fan_circulate_stop.assert_called_once_with(thermostat.id, 86)
        assert stop.native_value == datetime.time(21, 30)

    async def test_unique_id_schema_versions(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat()

        # Schema v0
        entry_v0 = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 0})
        data_v0 = DaikinOneData(_hass=None, entry=entry_v0, daikin=mock_data.daikin)  # type: ignore[arg-type]
        start_v0 = DaikinOneFanCirculationStartTime(
            TimeEntityDescription(key="fan_circulation_start"), data_v0, thermostat
        )
        assert start_v0.unique_id == "device123-fan_circulation_start"

        # Schema v1
        entry_v1 = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
        data_v1 = DaikinOneData(_hass=None, entry=entry_v1, daikin=mock_data.daikin)  # type: ignore[arg-type]
        stop_v1 = DaikinOneFanCirculationStopTime(
            TimeEntityDescription(key="fan_circulation_stop"), data_v1, thermostat
        )
        assert stop_v1.unique_id == "device123-fan_circulation_stop"

        # Invalid Schema
        entry_inv = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 99})
        data_inv = DaikinOneData(_hass=None, entry=entry_inv, daikin=mock_data.daikin)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="unexpected entity uid schema version"):
            DaikinOneFanCirculationStartTime(TimeEntityDescription(key="fan_circulation_start"), data_inv, thermostat)
