"""Tests for Daikin One number platform (dual fuel balance point)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.number import NumberDeviceClass, NumberMode
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant

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
from custom_components.daikinone.number import (
    DEBOUNCE_DELAY,
    DUAL_FUEL_BALANCE_POINT_DESCRIPTION,
    DaikinOneDualFuelBalancePointNumber,
    async_setup_entry,
)
from custom_components.daikinone.utils import Temperature


def _create_mock_thermostat(
    thermostat_id: str = "device123",
    name: str = "Mainfloor",
    aux_heat_lockout_temp: float | None = 4.5,
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
        fan_circulate_start=32,
        fan_circulate_stop=88,
        fan_circulate_duration=DaikinThermostatFanCirculateDuration.MIN_15,
        aux_heat_lockout_temp=aux_heat_lockout_temp,
    )


@pytest.fixture
def mock_data() -> DaikinOneData:
    entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
    client = MagicMock(spec=DaikinOne)
    client.set_thermostat_aux_heat_lockout_temp = AsyncMock()
    client.get_thermostats = MagicMock(return_value={})
    data = DaikinOneData(_hass=None, entry=entry, daikin=client)  # type: ignore[arg-type]
    data.update = AsyncMock()  # type: ignore[method-assign]
    return data


@pytest.fixture
async def mock_hass() -> MagicMock:
    loop = asyncio.get_running_loop()
    hass = MagicMock(spec=HomeAssistant)
    hass.loop = loop
    hass.async_create_task = MagicMock(side_effect=lambda coro: loop.create_task(coro))
    return hass


@pytest.fixture
def fast_debounce(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("custom_components.daikinone.number.DEBOUNCE_DELAY", 0.02)


class TestNumberPlatformSetup:
    async def test_setup_entry_creates_entity_when_supported(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=4.5)
        mock_data.daikin.get_thermostats.return_value = {thermostat.id: thermostat}
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        added_entities = []

        def async_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)  # type: ignore[arg-type]

        assert len(added_entities) == 1
        entity = added_entities[0]
        assert isinstance(entity, DaikinOneDualFuelBalancePointNumber)
        assert entity.entity_description.key == "dual_fuel_balance_point"
        assert entity.entity_description.name == "Dual fuel balance point"
        assert entity.entity_description.icon == "mdi:thermometer"
        assert entity.entity_description.device_class == NumberDeviceClass.TEMPERATURE
        assert entity.entity_description.native_unit_of_measurement == UnitOfTemperature.CELSIUS
        assert entity.entity_description.native_step == 0.5
        assert entity.entity_description.mode == NumberMode.BOX
        assert entity.mode == NumberMode.BOX
        assert entity.entity_description.entity_category == EntityCategory.CONFIG
        assert entity.entity_description.has_entity_name is True
        assert entity.unique_id == "device123-dual_fuel_balance_point"
        assert entity.native_value == 4.5

    async def test_setup_entry_skips_when_aux_heat_lockout_temp_none(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=None)
        mock_data.daikin.get_thermostats.return_value = {thermostat.id: thermostat}
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        added_entities = []

        def async_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)  # type: ignore[arg-type]

        assert len(added_entities) == 0


class TestNumberUniqueId:
    def test_unique_id_schema_v0(self, mock_data: DaikinOneData) -> None:
        mock_data.entry.data[CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY] = 0
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=4.5)
        entity = DaikinOneDualFuelBalancePointNumber(mock_data, thermostat, DUAL_FUEL_BALANCE_POINT_DESCRIPTION)
        assert entity.unique_id == "device123-Dual fuel balance point"

    def test_unique_id_schema_v1(self, mock_data: DaikinOneData) -> None:
        mock_data.entry.data[CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY] = 1
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=4.5)
        entity = DaikinOneDualFuelBalancePointNumber(mock_data, thermostat, DUAL_FUEL_BALANCE_POINT_DESCRIPTION)
        assert entity.unique_id == "device123-dual_fuel_balance_point"

    def test_unique_id_schema_invalid(self, mock_data: DaikinOneData) -> None:
        mock_data.entry.data[CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY] = 99
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=4.5)
        with pytest.raises(ValueError, match="unexpected entity uid schema version"):
            DaikinOneDualFuelBalancePointNumber(mock_data, thermostat, DUAL_FUEL_BALANCE_POINT_DESCRIPTION)


class TestAuxHeatLockoutTemperatureEntity:
    def test_native_value_returns_float(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=4.5)
        entity = DaikinOneDualFuelBalancePointNumber(mock_data, thermostat)
        assert entity.native_value == 4.5
        assert isinstance(entity.native_value, float)

    def test_debounce_delay_constant(self) -> None:
        assert DEBOUNCE_DELAY == 0.8

    async def test_async_set_native_value_debounced_single_setpoint(
        self, mock_data: DaikinOneData, mock_hass: MagicMock, fast_debounce: None
    ) -> None:
        """Setting value updates in-memory immediately and calls API once debounce timer fires."""
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=4.5)
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)
        entity = DaikinOneDualFuelBalancePointNumber(mock_data, thermostat)
        entity.hass = mock_hass
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_native_value(5.0)

        # In-memory device updated immediately with optimistic state
        assert thermostat.aux_heat_lockout_temp == 5.0
        assert entity.native_value == 5.0
        assert entity._target_value == 5.0
        assert entity._debounce_timer is not None
        assert entity.async_write_ha_state.call_count == 1
        # API not yet called before debounce settling delay
        mock_data.daikin.set_thermostat_aux_heat_lockout_temp.assert_not_called()

        # Advance event loop past debounce delay
        await asyncio.sleep(0.05)

        # Debounce timer cleared and API called with final target
        assert entity._debounce_timer is None
        mock_data.daikin.set_thermostat_aux_heat_lockout_temp.assert_called_once_with(thermostat.id, 5.0)
        assert thermostat.aux_heat_lockout_temp == 5.0
        assert entity.native_value == 5.0

    async def test_async_set_native_value_debounce_coalescing(
        self, mock_data: DaikinOneData, mock_hass: MagicMock, fast_debounce: None
    ) -> None:
        """Rapid clicks coalesce into a single trailing API write while rendering optimistically."""
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=4.5)
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)
        entity = DaikinOneDualFuelBalancePointNumber(mock_data, thermostat)
        entity.hass = mock_hass
        entity.async_write_ha_state = MagicMock()

        # Rapidly call async_set_native_value 3 times in quick succession (e.g. user tapping [+] 3 times)
        await entity.async_set_native_value(5.0)
        assert entity.native_value == 5.0
        assert thermostat.aux_heat_lockout_temp == 5.0
        assert entity._target_value == 5.0

        await entity.async_set_native_value(5.5)
        assert entity.native_value == 5.5
        assert thermostat.aux_heat_lockout_temp == 5.5
        assert entity._target_value == 5.5

        await entity.async_set_native_value(6.0)
        assert entity.native_value == 6.0
        assert thermostat.aux_heat_lockout_temp == 6.0
        assert entity._target_value == 6.0

        # Intermediate values were not transmitted to the API
        mock_data.daikin.set_thermostat_aux_heat_lockout_temp.assert_not_called()

        # Advance / await loop by debounce delay
        await asyncio.sleep(0.05)

        # Assert API was called ONLY ONCE with the final coalesced target (6.0)
        mock_data.daikin.set_thermostat_aux_heat_lockout_temp.assert_called_once_with(thermostat.id, 6.0)
        # Verify native_value rendered optimistically throughout
        assert entity.native_value == 6.0
        assert thermostat.aux_heat_lockout_temp == 6.0

    async def test_async_will_remove_from_hass_cancels_timer(
        self, mock_data: DaikinOneData, mock_hass: MagicMock, fast_debounce: None
    ) -> None:
        """Removing entity from hass cancels pending debounce timer and prevents API transmission."""
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=4.5)
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)
        entity = DaikinOneDualFuelBalancePointNumber(mock_data, thermostat)
        entity.hass = mock_hass
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_native_value(5.0)
        assert entity._debounce_timer is not None
        timer_handle = entity._debounce_timer

        await entity.async_will_remove_from_hass()

        assert entity._debounce_timer is None
        assert timer_handle.cancelled()

        # Advance loop past debounce delay
        await asyncio.sleep(0.05)
        mock_data.daikin.set_thermostat_aux_heat_lockout_temp.assert_not_called()

    async def test_async_will_remove_from_hass_no_timer(self, mock_data: DaikinOneData, mock_hass: MagicMock) -> None:
        """Removing entity when no timer is active executes cleanly."""
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=4.5)
        entity = DaikinOneDualFuelBalancePointNumber(mock_data, thermostat)
        entity.hass = mock_hass

        assert entity._debounce_timer is None
        await entity.async_will_remove_from_hass()
        assert entity._debounce_timer is None

    async def test_async_send_debounced_value_noop_when_target_none(
        self, mock_data: DaikinOneData, mock_hass: MagicMock
    ) -> None:
        """Debounced sender returns early if target value is None."""
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=4.5)
        entity = DaikinOneDualFuelBalancePointNumber(mock_data, thermostat)
        entity.hass = mock_hass

        entity._target_value = None
        await entity._async_send_debounced_value()

        mock_data.daikin.set_thermostat_aux_heat_lockout_temp.assert_not_called()

    def test_dynamic_bounds_within_standard_range(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=4.5)
        entity = DaikinOneDualFuelBalancePointNumber(mock_data, thermostat)
        assert entity.native_min_value == -23.0
        assert entity.native_max_value == 22.0

    def test_dynamic_bounds_expansion_below_min(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=-30.0)
        entity = DaikinOneDualFuelBalancePointNumber(mock_data, thermostat)
        assert entity.native_min_value == -30.0
        assert entity.native_max_value == 22.0

    def test_dynamic_bounds_expansion_above_max(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=25.5)
        entity = DaikinOneDualFuelBalancePointNumber(mock_data, thermostat)
        assert entity.native_min_value == -23.0
        assert entity.native_max_value == 25.5

    def test_dynamic_bounds_when_temp_is_none(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=None)
        entity = DaikinOneDualFuelBalancePointNumber(mock_data, thermostat)
        assert entity.native_min_value == -23.0
        assert entity.native_max_value == 22.0

    async def test_async_get_device(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(aux_heat_lockout_temp=4.5)
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)
        entity = DaikinOneDualFuelBalancePointNumber(mock_data, thermostat)

        device = await entity.async_get_device()
        assert device == thermostat
        mock_data.daikin.get_thermostat.assert_called_once_with(thermostat.id)

    def test_device_name(self, mock_data: DaikinOneData) -> None:
        thermostat = _create_mock_thermostat(name="Living Room")
        entity = DaikinOneDualFuelBalancePointNumber(mock_data, thermostat)
        assert entity.device_name == "Living Room Thermostat"
