from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate import ClimateEntityDescription
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import SensorDeviceClass, SensorEntityDescription

from custom_components.daikinone import DaikinOneData
from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.models import (
    DaikinIndoorUnit,
    DaikinThermostat,
    DaikinUserCredentials,
)
from custom_components.daikinone.climate import DaikinOneThermostat
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY, DOMAIN
from custom_components.daikinone.entity import DaikinOneEntity, DaikinOneThermostatEntity
from custom_components.daikinone.select import (
    DUAL_FUEL_PRIORITY_OPTIONS,
    DaikinOneDualFuelPrioritySelect,
)
from custom_components.daikinone.sensor import (
    DaikinOneEquipmentSensor,
    DaikinOneThermostatSensor,
)
from tests.test_mapping import AIR_HANDLER_DATA, _make_device


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

    async def test_thermostat_entity_available_when_online_and_unavailable_when_offline(
        self, daikin_client: DaikinOne, data: DaikinOneData
    ) -> None:
        """Verify thermostat entity availability is True when online and False when offline."""
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, _make_device())
            thermostat = daikin_client.get_thermostat("device123")
            sensor = DaikinOneThermostatSensor(
                description=_humidity_description(),
                data=data,
                device=thermostat,
                attribute=lambda t: t.indoor_humidity,
            )
            assert sensor.available is True

            # Device goes offline via empty data payload
            offline_payload = {"id": "device123", "name": "Device 123", "online": False, "data": {}}
            await _refresh(daikin_client, mock_req, offline_payload)
            await sensor.async_update(no_throttle=True)

            assert sensor.available is False

            # Device recovers
            await _refresh(daikin_client, mock_req, _make_device())
            await sensor.async_update(no_throttle=True)

            assert sensor.available is True

    async def test_child_equipment_inherits_thermostat_availability(
        self, daikin_client: DaikinOne, data: DaikinOneData
    ) -> None:
        """Verify child equipment inherits online/offline availability from parent thermostat."""
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, _make_device(AIR_HANDLER_DATA))
            thermostat = daikin_client.get_thermostat("device123")
            unit = next(e for e in thermostat.equipment.values() if isinstance(e, DaikinIndoorUnit))
            sensor = DaikinOneEquipmentSensor(
                description=_power_description(),
                data=data,
                device=unit,
                attribute=lambda e: e.power_usage,
            )
            assert sensor.available is True

            # Parent thermostat goes offline
            offline_payload = {"id": "device123", "name": "Device 123", "online": False, "data": {}}
            await _refresh(daikin_client, mock_req, offline_payload)
            await sensor.async_update(no_throttle=True)

            assert sensor.available is False

            # Parent thermostat recovers
            await _refresh(daikin_client, mock_req, _make_device(AIR_HANDLER_DATA))
            await sensor.async_update(no_throttle=True)

            assert sensor.available is True

    async def test_online_status_sensor_remains_available_when_offline(
        self, daikin_client: DaikinOne, data: DaikinOneData
    ) -> None:
        """Verify online status diagnostic sensor remains available and reports 'Offline' when offline."""
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, _make_device())
            thermostat = daikin_client.get_thermostat("device123")
            online_desc = SensorEntityDescription(
                key="online",
                name="Online Status",
                has_entity_name=True,
                device_class=SensorDeviceClass.ENUM,
            )
            online_sensor = DaikinOneThermostatSensor(
                description=online_desc,
                data=data,
                device=thermostat,
                attribute=lambda d: "Online" if d.online else "Offline",
            )
            online_sensor.update_entity_attributes()
            assert online_sensor.available is True
            assert online_sensor.native_value == "Online"

            # Thermostat goes offline
            offline_payload = {"id": "device123", "name": "Device 123", "online": False, "data": {}}
            await _refresh(daikin_client, mock_req, offline_payload)
            await online_sensor.async_update(no_throttle=True)

            # Diagnostic sensor remains available so HA displays "Offline" rather than "Unavailable"
            assert online_sensor.available is True
            assert online_sensor.native_value == "Offline"

    async def test_climate_entity_available_when_online_and_unavailable_when_offline(
        self, daikin_client: DaikinOne, data: DaikinOneData
    ) -> None:
        """Verify climate entity availability is natively driven by thermostat online status."""
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, _make_device())
            thermostat = daikin_client.get_thermostat("device123")
            climate_entity = DaikinOneThermostat(
                description=ClimateEntityDescription(key="climate", has_entity_name=True),
                data=data,
                thermostat=thermostat,
            )
            assert climate_entity.available is True

            # Thermostat goes offline
            offline_payload = {"id": "device123", "name": "Device 123", "online": False, "data": {}}
            await _refresh(daikin_client, mock_req, offline_payload)
            await climate_entity.async_update(no_throttle=True)

            assert climate_entity.available is False

            # Thermostat recovers
            await _refresh(daikin_client, mock_req, _make_device())
            await climate_entity.async_update(no_throttle=True)

            assert climate_entity.available is True

    async def test_control_entity_available_when_online_and_unavailable_when_offline(
        self, daikin_client: DaikinOne, data: DaikinOneData
    ) -> None:
        """Verify control entities (select, switch, number) are unavailable when thermostat is offline."""
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, _make_device())
            thermostat = daikin_client.get_thermostat("device123")
            select = DaikinOneDualFuelPrioritySelect(
                description=SelectEntityDescription(
                    key="dual_fuel_priority",
                    name="Dual Fuel Priority",
                    options=DUAL_FUEL_PRIORITY_OPTIONS,
                ),
                data=data,
                thermostat=thermostat,
            )
            assert select.available is True

            # Thermostat goes offline
            offline_payload = {"id": "device123", "name": "Device 123", "online": False, "data": {}}
            await _refresh(daikin_client, mock_req, offline_payload)
            await select.async_update(no_throttle=True)

            assert select.available is False

            # Thermostat recovers
            await _refresh(daikin_client, mock_req, _make_device())
            await select.async_update(no_throttle=True)

            assert select.available is True


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


class _StubEntity(DaikinOneEntity[DaikinThermostat]):
    async def async_get_device(self) -> DaikinThermostat:
        return self._device

    def update_entity_attributes(self) -> None:
        pass


class TestUpdateStateOptimistically:
    async def test_updates_paused_reset_after_operation_error(
        self, daikin_client: DaikinOne, data: DaikinOneData
    ) -> None:
        """Regression test: a failed operation must not permanently freeze the entity."""
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, _make_device(AIR_HANDLER_DATA))
        thermostat = daikin_client.get_thermostats()["device123"]

        entity = _StubEntity(data=data, device=thermostat)

        async def failing_operation() -> None:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await entity.update_state_optimistically(
                operation=failing_operation,
                optimistic_update=lambda d: None,
                check=lambda d: True,
            )

        assert entity._updates_paused is False

    async def test_updates_resume_after_wait_for_updated_value_error(
        self, daikin_client: DaikinOne, data: DaikinOneData
    ) -> None:
        """Regression test: a failed post-operation poll must not permanently freeze the entity."""
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await _refresh(daikin_client, mock_req, _make_device(AIR_HANDLER_DATA))
        thermostat = daikin_client.get_thermostats()["device123"]

        entity = _StubEntity(data=data, device=thermostat)
        entity.hass = None  # type: ignore[assignment]
        entity.entity_id = "climate.test"
        entity.async_write_ha_state = lambda: None  # type: ignore[method-assign]

        def check(_: DaikinThermostat) -> bool:
            raise RuntimeError("device disappeared mid-poll")

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [_make_device(AIR_HANDLER_DATA)]

            with pytest.raises(RuntimeError):
                await entity.update_state_optimistically(
                    operation=AsyncMock(),
                    optimistic_update=lambda d: None,
                    check=check,
                )

        assert entity._updates_paused is False


class TestDeviceHierarchy:
    """Tests for native multi-property device hierarchy via via_device."""

    async def test_thermostat_via_device_links_to_location_hub(
        self, daikin_client: DaikinOne, data: DaikinOneData
    ) -> None:
        """Verify thermostat device info links via_device to its parent location hub."""
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            dev = _make_device()
            dev["locationId"] = "loc-456"
            await _refresh(daikin_client, mock_req, dev)

        thermostat = daikin_client.get_thermostat("device123")
        assert thermostat.location_id == "loc-456"

        entity = _StubEntity(data=data, device=thermostat)
        assert entity.device_parent == "loc-456"

        info = entity.get_device_info()
        assert info is not None
        assert info["identifiers"] == {(DOMAIN, "device123")}
        assert info["via_device"] == (DOMAIN, "loc-456")

    async def test_thermostat_without_location_omits_via_device(
        self, daikin_client: DaikinOne, data: DaikinOneData
    ) -> None:
        """Verify thermostat without locationId does not set via_device."""
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            dev = _make_device()
            dev["locationId"] = ""
            await _refresh(daikin_client, mock_req, dev)

        thermostat = daikin_client.get_thermostat("device123")
        assert thermostat.location_id == ""

        entity = _StubEntity(data=data, device=thermostat)
        assert entity.device_parent is None

        info = entity.get_device_info()
        assert info is not None
        assert "via_device" not in info

    async def test_daikin_one_thermostat_entity_subclass(self, daikin_client: DaikinOne, data: DaikinOneData) -> None:
        """Verify DaikinOneThermostatEntity explicitly provides device_parent and via_device."""
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            dev = _make_device()
            dev["locationId"] = "loc-789"
            await _refresh(daikin_client, mock_req, dev)

        thermostat = daikin_client.get_thermostat("device123")

        class _ThermostatStub(DaikinOneThermostatEntity):
            async def async_get_device(self) -> DaikinThermostat:
                return self._device

            def update_entity_attributes(self) -> None:
                pass

        entity = _ThermostatStub(data=data, device=thermostat)
        assert entity.device_parent == "loc-789"
        info = entity.get_device_info()
        assert info is not None
        assert info["via_device"] == (DOMAIN, "loc-789")

    async def test_equipment_via_device_links_to_parent_thermostat(
        self, daikin_client: DaikinOne, data: DaikinOneData
    ) -> None:
        """Verify subordinate equipment links via_device to its parent thermostat."""
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            dev = _make_device(AIR_HANDLER_DATA)
            dev["locationId"] = "loc-123"
            await _refresh(daikin_client, mock_req, dev)

        thermostat = daikin_client.get_thermostats()["device123"]
        unit = next(e for e in thermostat.equipment.values() if isinstance(e, DaikinIndoorUnit))

        sensor = DaikinOneEquipmentSensor(
            description=_power_description(), data=data, device=unit, attribute=lambda e: e.power_usage
        )
        assert sensor.device_parent == "device123"

        info = sensor.get_device_info()
        assert info is not None
        assert info["identifiers"] == {(DOMAIN, f"device123-{unit.id}")}
        assert info["via_device"] == (DOMAIN, "device123")
