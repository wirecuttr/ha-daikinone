from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import SensorDeviceClass, SensorEntityDescription

from custom_components.daikinone import DaikinOneData
from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.models import (
    DaikinActiveHeatSource,
    DaikinIndoorUnit,
    DaikinThermostatMode,
    DaikinThermostatStatus,
    DaikinUserCredentials,
)
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.select import (
    DUAL_FUEL_PRIORITY_OPTIONS,
    DaikinOneDualFuelPrioritySelect,
)
from custom_components.daikinone.sensor import (
    DaikinOneActiveHeatSourceSensor,
    DaikinOneEquipmentSensor,
    DaikinOneThermostatSensor,
)
from tests.test_mapping import AIR_HANDLER_DATA, FURNACE_DATA, OUTDOOR_UNIT_DATA, _make_device


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


def _power_description() -> SensorEntityDescription:
    return SensorEntityDescription(key="power", name="Power", has_entity_name=True)


def _humidity_description() -> SensorEntityDescription:
    return SensorEntityDescription(key="humidity", name="Humidity", has_entity_name=True)


async def _refresh(daikin_client: DaikinOne, mock_req: AsyncMock, payload: dict[str, Any]) -> None:
    mock_req.return_value = [payload]
    await daikin_client.update()


class TestEntityAvailability:
    async def test_equipment_sensor_unavailable_when_equipment_skipped(
        self, daikin_client: DaikinOne, data: DaikinOneData
    ) -> None:
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, _make_device(AIR_HANDLER_DATA))

            thermostat = daikin_client.get_thermostats()["device123"]
            unit = next(e for e in thermostat.equipment.values() if isinstance(e, DaikinIndoorUnit))
            sensor = DaikinOneEquipmentSensor(
                description=_power_description(), data=data, device=unit, attribute=lambda e: e.power_usage
            )

            bad_ah = {**AIR_HANDLER_DATA, "ctAHSerialNoCharacter1_15": "he\ufffdlo"}
            await _refresh(daikin_client, mock_req, _make_device(bad_ah))
            await sensor.async_update(no_throttle=True)

        assert sensor.available is False
        # last-known _device is retained so attributes can recover cleanly
        assert sensor._device.id == unit.id

    async def test_equipment_sensor_recovers_when_equipment_returns(
        self, daikin_client: DaikinOne, data: DaikinOneData
    ) -> None:
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, _make_device(AIR_HANDLER_DATA))

            thermostat = daikin_client.get_thermostats()["device123"]
            unit = next(e for e in thermostat.equipment.values() if isinstance(e, DaikinIndoorUnit))
            sensor = DaikinOneEquipmentSensor(
                description=_power_description(), data=data, device=unit, attribute=lambda e: e.power_usage
            )

            bad_ah = {**AIR_HANDLER_DATA, "ctAHSerialNoCharacter1_15": "he\ufffdlo"}
            await _refresh(daikin_client, mock_req, _make_device(bad_ah))
            await sensor.async_update(no_throttle=True)
            assert sensor.available is False

            recovered = {**AIR_HANDLER_DATA, "ctIndoorPower": 1230}
            await _refresh(daikin_client, mock_req, _make_device(recovered))
            await sensor.async_update(no_throttle=True)

        assert sensor.available is True
        assert sensor._device.power_usage == 123.0

    async def test_thermostat_sensor_unaffected_by_equipment_availability(
        self, daikin_client: DaikinOne, data: DaikinOneData
    ) -> None:
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, _make_device(AIR_HANDLER_DATA))

            thermostat = daikin_client.get_thermostats()["device123"]
            sensor = DaikinOneThermostatSensor(
                description=_humidity_description(),
                data=data,
                device=thermostat,
                attribute=lambda t: t.indoor_humidity,
            )

            await sensor.async_update(no_throttle=True)

        assert sensor.available is True
        assert sensor.native_value == 45


class TestDualFuelPrioritySelect:
    async def test_select_state_and_options(self, daikin_client: DaikinOne, data: DaikinOneData) -> None:
        device_data = _make_device()
        device_data["data"]["ctDualFuelFurnaceLockoutEnable"] = False

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, device_data)

            thermostat = daikin_client.get_thermostats()["device123"]
            select = DaikinOneDualFuelPrioritySelect(
                description=SelectEntityDescription(
                    key="dual_fuel_priority",
                    name="Dual Fuel Priority",
                    icon="mdi:leaf",
                    options=DUAL_FUEL_PRIORITY_OPTIONS,
                ),
                data=data,
                thermostat=thermostat,
            )
            select.update_entity_attributes()
            assert select.current_option == "Comfort"
            assert select.icon == "mdi:leaf"
            assert select.unique_id == "device123-dual_fuel_priority"

            device_data_on = _make_device()
            device_data_on["data"]["ctDualFuelFurnaceLockoutEnable"] = True
            mock_req.return_value = [device_data_on]

            with patch.object(select, "async_write_ha_state"):
                await select.async_select_option("Efficiency")

            assert select.current_option == "Efficiency"
            assert select.icon == "mdi:leaf"

            with pytest.raises(ValueError):
                await select.async_select_option("Invalid")


class TestActiveHeatSourceSensor:
    def _create_description(self) -> SensorEntityDescription:
        return SensorEntityDescription(
            key="active_heat_source",
            name="Active Heat Source",
            has_entity_name=True,
            device_class=SensorDeviceClass.ENUM,
            options=[s.value for s in DaikinActiveHeatSource],
            translation_key="active_heat_source",
        )

    async def test_active_heat_source_sensor_schema_v0(self, daikin_client: DaikinOne) -> None:
        entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 0})
        v0_data = DaikinOneData(_hass=None, entry=entry, daikin=daikin_client)  # type: ignore[arg-type]

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, _make_device(OUTDOOR_UNIT_DATA, FURNACE_DATA))

        thermostat = daikin_client.get_thermostats()["device123"]
        sensor = DaikinOneActiveHeatSourceSensor(
            description=self._create_description(),
            data=v0_data,
            device=thermostat,
        )
        assert sensor.unique_id == "device123-Active Heat Source"

    async def test_active_heat_source_sensor_schema_v1(self, daikin_client: DaikinOne, data: DaikinOneData) -> None:
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, _make_device(OUTDOOR_UNIT_DATA, FURNACE_DATA))

        thermostat = daikin_client.get_thermostats()["device123"]
        sensor = DaikinOneActiveHeatSourceSensor(
            description=self._create_description(),
            data=data,
            device=thermostat,
        )
        assert sensor.unique_id == "device123-active_heat_source"
        assert sensor.device_class == SensorDeviceClass.ENUM
        assert sensor.options is not None
        assert len(sensor.options) == 12
        assert "heat_pump_heating" in sensor.options
        assert "gas_heating" in sensor.options
        assert "electric_heating" in sensor.options
        assert "emergency_heating" in sensor.options
        assert "drying" in sensor.options
        assert "defrost" in sensor.options

    async def test_active_heat_source_sensor_state_and_fuel_type(
        self, daikin_client: DaikinOne, data: DaikinOneData
    ) -> None:
        device_data = _make_device(OUTDOOR_UNIT_DATA, FURNACE_DATA)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value
        device_data["data"]["ctIFCCurrentHeatActualStatus"] = 70

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, device_data)

        thermostat = daikin_client.get_thermostats()["device123"]
        sensor = DaikinOneActiveHeatSourceSensor(
            description=self._create_description(),
            data=data,
            device=thermostat,
        )
        assert sensor.native_value == "gas_heating"
        assert sensor.extra_state_attributes == {"fuel_type": "gas"}

        # Switch to cooling
        cool_data = _make_device(OUTDOOR_UNIT_DATA, FURNACE_DATA)
        cool_data["data"]["mode"] = DaikinThermostatMode.COOL.value
        cool_data["data"]["equipmentStatus"] = DaikinThermostatStatus.COOLING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, cool_data)
            await sensor.async_update(no_throttle=True)

        assert sensor.native_value == "cooling"
        assert sensor.extra_state_attributes == {"fuel_type": "electric"}

        # Switch to idle
        idle_data = _make_device(OUTDOOR_UNIT_DATA, FURNACE_DATA)
        idle_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        idle_data["data"]["equipmentStatus"] = DaikinThermostatStatus.IDLE.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, idle_data)
            await sensor.async_update(no_throttle=True)

        assert sensor.native_value == "idle"
        assert sensor.extra_state_attributes == {}
