"""Tests for Daikin One climate platform, preset modes, and concurrency."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import ClimateEntityDescription
from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_NONE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.switch import SwitchEntityDescription

from custom_components.daikinone import DaikinOneData
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
    away_mode: bool | None = None,
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
        status=DaikinThermostatStatus.IDLE,
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
        one_clean_fan_active=None,
        dual_fuel_furnace_lockout_enable=None,
        equipment={},
        away_mode=away_mode,
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

        # Thermostat supporting away mode and emergency heat
        t_full = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.HEAT, DaikinThermostatCapability.EMERGENCY_HEAT},
            away_mode=False,
        )
        c_full = DaikinOneThermostat(_climate_desc(), mock_data, t_full)
        assert PRESET_NONE in c_full.preset_modes
        assert PRESET_AWAY in c_full.preset_modes
        assert DaikinOneThermostatPresetMode.EMERGENCY_HEAT.value in c_full.preset_modes
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

    async def test_climate_preset_mode_none_restores_heat_from_aux_heat(self, mock_data: DaikinOneData) -> None:
        """Verify selecting preset_mode='none' when in AUX_HEAT calls set_thermostat_mode(HEAT)."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.AUX_HEAT,
            away_mode=False,
        )
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        climate = DaikinOneThermostat(_climate_desc(), mock_data, thermostat)
        climate.async_write_ha_state = MagicMock()

        await climate.async_set_preset_mode(PRESET_NONE)
        mock_data.daikin.set_thermostat_mode.assert_called_once_with(thermostat.id, DaikinThermostatMode.HEAT)

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

        # Both states are active and faithfully reported concurrently!
        assert switch.is_on is True
        assert climate.preset_mode == PRESET_AWAY
        assert climate.hvac_mode == HVACMode.HEAT
