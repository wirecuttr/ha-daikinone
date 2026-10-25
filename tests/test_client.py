"""Tests for DaikinOne client write paths, setpoints, away mode, and One Lite dispatching."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.climate import ClimateEntityDescription
from homeassistant.components.climate.const import ClimateEntityFeature

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
    DaikinUserCredentials,
)
from custom_components.daikinone.client.wire import DAIKIN_API_URL_DEVICE_DATA
from custom_components.daikinone.climate import DaikinOneThermostat
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.select import async_setup_entry as async_setup_select_entry
from custom_components.daikinone.utils import Temperature


@pytest.fixture
def daikin_client() -> DaikinOne:
    creds = DaikinUserCredentials(email="test@example.com", password="password")
    client = DaikinOne(creds)
    client._DaikinOne__thermostats.clear()  # type: ignore[attr-defined]
    return client


def _create_thermostat(
    thermostat_id: str,
    name: str = "Test Stat",
    model: str = "ONEPLUS",
    is_one_lite: bool = False,
    set_point_heat: Temperature | None = None,
    set_point_cool: Temperature | None = None,
) -> DaikinThermostat:
    return DaikinThermostat(
        id=thermostat_id,
        location_id="loc123",
        name=name,
        model=model,
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
        set_point_heat=set_point_heat or Temperature.from_celsius(20.0),
        set_point_heat_min=Temperature.from_celsius(10.0),
        set_point_heat_max=Temperature.from_celsius(30.0),
        set_point_cool=set_point_cool or Temperature.from_celsius(24.0),
        set_point_cool_min=Temperature.from_celsius(18.0),
        set_point_cool_max=Temperature.from_celsius(32.0),
        outdoor_temperature=Temperature.from_celsius(15.0),
        outdoor_humidity=50,
        air_quality_outdoor=None,
        air_quality_indoor=None,
        equipment={},
        is_one_lite=is_one_lite,
    )


class TestOneLiteClientWritePaths:
    async def test_set_temperature_dispatches_heatsp_and_coolsp_for_one_lite(self, daikin_client: DaikinOne) -> None:
        tstat = _create_thermostat("onelite_1", model="ONELITE_24V", is_one_lite=True)
        daikin_client._DaikinOne__thermostats["onelite_1"] = tstat  # type: ignore[attr-defined]

        heat = Temperature.from_celsius(21.5)
        cool = Temperature.from_celsius(25.0)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_temperature("onelite_1", heat=heat, cool=cool)

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/onelite_1",
                method="PUT",
                body={"heatSP": 21.5, "coolSP": 25.0},
            )

        cached = daikin_client.get_thermostat("onelite_1")
        assert cached.set_point_heat == heat
        assert cached.set_point_cool == cool

    async def test_set_temperature_dispatches_hspactive_and_cspactive_for_one_plus(
        self, daikin_client: DaikinOne
    ) -> None:
        tstat = _create_thermostat("oneplus_1", model="ONEPLUS", is_one_lite=False)
        daikin_client._DaikinOne__thermostats["oneplus_1"] = tstat  # type: ignore[attr-defined]

        heat = Temperature.from_celsius(22.0)
        cool = Temperature.from_celsius(26.0)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_temperature("oneplus_1", heat=heat, cool=cool)

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/oneplus_1",
                method="PUT",
                body={"hspActive": 22.0, "cspActive": 26.0},
            )

        cached = daikin_client.get_thermostat("oneplus_1")
        assert cached.set_point_heat == heat
        assert cached.set_point_cool == cool

    async def test_set_temperature_single_setpoint_one_lite(self, daikin_client: DaikinOne) -> None:
        tstat = _create_thermostat("onelite_1", model="ONELITE_24V", is_one_lite=True)
        daikin_client._DaikinOne__thermostats["onelite_1"] = tstat  # type: ignore[attr-defined]

        heat = Temperature.from_celsius(19.0)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_temperature("onelite_1", heat=heat)

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/onelite_1",
                method="PUT",
                body={"heatSP": 19.0},
            )

        cached = daikin_client.get_thermostat("onelite_1")
        assert cached.set_point_heat == heat

    async def test_set_temperature_raises_value_error_if_no_temperatures(self, daikin_client: DaikinOne) -> None:
        with pytest.raises(ValueError, match="At least one of heat or cool set points must be set"):
            await daikin_client.set_temperature("some_id", heat=None, cool=None)

    async def test_set_thermostat_home_set_points_dispatches_heatsp_for_one_lite(
        self, daikin_client: DaikinOne
    ) -> None:
        tstat = _create_thermostat("onelite_1", model="D2271", is_one_lite=True)
        daikin_client._DaikinOne__thermostats["onelite_1"] = tstat  # type: ignore[attr-defined]

        heat = Temperature.from_celsius(20.5)
        cool = Temperature.from_celsius(24.5)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_thermostat_home_set_points(
                "onelite_1", heat=heat, cool=cool, override_schedule=True
            )

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/onelite_1",
                method="PUT",
                body={"heatSP": 20.5, "coolSP": 24.5},
            )

        cached = daikin_client.get_thermostat("onelite_1")
        assert cached.set_point_heat == heat
        assert cached.set_point_cool == cool

    async def test_set_thermostat_home_set_points_dispatches_hsphome_for_one_plus(
        self, daikin_client: DaikinOne
    ) -> None:
        tstat = _create_thermostat("oneplus_1", model="ONEPLUS", is_one_lite=False)
        daikin_client._DaikinOne__thermostats["oneplus_1"] = tstat  # type: ignore[attr-defined]

        heat = Temperature.from_celsius(20.0)
        cool = Temperature.from_celsius(24.0)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_thermostat_home_set_points(
                "oneplus_1", heat=heat, cool=cool, override_schedule=True
            )

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/oneplus_1",
                method="PUT",
                body={"hspHome": 20.0, "cspHome": 24.0, "schedOverride": 1},
            )

        cached = daikin_client.get_thermostat("oneplus_1")
        assert cached.set_point_heat == heat
        assert cached.set_point_cool == cool

    async def test_set_thermostat_home_set_points_raises_value_error_if_no_temperatures(
        self, daikin_client: DaikinOne
    ) -> None:
        with pytest.raises(ValueError, match="At least one of heat or cool set points must be set"):
            await daikin_client.set_thermostat_home_set_points("some_id", heat=None, cool=None)

    async def test_set_away_dispatches_away_for_one_lite(self, daikin_client: DaikinOne) -> None:
        tstat = _create_thermostat("onelite_1", model="ONELITE_24V", is_one_lite=True)
        daikin_client._DaikinOne__thermostats["onelite_1"] = tstat  # type: ignore[attr-defined]

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_away("onelite_1", away=True)

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/onelite_1",
                method="PUT",
                body={"away": True},
            )

    async def test_set_away_dispatches_geofencing_away_for_one_plus(self, daikin_client: DaikinOne) -> None:
        tstat = _create_thermostat("oneplus_1", model="ONEPLUS", is_one_lite=False)
        daikin_client._DaikinOne__thermostats["oneplus_1"] = tstat  # type: ignore[attr-defined]

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_away("oneplus_1", away=False)

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/oneplus_1",
                method="PUT",
                body={"geofencingAway": False},
            )


class TestOneLitePlatformIntegrations:
    def test_climate_entity_omits_fan_mode_for_one_lite(self, daikin_client: DaikinOne) -> None:
        tstat = _create_thermostat("onelite_1", model="ONELITE_24V", is_one_lite=True)
        entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
        data = DaikinOneData(_hass=None, entry=entry, daikin=daikin_client)  # type: ignore[arg-type]

        entity = DaikinOneThermostat(
            description=ClimateEntityDescription(key="onelite_1", has_entity_name=True),
            data=data,
            thermostat=tstat,
        )

        assert not (entity.supported_features & ClimateEntityFeature.FAN_MODE)
        assert entity.fan_modes == []

    async def test_climate_entity_set_fan_mode_raises_for_one_lite(self, daikin_client: DaikinOne) -> None:
        tstat = _create_thermostat("onelite_1", model="ONELITE_24V", is_one_lite=True)
        entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
        data = DaikinOneData(_hass=None, entry=entry, daikin=daikin_client)  # type: ignore[arg-type]

        entity = DaikinOneThermostat(
            description=ClimateEntityDescription(key="onelite_1", has_entity_name=True),
            data=data,
            thermostat=tstat,
        )

        with pytest.raises(NotImplementedError, match="Fan mode control is not supported on Daikin One Lite"):
            await entity.async_set_fan_mode("always_on")

    async def test_select_platform_skips_one_lite(self, daikin_client: DaikinOne) -> None:
        tstat = _create_thermostat("onelite_1", model="ONELITE_24V", is_one_lite=True)
        daikin_client._DaikinOne__thermostats["onelite_1"] = tstat  # type: ignore[attr-defined]

        added_entities: list[Any] = []
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.data = {CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1}
        mock_hass.data = {DOMAIN: DaikinOneData(_hass=mock_hass, entry=mock_entry, daikin=daikin_client)}

        await async_setup_select_entry(
            mock_hass,
            mock_entry,
            lambda entities, update_before_add=False: added_entities.extend(entities),
        )
        assert len(added_entities) == 0
