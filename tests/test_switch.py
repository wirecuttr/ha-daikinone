"""Tests for Daikin One switch platform, focusing on DaikinOneEmergencyHeatSwitch."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.switch import SwitchEntityDescription

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
from custom_components.daikinone.switch import (
    DaikinOneEmergencyHeatSwitch,
    DaikinOneNightModeSwitch,
    async_setup_entry,
)
from custom_components.daikinone.utils import Temperature


def _create_mock_thermostat(
    thermostat_id: str = "device123",
    name: str = "Living Room",
    capabilities: set[DaikinThermostatCapability] | None = None,
    mode: DaikinThermostatMode = DaikinThermostatMode.HEAT,
    away_mode: bool | None = None,
    one_clean_fan_active: bool | None = None,
    night_mode_enabled: bool | None = None,
    night_mode_active: bool | None = None,
    night_mode_start: int | None = None,
    night_mode_stop: int | None = None,
    night_mode_light_bar_allowed: bool | None = None,
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
        one_clean_fan_active=one_clean_fan_active,
        dual_fuel_furnace_lockout_enable=None,
        equipment={},
        away_mode=away_mode,
        night_mode_enabled=night_mode_enabled,
        night_mode_active=night_mode_active,
        night_mode_start=night_mode_start,
        night_mode_stop=night_mode_stop,
        night_mode_light_bar_allowed=night_mode_light_bar_allowed,
    )


@pytest.fixture
def mock_data() -> DaikinOneData:
    entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
    client = MagicMock(spec=DaikinOne)
    client.set_thermostat_mode = AsyncMock()
    client.set_thermostat_night_mode = AsyncMock()
    client.get_thermostats = MagicMock(return_value={})
    data = DaikinOneData(_hass=None, entry=entry, daikin=client)  # type: ignore[arg-type]
    data.update = AsyncMock()  # type: ignore[method-assign]
    return data


class TestEmergencyHeatSwitch:
    async def test_emergency_heat_switch_creation_when_capable(self, mock_data: DaikinOneData) -> None:
        """Verify emergency heat switch is created when thermostat has EMERGENCY_HEAT capability."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.HEAT, DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.HEAT,
        )
        mock_data.daikin.get_thermostats.return_value = {thermostat.id: thermostat}
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        added_entities = []

        def async_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)  # type: ignore[arg-type]

        emergency_heat_switches = [s for s in added_entities if isinstance(s, DaikinOneEmergencyHeatSwitch)]
        assert len(emergency_heat_switches) == 1
        switch = emergency_heat_switches[0]
        assert switch.is_on is False
        assert switch.entity_description.key == "emergency_heat"
        assert switch.entity_description.icon == "mdi:radiator"
        assert switch.unique_id == "device123-emergency_heat"
        assert switch.device_name == "Living Room Thermostat"

    async def test_emergency_heat_switch_omitted_when_not_capable(self, mock_data: DaikinOneData) -> None:
        """Verify emergency heat switch is NOT created when thermostat lacks EMERGENCY_HEAT capability."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.HEAT},
            mode=DaikinThermostatMode.HEAT,
        )
        mock_data.daikin.get_thermostats.return_value = {thermostat.id: thermostat}
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        added_entities = []

        def async_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)  # type: ignore[arg-type]

        emergency_heat_switches = [s for s in added_entities if isinstance(s, DaikinOneEmergencyHeatSwitch)]
        assert len(emergency_heat_switches) == 0

    async def test_emergency_heat_switch_is_on_state(self, mock_data: DaikinOneData) -> None:
        """Verify is_on reflects whether thermostat mode is AUX_HEAT."""
        thermostat_aux = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.AUX_HEAT,
        )
        switch_on = DaikinOneEmergencyHeatSwitch(
            SwitchEntityDescription(key="emergency_heat"), mock_data, thermostat_aux
        )
        assert switch_on.is_on is True

        thermostat_heat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.HEAT,
        )
        switch_off = DaikinOneEmergencyHeatSwitch(
            SwitchEntityDescription(key="emergency_heat"), mock_data, thermostat_heat
        )
        assert switch_off.is_on is False

    async def test_emergency_heat_switch_turn_on(self, mock_data: DaikinOneData) -> None:
        """Verify async_turn_on calls set_thermostat_mode with AUX_HEAT and updates optimistically."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.HEAT,
        )
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        switch = DaikinOneEmergencyHeatSwitch(SwitchEntityDescription(key="emergency_heat"), mock_data, thermostat)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_on()
        mock_data.daikin.set_thermostat_mode.assert_called_once_with(thermostat.id, DaikinThermostatMode.AUX_HEAT)
        assert switch.is_on is True

    async def test_emergency_heat_switch_turn_off(self, mock_data: DaikinOneData) -> None:
        """Verify async_turn_off calls set_thermostat_mode with HEAT and updates optimistically."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.AUX_HEAT,
        )
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        switch = DaikinOneEmergencyHeatSwitch(SwitchEntityDescription(key="emergency_heat"), mock_data, thermostat)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_off()
        mock_data.daikin.set_thermostat_mode.assert_called_once_with(thermostat.id, DaikinThermostatMode.HEAT)
        assert switch.is_on is False

    async def test_emergency_heat_switch_uid_schema_v0(self, mock_data: DaikinOneData) -> None:
        """Verify unique_id generation for schema version 0."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.HEAT,
        )
        entry_v0 = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 0})
        data_v0 = DaikinOneData(_hass=None, entry=entry_v0, daikin=mock_data.daikin)  # type: ignore[arg-type]
        switch = DaikinOneEmergencyHeatSwitch(SwitchEntityDescription(key="emergency_heat"), data_v0, thermostat)
        assert switch.unique_id == "device123-emergency_heat"

    async def test_emergency_heat_switch_uid_invalid_schema(self, mock_data: DaikinOneData) -> None:
        """Verify invalid uid schema version raises ValueError."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.HEAT,
        )
        entry_invalid = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 99})
        data_invalid = DaikinOneData(_hass=None, entry=entry_invalid, daikin=mock_data.daikin)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="unexpected entity uid schema version"):
            DaikinOneEmergencyHeatSwitch(SwitchEntityDescription(key="emergency_heat"), data_invalid, thermostat)


class TestNightModeSwitch:
    async def test_night_mode_switch_creation_when_supported(self, mock_data: DaikinOneData) -> None:
        """Verify night mode switch is created when thermostat has night_mode_enabled."""
        thermostat = _create_mock_thermostat(
            night_mode_enabled=False,
            night_mode_active=False,
            night_mode_light_bar_allowed=True,
        )
        mock_data.daikin.get_thermostats.return_value = {thermostat.id: thermostat}
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        added_entities = []

        def async_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)  # type: ignore[arg-type]

        night_mode_switches = [s for s in added_entities if isinstance(s, DaikinOneNightModeSwitch)]
        assert len(night_mode_switches) == 1
        switch = night_mode_switches[0]
        assert switch.is_on is False
        assert switch.entity_description.key == "night_mode"
        assert switch.entity_description.name == "Night mode"
        assert switch.entity_description.icon == "mdi:weather-night"
        assert switch.unique_id == "device123-night_mode"
        assert switch.device_name == "Living Room Thermostat"
        assert switch.extra_state_attributes == {
            "night_mode_active": False,
            "light_bar_allowed": True,
        }

    async def test_night_mode_switch_omitted_when_unsupported(self, mock_data: DaikinOneData) -> None:
        """Verify night mode switch is NOT created when night_mode_enabled is None."""
        thermostat = _create_mock_thermostat(night_mode_enabled=None)
        mock_data.daikin.get_thermostats.return_value = {thermostat.id: thermostat}
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        added_entities = []

        def async_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)  # type: ignore[arg-type]

        night_mode_switches = [s for s in added_entities if isinstance(s, DaikinOneNightModeSwitch)]
        assert len(night_mode_switches) == 0

    async def test_night_mode_switch_is_on_state(self, mock_data: DaikinOneData) -> None:
        """Verify is_on reflects whether thermostat night_mode_enabled is True."""
        thermostat_on = _create_mock_thermostat(night_mode_enabled=True)
        switch_on = DaikinOneNightModeSwitch(SwitchEntityDescription(key="night_mode"), mock_data, thermostat_on)
        assert switch_on.is_on is True

        thermostat_off = _create_mock_thermostat(night_mode_enabled=False)
        switch_off = DaikinOneNightModeSwitch(SwitchEntityDescription(key="night_mode"), mock_data, thermostat_off)
        assert switch_off.is_on is False

    async def test_night_mode_switch_turn_on(self, mock_data: DaikinOneData) -> None:
        """Verify async_turn_on calls set_thermostat_night_mode with True and updates optimistically."""
        thermostat = _create_mock_thermostat(night_mode_enabled=False)
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        switch = DaikinOneNightModeSwitch(SwitchEntityDescription(key="night_mode"), mock_data, thermostat)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_on()
        mock_data.daikin.set_thermostat_night_mode.assert_called_once_with(thermostat.id, True)
        assert switch.is_on is True

    async def test_night_mode_switch_turn_off(self, mock_data: DaikinOneData) -> None:
        """Verify async_turn_off calls set_thermostat_night_mode with False and updates optimistically."""
        thermostat = _create_mock_thermostat(night_mode_enabled=True)
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        switch = DaikinOneNightModeSwitch(SwitchEntityDescription(key="night_mode"), mock_data, thermostat)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_off()
        mock_data.daikin.set_thermostat_night_mode.assert_called_once_with(thermostat.id, False)
        assert switch.is_on is False

    async def test_night_mode_switch_extra_state_attributes(self, mock_data: DaikinOneData) -> None:
        """Verify extra_state_attributes handles present and absent values."""
        # Both present
        thermostat = _create_mock_thermostat(
            night_mode_enabled=True,
            night_mode_active=True,
            night_mode_light_bar_allowed=False,
        )
        switch = DaikinOneNightModeSwitch(SwitchEntityDescription(key="night_mode"), mock_data, thermostat)
        assert switch.extra_state_attributes == {
            "night_mode_active": True,
            "light_bar_allowed": False,
        }

        # Both None
        thermostat_none = _create_mock_thermostat(
            night_mode_enabled=True,
            night_mode_active=None,
            night_mode_light_bar_allowed=None,
        )
        switch_none = DaikinOneNightModeSwitch(SwitchEntityDescription(key="night_mode"), mock_data, thermostat_none)
        assert switch_none.extra_state_attributes == {}

    async def test_night_mode_switch_uid_schema_v0(self, mock_data: DaikinOneData) -> None:
        """Verify unique_id generation for schema version 0."""
        thermostat = _create_mock_thermostat(night_mode_enabled=True)
        entry_v0 = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 0})
        data_v0 = DaikinOneData(_hass=None, entry=entry_v0, daikin=mock_data.daikin)  # type: ignore[arg-type]
        switch = DaikinOneNightModeSwitch(SwitchEntityDescription(key="night_mode"), data_v0, thermostat)
        assert switch.unique_id == "device123-night_mode"

    async def test_night_mode_switch_uid_invalid_schema(self, mock_data: DaikinOneData) -> None:
        """Verify invalid uid schema version raises ValueError."""
        thermostat = _create_mock_thermostat(night_mode_enabled=True)
        entry_invalid = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 99})
        data_invalid = DaikinOneData(_hass=None, entry=entry_invalid, daikin=mock_data.daikin)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="unexpected entity uid schema version"):
            DaikinOneNightModeSwitch(SwitchEntityDescription(key="night_mode"), data_invalid, thermostat)
