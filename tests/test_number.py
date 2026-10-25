"""Tests for Daikin One native temperature and humidity calibration offset numbers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.number import NumberDeviceClass, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature

from custom_components.daikinone import DOMAIN, DaikinOneData
from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.mapping import map_thermostat
from custom_components.daikinone.client.models import DaikinThermostat
from custom_components.daikinone.client.wire import DaikinDeviceDataResponse
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.number import (
    DaikinHumidityOffsetNumber,
    DaikinTemperatureOffsetNumber,
    async_setup_entry,
)
from tests.test_mapping import _make_device


def _make_thermostat(
    temp_offset: float | None = 0.0,
    hum_offset: int | None = 0,
    units: int = 0,
) -> DaikinThermostat:
    payload = _make_device()
    payload["data"]["tempOffset"] = temp_offset
    payload["data"]["humOffset"] = hum_offset
    payload["data"]["units"] = units
    return map_thermostat(DaikinDeviceDataResponse(**payload))


def _data_for(thermostat: DaikinThermostat, schema: int = 1) -> DaikinOneData:
    entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: schema})
    daikin = MagicMock(spec=DaikinOne)
    daikin.get_thermostats.return_value = {thermostat.id: thermostat}
    daikin.get_thermostat.return_value = thermostat
    daikin.set_temperature_offset = AsyncMock()
    daikin.set_humidity_offset = AsyncMock()
    data = DaikinOneData(_hass=None, entry=entry, daikin=daikin)  # type: ignore[arg-type]
    data.update = AsyncMock()  # type: ignore[method-assign]
    return data


async def test_setup_creates_entities_only_when_registers_populated() -> None:
    thermostat = _make_thermostat(temp_offset=1.5, hum_offset=-2)
    data = _data_for(thermostat)
    entities: list[object] = []
    hass = SimpleNamespace(data={DOMAIN: data})

    await async_setup_entry(
        hass,
        data.entry,
        lambda added, update_before_add=False: entities.extend(added),  # type: ignore[arg-type]
    )

    assert len(entities) == 2
    temp_entity = next(e for e in entities if isinstance(e, DaikinTemperatureOffsetNumber))
    hum_entity = next(e for e in entities if isinstance(e, DaikinHumidityOffsetNumber))
    assert temp_entity.entity_description.key == "temperature_offset"
    assert hum_entity.entity_description.key == "humidity_offset"

    # Both None -> No entities created
    absent = _make_thermostat(temp_offset=None, hum_offset=None)
    absent_data = _data_for(absent)
    absent_entities: list[object] = []
    await async_setup_entry(
        SimpleNamespace(data={DOMAIN: absent_data}),
        absent_data.entry,
        lambda added, update_before_add=False: absent_entities.extend(added),  # type: ignore[arg-type]
    )
    assert absent_entities == []

    # Only temperature offset populated
    only_temp = _make_thermostat(temp_offset=0.0, hum_offset=None)
    only_temp_data = _data_for(only_temp)
    only_temp_entities: list[object] = []
    await async_setup_entry(
        SimpleNamespace(data={DOMAIN: only_temp_data}),
        only_temp_data.entry,
        lambda added, update_before_add=False: only_temp_entities.extend(added),  # type: ignore[arg-type]
    )
    assert len(only_temp_entities) == 1
    assert isinstance(only_temp_entities[0], DaikinTemperatureOffsetNumber)

    # Only humidity offset populated
    only_hum = _make_thermostat(temp_offset=None, hum_offset=0)
    only_hum_data = _data_for(only_hum)
    only_hum_entities: list[object] = []
    await async_setup_entry(
        SimpleNamespace(data={DOMAIN: only_hum_data}),
        only_hum_data.entry,
        lambda added, update_before_add=False: only_hum_entities.extend(added),  # type: ignore[arg-type]
    )
    assert len(only_hum_entities) == 1
    assert isinstance(only_hum_entities[0], DaikinHumidityOffsetNumber)


def test_temperature_offset_entity_attributes_fahrenheit() -> None:
    thermostat = _make_thermostat(temp_offset=-2.0, units=0)
    data = _data_for(thermostat, schema=1)
    entity = DaikinTemperatureOffsetNumber(data, thermostat)

    assert entity.unique_id == "device123-temperature_offset"
    assert entity.entity_description.name == "Temperature offset"
    assert entity.device_name == "Test Thermostat Thermostat"
    assert entity.device_class == NumberDeviceClass.TEMPERATURE_DELTA
    assert entity.entity_category == EntityCategory.CONFIG
    assert entity.mode == NumberMode.BOX
    assert entity.native_value == -2.0
    assert entity.native_min_value == -10.0
    assert entity.native_max_value == 10.0
    assert entity.native_step == 1.0
    assert entity.native_unit_of_measurement == UnitOfTemperature.FAHRENHEIT

    # Schema v0 unique ID fallback
    legacy_entity = DaikinTemperatureOffsetNumber(_data_for(thermostat, schema=0), thermostat)
    assert legacy_entity.unique_id == "device123-Temperature Offset"


def test_temperature_offset_entity_attributes_celsius() -> None:
    thermostat = _make_thermostat(temp_offset=1.5, units=1)
    data = _data_for(thermostat, schema=1)
    entity = DaikinTemperatureOffsetNumber(data, thermostat)

    assert entity.unique_id == "device123-temperature_offset"
    assert entity.native_value == 1.5
    assert entity.native_min_value == -5.5
    assert entity.native_max_value == 5.5
    assert entity.native_step == 0.5
    assert entity.native_unit_of_measurement == UnitOfTemperature.CELSIUS


def test_humidity_offset_entity_attributes() -> None:
    thermostat = _make_thermostat(hum_offset=5)
    data = _data_for(thermostat, schema=1)
    entity = DaikinHumidityOffsetNumber(data, thermostat)

    assert entity.unique_id == "device123-humidity_offset"
    assert entity.entity_description.name == "Humidity offset"
    assert entity.device_name == "Test Thermostat Thermostat"
    assert entity.device_class == NumberDeviceClass.HUMIDITY
    assert entity.entity_category == EntityCategory.CONFIG
    assert entity.mode == NumberMode.SLIDER
    assert entity.native_value == 5.0
    assert entity.native_min_value == -15.0
    assert entity.native_max_value == 15.0
    assert entity.native_step == 1.0
    assert entity.native_unit_of_measurement == PERCENTAGE

    # Schema v0 unique ID fallback
    legacy_entity = DaikinHumidityOffsetNumber(_data_for(thermostat, schema=0), thermostat)
    assert legacy_entity.unique_id == "device123-Humidity Offset"


def test_unknown_unique_id_schema_raises() -> None:
    thermostat = _make_thermostat()
    data = _data_for(thermostat, schema=99)
    with pytest.raises(ValueError, match="unexpected entity uid schema version"):
        DaikinTemperatureOffsetNumber(data, thermostat)

    with pytest.raises(ValueError, match="unexpected entity uid schema version"):
        DaikinHumidityOffsetNumber(data, thermostat)


async def test_temperature_offset_async_set_native_value() -> None:
    thermostat = _make_thermostat(temp_offset=0.0)
    data = _data_for(thermostat)
    entity = DaikinTemperatureOffsetNumber(data, thermostat)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    await entity.async_set_native_value(-2.5)

    data.daikin.set_temperature_offset.assert_awaited_once_with("device123", -2.5)
    assert entity.native_value == -2.5


async def test_humidity_offset_async_set_native_value() -> None:
    thermostat = _make_thermostat(hum_offset=0)
    data = _data_for(thermostat)
    entity = DaikinHumidityOffsetNumber(data, thermostat)
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    await entity.async_set_native_value(3.0)

    data.daikin.set_humidity_offset.assert_awaited_once_with("device123", 3)
    assert entity.native_value == 3.0


async def test_async_get_device() -> None:
    thermostat = _make_thermostat()
    data = _data_for(thermostat)
    temp_entity = DaikinTemperatureOffsetNumber(data, thermostat)
    hum_entity = DaikinHumidityOffsetNumber(data, thermostat)

    assert await temp_entity.async_get_device() is thermostat
    assert await hum_entity.async_get_device() is thermostat
