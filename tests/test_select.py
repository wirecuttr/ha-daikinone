"""Tests for Daikin One select platform (fan speed, duty cycle, dual fuel priority)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.select import SelectEntityDescription
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
from custom_components.daikinone.select import (
    FAN_CIRCULATE_DUTY_CYCLE_OPTIONS,
    DaikinOneDualFuelPrioritySelect,
    DaikinOneFanCirculationDutyCycleSelect,
    DaikinOneFanSpeedSelect,
    async_setup_entry,
)
from custom_components.daikinone.utils import Temperature


def _create_mock_thermostat(
    thermostat_id: str = "device123",
    name: str = "Mainfloor",
    fan_speed: DaikinThermostatFanSpeed = DaikinThermostatFanSpeed.LOW,
    fan_circulate_duration: DaikinThermostatFanCirculateDuration | None = DaikinThermostatFanCirculateDuration.MIN_15,
    dual_fuel_furnace_lockout_enable: bool | None = None,
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
        fan_speed=fan_speed,
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
        dual_fuel_furnace_lockout_enable=dual_fuel_furnace_lockout_enable,
        equipment={},
        away_mode=None,
        fan_circulate_start=32,
        fan_circulate_stop=88,
        fan_circulate_duration=fan_circulate_duration,
    )


@pytest.fixture
def mock_data() -> DaikinOneData:
    entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
    client = MagicMock(spec=DaikinOne)
    client.set_thermostat_fan_speed = AsyncMock()
    client.set_thermostat_fan_circulate_duration = AsyncMock()
    client.set_dual_fuel_furnace_lockout_enable = AsyncMock()
    client.get_thermostats = MagicMock(return_value={})
    data = DaikinOneData(_hass=None, entry=entry, daikin=client)  # type: ignore[arg-type]
    data.update = AsyncMock()  # type: ignore[method-assign]
    return data


class TestSelectPlatformSetup:
    async def test_fan_speed_has_config_category(self, mock_data: DaikinOneData) -> None:
        """Verify fan_speed select entity has entity_category == EntityCategory.CONFIG."""
        thermostat = _create_mock_thermostat()
        mock_data.daikin.get_thermostats.return_value = {thermostat.id: thermostat}
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        added_entities = []

        def async_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)  # type: ignore[arg-type]

        fan_speed_entities = [e for e in added_entities if isinstance(e, DaikinOneFanSpeedSelect)]
        assert len(fan_speed_entities) == 1
        speed_entity = fan_speed_entities[0]
        assert speed_entity.entity_description.entity_category == EntityCategory.CONFIG
        assert speed_entity.entity_description.key == "fan_speed"
        assert speed_entity.current_option == "Low"

    async def test_fan_circulation_duty_cycle_created_when_duration_present(self, mock_data: DaikinOneData) -> None:
        """Verify duty cycle select entity is created with correct options and CONFIG category."""
        thermostat = _create_mock_thermostat(fan_circulate_duration=DaikinThermostatFanCirculateDuration.MIN_15)
        mock_data.daikin.get_thermostats.return_value = {thermostat.id: thermostat}
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        added_entities = []

        def async_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)  # type: ignore[arg-type]

        duty_entities = [e for e in added_entities if isinstance(e, DaikinOneFanCirculationDutyCycleSelect)]
        assert len(duty_entities) == 1
        duty = duty_entities[0]
        assert duty.entity_description.key == "fan_circulation_duty_cycle"
        assert duty.entity_description.name == "Fan Circulation Duty Cycle"
        assert duty.entity_description.icon == "mdi:fan-clock"
        assert duty.entity_description.has_entity_name is True
        assert duty.entity_description.entity_category == EntityCategory.CONFIG
        assert duty.entity_description.options == [
            "Continuous",
            "5 min/hr",
            "15 min/hr",
            "30 min/hr",
            "45 min/hr",
        ]
        assert duty.unique_id == "device123-fan_circulation_duty_cycle"
        assert duty.current_option == "15 min/hr"

    async def test_fan_circulation_duty_cycle_omitted_when_duration_none(self, mock_data: DaikinOneData) -> None:
        """Verify duty cycle select entity is omitted when fan_circulate_duration is None."""
        thermostat = _create_mock_thermostat(fan_circulate_duration=None)
        mock_data.daikin.get_thermostats.return_value = {thermostat.id: thermostat}
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        added_entities = []

        def async_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)  # type: ignore[arg-type]

        duty_entities = [e for e in added_entities if isinstance(e, DaikinOneFanCirculationDutyCycleSelect)]
        assert len(duty_entities) == 0

    async def test_dual_fuel_priority_select_created_when_supported(self, mock_data: DaikinOneData) -> None:
        """Verify dual fuel priority select is created when dual_fuel_furnace_lockout_enable is not None."""
        thermostat = _create_mock_thermostat(dual_fuel_furnace_lockout_enable=True)
        mock_data.daikin.get_thermostats.return_value = {thermostat.id: thermostat}
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        added_entities = []

        def async_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)  # type: ignore[arg-type]

        df_entities = [e for e in added_entities if isinstance(e, DaikinOneDualFuelPrioritySelect)]
        assert len(df_entities) == 1
        df = df_entities[0]
        assert df.current_option == "Efficiency"
        assert df.entity_description.entity_category == EntityCategory.CONFIG


class TestFanCirculationDutyCycleSelect:
    @pytest.mark.parametrize(
        ("option", "expected_duration"),
        [
            ("Continuous", DaikinThermostatFanCirculateDuration.CONTINUOUS),
            ("5 min/hr", DaikinThermostatFanCirculateDuration.MIN_5),
            ("15 min/hr", DaikinThermostatFanCirculateDuration.MIN_15),
            ("30 min/hr", DaikinThermostatFanCirculateDuration.MIN_30),
            ("45 min/hr", DaikinThermostatFanCirculateDuration.MIN_45),
        ],
    )
    async def test_select_option_optimistic(
        self,
        mock_data: DaikinOneData,
        option: str,
        expected_duration: DaikinThermostatFanCirculateDuration,
    ) -> None:
        """Verify selecting an option calls API and updates state optimistically."""
        thermostat = _create_mock_thermostat(fan_circulate_duration=DaikinThermostatFanCirculateDuration.CONTINUOUS)
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        duty = DaikinOneFanCirculationDutyCycleSelect(
            SelectEntityDescription(
                key="fan_circulation_duty_cycle",
                options=list(FAN_CIRCULATE_DUTY_CYCLE_OPTIONS.keys()),
            ),
            mock_data,
            thermostat,
        )
        duty.async_write_ha_state = MagicMock()

        await duty.async_select_option(option)
        mock_data.daikin.set_thermostat_fan_circulate_duration.assert_called_once_with(thermostat.id, expected_duration)
        assert duty.current_option == option
        assert thermostat.fan_circulate_duration == expected_duration

    async def test_select_unsupported_option_raises(self, mock_data: DaikinOneData) -> None:
        """Verify setting an unknown option raises ValueError."""
        thermostat = _create_mock_thermostat()
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        duty = DaikinOneFanCirculationDutyCycleSelect(
            SelectEntityDescription(
                key="fan_circulation_duty_cycle",
                options=list(FAN_CIRCULATE_DUTY_CYCLE_OPTIONS.keys()),
            ),
            mock_data,
            thermostat,
        )

        with pytest.raises(ValueError, match="Attempted to set unsupported fan circulation duty cycle"):
            await duty.async_select_option("60 min/hr")

    def test_current_option_none_when_device_duration_none(self, mock_data: DaikinOneData) -> None:
        """Verify current_option returns None if fan_circulate_duration is None or unknown."""
        thermostat = _create_mock_thermostat(fan_circulate_duration=None)
        duty = DaikinOneFanCirculationDutyCycleSelect(
            SelectEntityDescription(key="fan_circulation_duty_cycle"),
            mock_data,
            thermostat,
        )
        assert duty.current_option is None

    def test_current_option_none_when_unknown_duration(self, mock_data: DaikinOneData) -> None:
        """Verify current_option returns None if fan_circulate_duration is UNKNOWN."""
        thermostat = _create_mock_thermostat(fan_circulate_duration=DaikinThermostatFanCirculateDuration.UNKNOWN)
        duty = DaikinOneFanCirculationDutyCycleSelect(
            SelectEntityDescription(key="fan_circulation_duty_cycle"),
            mock_data,
            thermostat,
        )
        assert duty.current_option is None

    async def test_unique_id_schema_versions(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat()

        # Schema v0
        entry_v0 = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 0})
        data_v0 = DaikinOneData(_hass=None, entry=entry_v0, daikin=mock_data.daikin)  # type: ignore[arg-type]
        duty_v0 = DaikinOneFanCirculationDutyCycleSelect(
            SelectEntityDescription(key="fan_circulation_duty_cycle"), data_v0, thermostat
        )
        assert duty_v0.unique_id == "device123-fan_circulation_duty_cycle"

        # Schema v1
        entry_v1 = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
        data_v1 = DaikinOneData(_hass=None, entry=entry_v1, daikin=mock_data.daikin)  # type: ignore[arg-type]
        duty_v1 = DaikinOneFanCirculationDutyCycleSelect(
            SelectEntityDescription(key="fan_circulation_duty_cycle"), data_v1, thermostat
        )
        assert duty_v1.unique_id == "device123-fan_circulation_duty_cycle"

        # Invalid Schema
        entry_inv = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 99})
        data_inv = DaikinOneData(_hass=None, entry=entry_inv, daikin=mock_data.daikin)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="unexpected entity uid schema version"):
            DaikinOneFanCirculationDutyCycleSelect(
                SelectEntityDescription(key="fan_circulation_duty_cycle"), data_inv, thermostat
            )
