"""Tests for Daikin One climate platform, preset modes, and native HVAC actions."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import ClimateEntityDescription
from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_NONE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.switch import SwitchEntityDescription

from custom_components.daikinone import DaikinOneData
from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.models import (
    DaikinIndoorUnit,
    DaikinOutdoorUnit,
    DaikinOutdoorUnitHeaterStatus,
    DaikinOutdoorUnitReversingValveStatus,
    DaikinThermostat,
    DaikinThermostatCapability,
    DaikinThermostatFanMode,
    DaikinThermostatFanSpeed,
    DaikinThermostatMode,
    DaikinThermostatSchedule,
    DaikinThermostatStatus,
)
from custom_components.daikinone.climate import (
    DaikinOneThermostat,
    DaikinOneThermostatPresetMode,
)
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.switch import DaikinOneEmergencyHeatSwitch
from custom_components.daikinone.utils import Temperature


def _create_mock_thermostat(
    thermostat_id: str = "device123",
    name: str = "Living Room",
    capabilities: set[DaikinThermostatCapability] | None = None,
    mode: DaikinThermostatMode = DaikinThermostatMode.HEAT,
    status: DaikinThermostatStatus = DaikinThermostatStatus.IDLE,
    away_mode: bool | None = None,
    equipment: dict | None = None,
    hum_setpoint: int | None = 45,
    dehum_setpoint: int | None = 55,
    humidification_available: bool = False,
    dehumidification_available: bool = False,
) -> DaikinThermostat:
    return DaikinThermostat(
        id=thermostat_id,
        location_id="loc456",
        name=name,
        model="ONEPLUS",
        firmware_version="1.0.0",
        online=True,
        capabilities=capabilities if capabilities is not None else {DaikinThermostatCapability.HEAT},
        mode=mode,
        status=status,
        fan_mode=DaikinThermostatFanMode.OFF,
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
        hum_setpoint=hum_setpoint,
        dehum_setpoint=dehum_setpoint,
        humidification_available=humidification_available,
        dehumidification_available=dehumidification_available,
        one_clean_fan_active=None,
        dual_fuel_furnace_lockout_enable=None,
        equipment=equipment if equipment is not None else {},
        away_mode=away_mode,
    )


def _create_outdoor_unit(
    mode: str | None = None,
    compressor_speed: int = 0,
    heat_demand: int = 0,
) -> DaikinOutdoorUnit:
    return DaikinOutdoorUnit(
        id="OD-123",
        thermostat_id="device123",
        name="Heat Pump",
        model="OD-MODEL",
        serial="OD-SERIAL",
        firmware_version="1.0.0",
        inverter_software_version="1.0.0",
        total_runtime=None,
        mode=mode,
        compressor_speed_target=compressor_speed,
        compressor_speed_current=compressor_speed,
        outdoor_fan_target_rpm=None,
        outdoor_fan_rpm=None,
        suction_pressure_psi=None,
        eev_opening_percent=None,
        reversing_valve=DaikinOutdoorUnitReversingValveStatus.UNKNOWN,
        heat_demand_percent=heat_demand,
        cool_demand_percent=None,
        fan_demand_percent=None,
        fan_demand_airflow=None,
        dehumidify_demand_percent=None,
        air_temperature=None,
        coil_temperature=None,
        discharge_temperature=None,
        liquid_temperature=None,
        defrost_sensor_temperature=None,
        inverter_fin_temperature=None,
        power_usage=None,
        compressor_amps=None,
        inverter_amps=None,
        fan_motor_amps=None,
        crank_case_heater=DaikinOutdoorUnitHeaterStatus.UNKNOWN,
        drain_pan_heater=DaikinOutdoorUnitHeaterStatus.UNKNOWN,
        preheat_heater=DaikinOutdoorUnitHeaterStatus.UNKNOWN,
    )


def _create_indoor_unit(
    airflow: int = 0,
    heat_demand: int = 0,
) -> DaikinIndoorUnit:
    return DaikinIndoorUnit(
        id="AH-123",
        thermostat_id="device123",
        name="Air Handler",
        model="AH-MODEL",
        firmware_version="1.0.0",
        serial="AH-SERIAL",
        mode=None,
        current_airflow=airflow,
        fan_demand_requested_percent=None,
        fan_demand_current_percent=None,
        heat_demand_requested_percent=heat_demand,
        heat_demand_current_percent=heat_demand,
        cool_demand_requested_percent=None,
        cool_demand_current_percent=None,
        humidification_demand_requested_percent=None,
        dehumidification_demand_requested_percent=None,
        power_usage=None,
    )


@pytest.fixture
def mock_data() -> DaikinOneData:
    entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
    client = MagicMock(spec=DaikinOne)
    client.set_thermostat_mode = AsyncMock()
    client.set_thermostat_away_mode = AsyncMock()
    client.get_thermostats = MagicMock(return_value={})
    data = DaikinOneData(_hass=None, entry=entry, daikin=client)  # type: ignore[arg-type]
    data.update = AsyncMock()  # type: ignore[method-assign]
    return data


def _climate_desc() -> ClimateEntityDescription:
    return ClimateEntityDescription(key="device123", has_entity_name=True, name=None)


class TestClimatePresets:
    async def test_preset_modes_supported_features(self, mock_data: DaikinOneData) -> None:
        """Verify preset_modes and PRESET_MODE feature flag according to hardware capabilities."""
        # Baseline thermostat without away or emergency heat
        t_base = _create_mock_thermostat(capabilities={DaikinThermostatCapability.HEAT}, away_mode=None)
        c_base = DaikinOneThermostat(_climate_desc(), mock_data, t_base)
        assert c_base.preset_modes == [DaikinOneThermostatPresetMode.NONE.value]
        assert not (c_base.supported_features & ClimateEntityFeature.PRESET_MODE)

        # Thermostat supporting away mode
        t_away = _create_mock_thermostat(capabilities={DaikinThermostatCapability.HEAT}, away_mode=False)
        c_away = DaikinOneThermostat(_climate_desc(), mock_data, t_away)
        assert PRESET_NONE in c_away.preset_modes
        assert PRESET_AWAY in c_away.preset_modes
        assert c_away.supported_features & ClimateEntityFeature.PRESET_MODE

        # Thermostat supporting away mode and emergency heat (emergency heat is on switch platform, not in presets)
        t_full = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.HEAT, DaikinThermostatCapability.EMERGENCY_HEAT},
            away_mode=False,
        )
        c_full = DaikinOneThermostat(_climate_desc(), mock_data, t_full)
        assert c_full.preset_modes == [PRESET_NONE, PRESET_AWAY]
        assert DaikinOneThermostatPresetMode.EMERGENCY_HEAT.value not in c_full.preset_modes
        assert c_full.supported_features & ClimateEntityFeature.PRESET_MODE

    async def test_climate_preset_mode_away_activation(self, mock_data: DaikinOneData) -> None:
        """Verify selecting preset_mode='away' calls set_thermostat_away_mode(True)."""
        thermostat = _create_mock_thermostat(away_mode=False)
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        climate = DaikinOneThermostat(_climate_desc(), mock_data, thermostat)
        climate.async_write_ha_state = MagicMock()

        await climate.async_set_preset_mode(PRESET_AWAY)
        mock_data.daikin.set_thermostat_away_mode.assert_called_once_with(thermostat.id, True)
        assert climate.preset_mode == PRESET_AWAY

    async def test_climate_preset_mode_none_deactivates_away(self, mock_data: DaikinOneData) -> None:
        """Verify selecting preset_mode='none' when away calls set_thermostat_away_mode(False)."""
        thermostat = _create_mock_thermostat(away_mode=True)
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        climate = DaikinOneThermostat(_climate_desc(), mock_data, thermostat)
        climate.async_write_ha_state = MagicMock()

        await climate.async_set_preset_mode(PRESET_NONE)
        mock_data.daikin.set_thermostat_away_mode.assert_called_once_with(thermostat.id, False)
        assert climate.preset_mode == PRESET_NONE

    async def test_climate_preset_mode_none_preserves_aux_heat(self, mock_data: DaikinOneData) -> None:
        """Verify selecting preset_mode='none' does not turn off AUX_HEAT mode (orthogonal control)."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.AUX_HEAT,
            away_mode=True,
        )
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        climate = DaikinOneThermostat(_climate_desc(), mock_data, thermostat)
        climate.async_write_ha_state = MagicMock()

        await climate.async_set_preset_mode(PRESET_NONE)
        mock_data.daikin.set_thermostat_away_mode.assert_called_once_with(thermostat.id, False)
        # Verify mode was NOT changed away from AUX_HEAT
        mock_data.daikin.set_thermostat_mode.assert_not_called()

    async def test_climate_emergency_heat_preset_alias_warning(
        self, mock_data: DaikinOneData, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify selecting preset_mode='emergency_heat' logs a deprecation warning and delegates to AUX_HEAT."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.HEAT,
        )
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        climate = DaikinOneThermostat(_climate_desc(), mock_data, thermostat)
        climate.async_write_ha_state = MagicMock()

        with caplog.at_level(logging.WARNING):
            await climate.async_set_preset_mode("emergency_heat")

        assert "deprecated and will be removed in v2.0" in caplog.text
        mock_data.daikin.set_thermostat_mode.assert_called_once_with(thermostat.id, DaikinThermostatMode.AUX_HEAT)

    async def test_climate_unsupported_preset_mode_raises(self, mock_data: DaikinOneData) -> None:
        """Verify setting an unknown preset mode raises ValueError."""
        thermostat = _create_mock_thermostat(away_mode=False)
        climate = DaikinOneThermostat(_climate_desc(), mock_data, thermostat)

        with pytest.raises(ValueError, match="Attempted to set unsupported preset mode: invalid_preset"):
            await climate.async_set_preset_mode("invalid_preset")

    async def test_full_concurrency_emergency_heat_and_away(self, mock_data: DaikinOneData) -> None:
        """Verify emergency heat switch and away preset operate simultaneously with zero collision."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.AUX_HEAT,
            away_mode=True,
        )
        switch = DaikinOneEmergencyHeatSwitch(SwitchEntityDescription(key="emergency_heat"), mock_data, thermostat)
        climate = DaikinOneThermostat(_climate_desc(), mock_data, thermostat)

        switch.update_entity_attributes()
        climate.update_entity_attributes()

        assert switch.is_on is True
        assert climate.preset_mode == PRESET_AWAY
        assert climate.hvac_mode == HVACMode.HEAT


class TestClimateHVACAction:
    """Test native HVAC actions on DaikinOneThermostat."""

    async def test_hvac_action_idle(self, mock_data: DaikinOneData) -> None:
        t = _create_mock_thermostat(status=DaikinThermostatStatus.IDLE)
        climate = DaikinOneThermostat(_climate_desc(), mock_data, t)
        climate.update_entity_attributes()
        assert climate.hvac_action == HVACAction.IDLE

    async def test_hvac_action_cooling(self, mock_data: DaikinOneData) -> None:
        t = _create_mock_thermostat(status=DaikinThermostatStatus.COOLING)
        climate = DaikinOneThermostat(_climate_desc(), mock_data, t)
        climate.update_entity_attributes()
        assert climate.hvac_action == HVACAction.COOLING

    async def test_hvac_action_drying(self, mock_data: DaikinOneData) -> None:
        t = _create_mock_thermostat(status=DaikinThermostatStatus.DRYING)
        climate = DaikinOneThermostat(_climate_desc(), mock_data, t)
        climate.update_entity_attributes()
        assert climate.hvac_action == HVACAction.DRYING

    async def test_hvac_action_fan(self, mock_data: DaikinOneData) -> None:
        t = _create_mock_thermostat(status=DaikinThermostatStatus.CIRCULATING_AIR)
        climate = DaikinOneThermostat(_climate_desc(), mock_data, t)
        climate.update_entity_attributes()
        assert climate.hvac_action == HVACAction.FAN

    async def test_hvac_action_heating(self, mock_data: DaikinOneData) -> None:
        od = _create_outdoor_unit(mode="Heating", compressor_speed=50, heat_demand=80)
        ah = _create_indoor_unit(airflow=450, heat_demand=80)
        t = _create_mock_thermostat(
            status=DaikinThermostatStatus.HEATING,
            equipment={"od": od, "ah": ah},
        )
        climate = DaikinOneThermostat(_climate_desc(), mock_data, t)
        climate.update_entity_attributes()
        assert climate.hvac_action == HVACAction.HEATING

    async def test_hvac_action_defrosting(self, mock_data: DaikinOneData) -> None:
        od = _create_outdoor_unit(mode="Defrost", compressor_speed=60, heat_demand=100)
        ah = _create_indoor_unit(airflow=400, heat_demand=50)
        t = _create_mock_thermostat(
            status=DaikinThermostatStatus.HEATING,
            equipment={"od": od, "ah": ah},
        )
        climate = DaikinOneThermostat(_climate_desc(), mock_data, t)
        climate.update_entity_attributes()
        assert climate.hvac_action == HVACAction.DEFROSTING

    async def test_hvac_action_preheating_startup_mode(self, mock_data: DaikinOneData) -> None:
        od = _create_outdoor_unit(mode="Heating startup", compressor_speed=30, heat_demand=50)
        ah = _create_indoor_unit(airflow=0, heat_demand=50)
        t = _create_mock_thermostat(
            status=DaikinThermostatStatus.HEATING,
            equipment={"od": od, "ah": ah},
        )
        climate = DaikinOneThermostat(_climate_desc(), mock_data, t)
        climate.update_entity_attributes()
        assert climate.hvac_action == HVACAction.PREHEATING

    async def test_hvac_action_preheating_zero_airflow(self, mock_data: DaikinOneData) -> None:
        od = _create_outdoor_unit(mode="Heating", compressor_speed=30, heat_demand=50)
        ah = _create_indoor_unit(airflow=0, heat_demand=50)
        t = _create_mock_thermostat(
            status=DaikinThermostatStatus.HEATING,
            equipment={"od": od, "ah": ah},
        )
        climate = DaikinOneThermostat(_climate_desc(), mock_data, t)
        climate.update_entity_attributes()
        assert climate.hvac_action == HVACAction.PREHEATING


_make_mock_thermostat = _create_mock_thermostat


class TestTargetHumidityFeatureFlag:
    def test_target_humidity_supported_when_humidification_available(self, mock_data: DaikinOneData) -> None:
        thermostat = _make_mock_thermostat(humidification_available=True)
        entity = DaikinOneThermostat(
            _climate_desc(),
            mock_data,
            thermostat,
        )
        assert ClimateEntityFeature.TARGET_HUMIDITY in entity.supported_features
        assert entity.min_humidity == 25
        assert entity.max_humidity == 65
        assert entity.target_humidity == 45

    def test_target_humidity_supported_when_dehumidification_available(self, mock_data: DaikinOneData) -> None:
        thermostat = _make_mock_thermostat(dehumidification_available=True)
        entity = DaikinOneThermostat(
            _climate_desc(),
            mock_data,
            thermostat,
        )
        assert ClimateEntityFeature.TARGET_HUMIDITY in entity.supported_features
        assert entity.min_humidity == 25
        assert entity.max_humidity == 65

    def test_target_humidity_not_supported_when_neither_available(self, mock_data: DaikinOneData) -> None:
        thermostat = _make_mock_thermostat(
            humidification_available=False,
            dehumidification_available=False,
        )
        entity = DaikinOneThermostat(
            _climate_desc(),
            mock_data,
            thermostat,
        )
        assert ClimateEntityFeature.TARGET_HUMIDITY not in entity.supported_features

    def test_target_humidity_none_when_unconfigured(self, mock_data: DaikinOneData) -> None:
        thermostat = _make_mock_thermostat(
            humidification_available=True,
            hum_setpoint=None,
        )
        entity = DaikinOneThermostat(
            _climate_desc(),
            mock_data,
            thermostat,
        )
        assert entity.target_humidity is None


class TestClimateAsyncSetHumidity:
    async def test_async_set_humidity(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from custom_components.daikinone.client.models import DaikinUserCredentials

        creds = DaikinUserCredentials(email="test@example.com", password="password")
        daikin_client = DaikinOne(creds)
        thermostat = _make_mock_thermostat(humidification_available=True, hum_setpoint=40)
        daikin_client._DaikinOne__thermostats[thermostat.id] = thermostat

        mock_data = DaikinOneData(
            _hass=None,
            entry=SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1}),
            daikin=daikin_client,
        )

        entity = DaikinOneThermostat(
            _climate_desc(),
            mock_data,
            thermostat,
        )
        entity.async_write_ha_state = MagicMock()

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            with patch.object(mock_data, "update", new_callable=AsyncMock):
                await entity.async_set_humidity(50)

            mock_req.assert_awaited_once_with(
                url="https://api.daikinskyport.com/deviceData/device123",
                method="PUT",
                body={"humSP": 50},
            )
        assert entity.target_humidity == 50
        assert entity._attr_target_humidity == 50


class TestClientHumidityControls:
    async def test_set_humidity(self) -> None:
        from unittest.mock import AsyncMock, patch

        from custom_components.daikinone.client.models import DaikinUserCredentials

        creds = DaikinUserCredentials(email="test@example.com", password="password")
        daikin_client = DaikinOne(creds)
        thermostat = _make_mock_thermostat(hum_setpoint=40)
        daikin_client._DaikinOne__thermostats[thermostat.id] = thermostat

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            await daikin_client.set_humidity("device123", 45)

            mock_req.assert_awaited_once_with(
                url="https://api.daikinskyport.com/deviceData/device123",
                method="PUT",
                body={"humSP": 45},
            )
        assert daikin_client.get_thermostat("device123").hum_setpoint == 45

    async def test_set_dehumidify_setpoint(self) -> None:
        from unittest.mock import AsyncMock, patch

        from custom_components.daikinone.client.models import DaikinUserCredentials

        creds = DaikinUserCredentials(email="test@example.com", password="password")
        daikin_client = DaikinOne(creds)
        thermostat = _make_mock_thermostat(dehum_setpoint=60)
        daikin_client._DaikinOne__thermostats[thermostat.id] = thermostat

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            await daikin_client.set_dehumidify_setpoint("device123", 55)

            mock_req.assert_awaited_once_with(
                url="https://api.daikinskyport.com/deviceData/device123",
                method="PUT",
                body={"dehumSP": 55},
            )
        assert daikin_client.get_thermostat("device123").dehum_setpoint == 55
