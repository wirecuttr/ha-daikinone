"""Unit tests for Daikin One climate platform and target humidity controls."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.climate import ClimateEntityDescription
from homeassistant.components.climate.const import ClimateEntityFeature

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
    DaikinUserCredentials,
)
from custom_components.daikinone.climate import DaikinOneThermostat
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.utils import Temperature


def _make_mock_thermostat(
    thermostat_id: str = "device123",
    hum_setpoint: int | None = 45,
    dehum_setpoint: int | None = 55,
    humidification_available: bool = False,
    dehumidification_available: bool = False,
) -> DaikinThermostat:
    return DaikinThermostat(
        id=thermostat_id,
        location_id="loc456",
        name="Living Room",
        model="ONEPLUS",
        firmware_version="1.0.0",
        online=True,
        capabilities={DaikinThermostatCapability.HEAT, DaikinThermostatCapability.COOL},
        mode=DaikinThermostatMode.HEAT,
        status=DaikinThermostatStatus.IDLE,
        fan_mode=DaikinThermostatFanMode.OFF,
        fan_speed=DaikinThermostatFanSpeed.LOW,
        schedule=DaikinThermostatSchedule(enabled=True),
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
        equipment={},
        hum_setpoint=hum_setpoint,
        dehum_setpoint=dehum_setpoint,
        humidification_available=humidification_available,
        dehumidification_available=dehumidification_available,
    )


@pytest.fixture
def daikin_client() -> DaikinOne:
    creds = DaikinUserCredentials(email="test@example.com", password="password")
    client = DaikinOne(creds)
    client._DaikinOne__thermostats.clear()  # type: ignore[attr-defined]
    return client


@pytest.fixture
def data(daikin_client: DaikinOne) -> DaikinOneData:
    entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
    return DaikinOneData(_hass=None, entry=entry, daikin=daikin_client)  # type: ignore[arg-type]


class TestTargetHumidityFeatureFlag:
    def test_target_humidity_supported_when_humidification_available(self, data: DaikinOneData) -> None:
        thermostat = _make_mock_thermostat(humidification_available=True)
        entity = DaikinOneThermostat(
            ClimateEntityDescription(key=thermostat.id, has_entity_name=True, name=None),
            data,
            thermostat,
        )
        assert ClimateEntityFeature.TARGET_HUMIDITY in entity.supported_features
        assert entity.min_humidity == 25
        assert entity.max_humidity == 65
        assert entity.target_humidity == 45

    def test_target_humidity_supported_when_dehumidification_available(self, data: DaikinOneData) -> None:
        thermostat = _make_mock_thermostat(dehumidification_available=True)
        entity = DaikinOneThermostat(
            ClimateEntityDescription(key=thermostat.id, has_entity_name=True, name=None),
            data,
            thermostat,
        )
        assert ClimateEntityFeature.TARGET_HUMIDITY in entity.supported_features
        assert entity.min_humidity == 25
        assert entity.max_humidity == 65

    def test_target_humidity_not_supported_when_neither_available(self, data: DaikinOneData) -> None:
        thermostat = _make_mock_thermostat(
            humidification_available=False,
            dehumidification_available=False,
        )
        entity = DaikinOneThermostat(
            ClimateEntityDescription(key=thermostat.id, has_entity_name=True, name=None),
            data,
            thermostat,
        )
        assert ClimateEntityFeature.TARGET_HUMIDITY not in entity.supported_features

    def test_target_humidity_none_when_unconfigured(self, data: DaikinOneData) -> None:
        thermostat = _make_mock_thermostat(
            humidification_available=True,
            hum_setpoint=None,
        )
        entity = DaikinOneThermostat(
            ClimateEntityDescription(key=thermostat.id, has_entity_name=True, name=None),
            data,
            thermostat,
        )
        assert entity.target_humidity is None


class TestClimateAsyncSetHumidity:
    async def test_async_set_humidity(self, daikin_client: DaikinOne, data: DaikinOneData) -> None:
        thermostat = _make_mock_thermostat(humidification_available=True, hum_setpoint=40)
        daikin_client._DaikinOne__thermostats[thermostat.id] = thermostat  # type: ignore[attr-defined]

        entity = DaikinOneThermostat(
            ClimateEntityDescription(key=thermostat.id, has_entity_name=True, name=None),
            data,
            thermostat,
        )
        entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            with patch.object(data, "update", new_callable=AsyncMock):
                await entity.async_set_humidity(50)

            mock_req.assert_awaited_once_with(
                url="https://api.daikinskyport.com/deviceData/device123",
                method="PUT",
                body={"humSP": 50},
            )
        assert entity.target_humidity == 50
        assert entity._attr_target_humidity == 50


class TestClientHumidityControls:
    async def test_set_humidity(self, daikin_client: DaikinOne) -> None:
        thermostat = _make_mock_thermostat(hum_setpoint=40)
        daikin_client._DaikinOne__thermostats[thermostat.id] = thermostat  # type: ignore[attr-defined]

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            await daikin_client.set_humidity("device123", 45)

            mock_req.assert_awaited_once_with(
                url="https://api.daikinskyport.com/deviceData/device123",
                method="PUT",
                body={"humSP": 45},
            )
        assert daikin_client.get_thermostat("device123").hum_setpoint == 45

    async def test_set_dehumidify_setpoint(self, daikin_client: DaikinOne) -> None:
        thermostat = _make_mock_thermostat(dehum_setpoint=60)
        daikin_client._DaikinOne__thermostats[thermostat.id] = thermostat  # type: ignore[attr-defined]

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            await daikin_client.set_dehumidify_setpoint("device123", 55)

            mock_req.assert_awaited_once_with(
                url="https://api.daikinskyport.com/deviceData/device123",
                method="PUT",
                body={"dehumSP": 55},
            )
        assert daikin_client.get_thermostat("device123").dehum_setpoint == 55
