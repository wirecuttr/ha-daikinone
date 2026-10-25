from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.models import (
    DaikinEEVCoil,
    DaikinIndoorUnit,
    DaikinOutdoorUnit,
    DaikinOutdoorUnitHeaterStatus,
    DaikinOutdoorUnitReversingValveStatus,
    DaikinThermostatCapability,
    DaikinThermostatFanMode,
    DaikinThermostatFanSpeed,
    DaikinThermostatMode,
    DaikinThermostatStatus,
    DaikinUserCredentials,
)


@pytest.fixture
def daikin_client() -> DaikinOne:
    creds = DaikinUserCredentials(email="test@example.com", password="password")
    client = DaikinOne(creds)
    client._DaikinOne__thermostats.clear()  # type: ignore[attr-defined]
    return client


# --- Fixtures: minimal but complete device-data payloads ---

COMMON_THERMOSTAT_DATA: dict[str, Any] = {
    "ctSystemCapHeat": True,
    "ctSystemCapCool": True,
    "ctSystemCapEmergencyHeat": False,
    "mode": 1,
    "equipmentStatus": 5,
    "fanCirculate": 0,
    "fanCirculateSpeed": 1,
    "schedEnabled": True,
    "tempIndoor": 20.0,
    "humIndoor": 45,
    "hspActive": 19.0,
    "EquipProtocolMinHeatSetpoint": 10.0,
    "EquipProtocolMaxHeatSetpoint": 30.0,
    "cspActive": 24.0,
    "EquipProtocolMinCoolSetpoint": 18.0,
    "EquipProtocolMaxCoolSetpoint": 32.0,
    "tempOutdoor": 15.0,
    "humOutdoor": 60,
    "aqOutdoorAvailable": False,
    "aqIndoorAvailable": False,
}

AIR_HANDLER_DATA: dict[str, Any] = {
    "ctAHUnitType": 1,
    "ctAHModelNoCharacter1_15": "AH-MODEL        ",
    "ctAHSerialNoCharacter1_15": "AH-SERIAL       ",
    "ctAHControlSoftwareVersion": "1.0.0           ",
    "ctAHMode": "heat            ",
    "ctAHCurrentIndoorAirflow": 400,
    "ctAHFanRequestedDemand": 50,
    "ctAHFanCurrentDemandStatus": 48,
    "ctAHHeatRequestedDemand": 100,
    "ctAHHeatCurrentDemandStatus": 98,
    "ctAHHumidificationRequestedDemand": 0,
    "ctIndoorPower": 100,
}

OUTDOOR_UNIT_DATA: dict[str, Any] = {
    "ctOutdoorUnitType": 1,
    "ctOutdoorModelNoCharacter1_15": "OD-MODEL        ",
    "ctOutdoorSerialNoCharacter1_15": "OD-SERIAL       ",
    "ctOutdoorControlSoftwareVersion": "2.0.0           ",
    "ctOutdoorInverterSoftwareVersion": "1.5.0           ",
    "ctOutdoorCompressorRunTime": 1000,
    "ctOutdoorMode": "cool            ",
    "ctTargetCompressorspeed": 50,
    "ctCurrentCompressorRPS": 48,
    "ctTargetODFanRPM": 80,
    "ctOutdoorFanRPM": 780,
    "ctOutdoorSuctionPressure": 120,
    "ctOutdoorEEVOpening": 50,
    "ctReversingValve": 1,
    "ctOutdoorHeatRequestedDemand": 80,
    "ctOutdoorCoolRequestedDemand": 100,
    "ctOutdoorFanRequestedDemandPercentage": 60,
    "ctOutdoorRequestedIndoorAirflow": 400,
    "ctOutdoorDeHumidificationRequestedDemand": 0,
    "ctOutdoorAirTemperature": 750,
    "ctOutdoorCoilTemperature": 600,
    "ctOutdoorDischargeTemperature": 900,
    "ctOutdoorLiquidTemperature": 500,
    "ctOutdoorDefrostSensorTemperature": 320,
    "ctInverterFinTemp": 40,
    "ctOutdoorPower": 500,
    "ctCompressorCurrent": 50,
    "ctInverterCurrent": 30,
    "ctODFanMotorCurrent": 10,
    "ctCrankCaseHeaterOnOff": 0,
    "ctDrainPanHeaterOnOff": 0,
    "ctPreHeatOnOff": 0,
    "ctOutdoorHeatMaxRPS": 100,
}

EEV_COIL_DATA: dict[str, Any] = {
    "ctCoilUnitType": 1,
    "ctCoilSerialNoCharacter1_15": "EEV-SERIAL      ",
    "ctCoilControlSoftwareVersion": "3.0.0           ",
    "ctEEVCoilPressureSensor": 150,
    "ctEEVCoilSuperHeatValue": 100,
    "ctEEVCoilSubCoolValue": 50,
    "ctEEVCoilSuctionTemperature": 400,
}

NO_EQUIPMENT: dict[str, Any] = {
    "ctAHUnitType": 255,
    "ctIFCUnitType": 255,
    "ctOutdoorUnitType": 255,
    "ctCoilUnitType": 255,
}


def _make_device(*equipment_blocks: dict[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {**COMMON_THERMOSTAT_DATA, **NO_EQUIPMENT}
    for block in equipment_blocks:
        data.update(block)
    return {
        "id": "device123",
        "locationId": "loc456",
        "name": "Test Thermostat",
        "model": "ONEPLUS",
        "firmware": "1.0.0",
        "online": True,
        "data": data,
    }


ONELITE_24V_DATA: dict[str, Any] = {
    "coolSP": 24.0,
    "heatSP": 20.0,
    "spaceTemp": 21.5,
    "spaceHum": 45,
    "mode": 1,
    "eqStatus": 3,
    "away": False,
    "progOn": True,
    "heat1": True,
    "cool1": True,
    "tempOutdoor": 15.0,
    "humOutdoor": 55,
}


def _make_one_lite_device(
    device_id: str = "onelite123",
    model: str = "ONELITE_24V",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload_data = dict(ONELITE_24V_DATA)
    if data:
        payload_data.update(data)
    return {
        "id": device_id,
        "locationId": "loc456",
        "name": "One Lite Thermostat",
        "model": model,
        "firmware": "1.0.0",
        "online": True,
        "data": payload_data,
    }


# --- End-to-end: granular sanitization through DaikinOne.update ---


class TestMappingPreservesValidFields:
    async def test_air_handler_garbage_demand_becomes_none(self, daikin_client: DaikinOne) -> None:
        ah = {**AIR_HANDLER_DATA, "ctAHFanRequestedDemand": 255, "ctAHHeatRequestedDemand": 255}
        device_data = _make_device(ah)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        unit = next(e for e in thermostat.equipment.values() if isinstance(e, DaikinIndoorUnit))
        assert unit.fan_demand_requested_percent is None
        assert unit.heat_demand_requested_percent is None
        assert unit.current_airflow == 400

    async def test_air_handler_garbage_power_becomes_none(self, daikin_client: DaikinOne) -> None:
        ah = {**AIR_HANDLER_DATA, "ctIndoorPower": 65535}
        device_data = _make_device(ah)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        unit = next(e for e in thermostat.equipment.values() if isinstance(e, DaikinIndoorUnit))
        assert unit.power_usage is None
        assert unit.fan_demand_requested_percent == 25

    async def test_outdoor_garbage_temperature_becomes_none(self, daikin_client: DaikinOne) -> None:
        od = {**OUTDOOR_UNIT_DATA, "ctOutdoorAirTemperature": 32767, "ctInverterFinTemp": 255}
        device_data = _make_device(od)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        unit = next(e for e in thermostat.equipment.values() if isinstance(e, DaikinOutdoorUnit))
        assert unit.air_temperature is None
        assert unit.inverter_fin_temperature is None
        assert unit.coil_temperature is not None

    async def test_outdoor_garbage_runtime_becomes_none(self, daikin_client: DaikinOne) -> None:
        od = {**OUTDOOR_UNIT_DATA, "ctOutdoorCompressorRunTime": 4294967295}
        device_data = _make_device(od)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        unit = next(e for e in thermostat.equipment.values() if isinstance(e, DaikinOutdoorUnit))
        assert unit.total_runtime is None

    async def test_eev_coil_garbage_pressure_becomes_none(self, daikin_client: DaikinOne) -> None:
        eev = {**EEV_COIL_DATA, "ctEEVCoilPressureSensor": 32767}
        device_data = _make_device(eev)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        unit = next(e for e in thermostat.equipment.values() if isinstance(e, DaikinEEVCoil))
        assert unit.pressure_psi is None
        assert unit.indoor_superheat_temperature is not None

    async def test_humidity_out_of_range_becomes_none(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"]["humIndoor"] = 255

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.indoor_humidity is None

    async def test_thermostat_still_mapped_when_equipment_fields_garbage(self, daikin_client: DaikinOne) -> None:
        ah = {**AIR_HANDLER_DATA, "ctAHFanRequestedDemand": 255, "ctIndoorPower": 65535}
        device_data = _make_device(ah)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostats = daikin_client.get_thermostats()
        assert "device123" in thermostats
        assert thermostats["device123"].indoor_humidity == 45


class TestEquipmentSkippedOnInvalidIdentity:
    """When a wire identity string (model, serial) sanitizes to None, the equipment is
    omitted from the thermostat's equipment dict rather than registered under a synthetic
    id. Skipping preserves HA entity unique_id stability: the original `{model}-{serial}`
    eid is never polluted with fallback values, so entities go temporarily unavailable
    during garbage refreshes rather than being orphaned and re-registered under a new id."""

    async def test_air_handler_skipped_when_serial_invalid(self, daikin_client: DaikinOne) -> None:
        ah = {**AIR_HANDLER_DATA, "ctAHSerialNoCharacter1_15": "he\ufffdlo"}
        device_data = _make_device(ah)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert not any(isinstance(e, DaikinIndoorUnit) for e in thermostat.equipment.values())

    async def test_outdoor_skipped_when_model_invalid(self, daikin_client: DaikinOne) -> None:
        od = {**OUTDOOR_UNIT_DATA, "ctOutdoorModelNoCharacter1_15": "bad\ufffddata"}
        device_data = _make_device(od)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert not any(isinstance(e, DaikinOutdoorUnit) for e in thermostat.equipment.values())

    async def test_eev_skipped_when_serial_invalid(self, daikin_client: DaikinOne) -> None:
        eev = {**EEV_COIL_DATA, "ctCoilSerialNoCharacter1_15": "cor\ufffdupt"}
        device_data = _make_device(eev)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert not any(isinstance(e, DaikinEEVCoil) for e in thermostat.equipment.values())

    async def test_other_equipment_unaffected_by_one_skip(self, daikin_client: DaikinOne) -> None:
        """Skipping one equipment kind does not affect unrelated equipment on the same thermostat."""
        ah = {**AIR_HANDLER_DATA, "ctAHSerialNoCharacter1_15": "he\ufffdlo"}
        device_data = _make_device(ah, OUTDOOR_UNIT_DATA)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert not any(isinstance(e, DaikinIndoorUnit) for e in thermostat.equipment.values())
        assert any(isinstance(e, DaikinOutdoorUnit) for e in thermostat.equipment.values())

    async def test_identity_preserved_when_fields_valid(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device(AIR_HANDLER_DATA)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        unit = next(e for e in thermostat.equipment.values() if isinstance(e, DaikinIndoorUnit))
        assert unit.id == "AH-MODEL-AH-SERIAL"


class TestEquipmentUnitTypeAbsent:
    """P1/P2 mini-split payloads omit the ``ct*UnitType`` keys entirely; the mapping
    must treat that as 'equipment not present' rather than KeyError-ing on setup."""

    async def test_no_equipment_mapped_when_unit_type_keys_missing(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        for key in ("ctAHUnitType", "ctIFCUnitType", "ctOutdoorUnitType", "ctCoilUnitType"):
            del device_data["data"][key]

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.equipment == {}

    async def test_partial_unit_type_keys_gate_only_their_own_equipment(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device(OUTDOOR_UNIT_DATA)
        del device_data["data"]["ctAHUnitType"]
        del device_data["data"]["ctIFCUnitType"]
        del device_data["data"]["ctCoilUnitType"]

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert any(isinstance(e, DaikinOutdoorUnit) for e in thermostat.equipment.values())
        assert not any(isinstance(e, DaikinIndoorUnit) for e in thermostat.equipment.values())
        assert not any(isinstance(e, DaikinEEVCoil) for e in thermostat.equipment.values())


class TestThermostatCapabilitiesAbsent:
    """Some thermostat payloads omit the ``ctSystemCap*`` flags entirely; mapping
    must treat missing keys as 'capability not advertised' rather than KeyError-ing
    on setup."""

    async def test_no_capabilities_when_cap_keys_missing(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        for key in ("ctSystemCapHeat", "ctSystemCapCool", "ctSystemCapEmergencyHeat"):
            del device_data["data"][key]

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.capabilities == set()


class TestOutdoorUnitName:
    async def test_heat_pump_when_max_rps_positive(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device({**OUTDOOR_UNIT_DATA, "ctOutdoorHeatMaxRPS": 100})

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        unit = next(
            e
            for e in daikin_client.get_thermostats()["device123"].equipment.values()
            if isinstance(e, DaikinOutdoorUnit)
        )
        assert unit.name == "Heat Pump"

    async def test_condensing_unit_when_max_rps_zero(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device({**OUTDOOR_UNIT_DATA, "ctOutdoorHeatMaxRPS": 0})

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        unit = next(
            e
            for e in daikin_client.get_thermostats()["device123"].equipment.values()
            if isinstance(e, DaikinOutdoorUnit)
        )
        assert unit.name == "Condensing Unit"

    async def test_condensing_unit_when_max_rps_sentinel(self, daikin_client: DaikinOne) -> None:
        # 65535 is the U16 sentinel returned during a thermostat reboot; previously this
        # was checked inline in mapping, now it flows through read()
        device_data = _make_device({**OUTDOOR_UNIT_DATA, "ctOutdoorHeatMaxRPS": 65535})

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        unit = next(
            e
            for e in daikin_client.get_thermostats()["device123"].equipment.values()
            if isinstance(e, DaikinOutdoorUnit)
        )
        assert unit.name == "Condensing Unit"


class TestEnumSanitization:
    """Enum-wrapped raw values would previously raise ValueError during reboot, crashing
    the refresh. _missing_ now coerces unknown values to UNKNOWN so the mapping completes."""

    async def test_thermostat_mode_sentinel_becomes_unknown(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"]["mode"] = 255

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        assert daikin_client.get_thermostats()["device123"].mode is DaikinThermostatMode.UNKNOWN

    async def test_thermostat_status_sentinel_becomes_unknown(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"]["equipmentStatus"] = 255

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        assert daikin_client.get_thermostats()["device123"].status is DaikinThermostatStatus.UNKNOWN

    async def test_thermostat_fan_mode_sentinel_becomes_unknown(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"]["fanCirculate"] = 255

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        assert daikin_client.get_thermostats()["device123"].fan_mode is DaikinThermostatFanMode.UNKNOWN

    async def test_thermostat_fan_speed_sentinel_becomes_unknown(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"]["fanCirculateSpeed"] = 255

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        assert daikin_client.get_thermostats()["device123"].fan_speed is DaikinThermostatFanSpeed.UNKNOWN

    async def test_thermostat_enum_unexpected_value_becomes_unknown(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"]["mode"] = 99

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        assert daikin_client.get_thermostats()["device123"].mode is DaikinThermostatMode.UNKNOWN

    async def test_outdoor_reversing_valve_unexpected_value_becomes_unknown(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device({**OUTDOOR_UNIT_DATA, "ctReversingValve": 42})

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        unit = next(
            e
            for e in daikin_client.get_thermostats()["device123"].equipment.values()
            if isinstance(e, DaikinOutdoorUnit)
        )
        assert unit.reversing_valve is DaikinOutdoorUnitReversingValveStatus.UNKNOWN

    async def test_outdoor_heater_unexpected_value_becomes_unknown(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device({**OUTDOOR_UNIT_DATA, "ctCrankCaseHeaterOnOff": 42})

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        unit = next(
            e
            for e in daikin_client.get_thermostats()["device123"].equipment.values()
            if isinstance(e, DaikinOutdoorUnit)
        )
        assert unit.crank_case_heater is DaikinOutdoorUnitHeaterStatus.UNKNOWN


class TestOneLiteMapping:
    """Tests for Daikin One Lite 24V (D2271 / ONELITE_24V) payload normalization and mapping."""

    async def test_one_lite_payload_normalization_and_mapping(self, daikin_client: DaikinOne) -> None:
        device_data = _make_one_lite_device()

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        tstat = daikin_client.get_thermostats()["onelite123"]
        assert tstat.is_one_lite is True
        assert tstat.model == "ONELITE_24V"
        assert tstat.indoor_temperature is not None
        assert tstat.indoor_temperature.celsius == 21.5
        assert tstat.indoor_humidity == 45
        assert tstat.set_point_cool is not None
        assert tstat.set_point_cool.celsius == 24.0
        assert tstat.set_point_heat is not None
        assert tstat.set_point_heat.celsius == 20.0
        assert tstat.mode is DaikinThermostatMode.HEAT
        assert tstat.status is DaikinThermostatStatus.HEATING
        assert tstat.schedule.enabled is True
        assert DaikinThermostatCapability.HEAT in tstat.capabilities
        assert DaikinThermostatCapability.COOL in tstat.capabilities
        assert DaikinThermostatCapability.EMERGENCY_HEAT not in tstat.capabilities
        assert tstat.equipment == {}
        assert tstat.air_quality_indoor is None
        assert tstat.air_quality_outdoor is None

    async def test_one_lite_detection_by_d2271_model(self, daikin_client: DaikinOne) -> None:
        device_data = _make_one_lite_device(model="D2271")

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        tstat = daikin_client.get_thermostats()["onelite123"]
        assert tstat.is_one_lite is True
        assert tstat.model == "D2271"

    async def test_one_lite_detection_by_coolsp_with_unknown_model(self, daikin_client: DaikinOne) -> None:
        device_data = _make_one_lite_device(model="UNKNOWN_STAT")

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        tstat = daikin_client.get_thermostats()["onelite123"]
        assert tstat.is_one_lite is True

    async def test_one_lite_terminal_relay_capability_fallback(self, daikin_client: DaikinOne) -> None:
        device_data = _make_one_lite_device(
            data={"heat1": False, "cool1": False, "w1ObTerminal": True, "y1Terminal": True}
        )

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        tstat = daikin_client.get_thermostats()["onelite123"]
        assert DaikinThermostatCapability.HEAT in tstat.capabilities
        assert DaikinThermostatCapability.COOL in tstat.capabilities

    async def test_one_lite_heat_only_capabilities(self, daikin_client: DaikinOne) -> None:
        device_data = _make_one_lite_device(
            data={"heat1": True, "cool1": False, "w1ObTerminal": False, "y1Terminal": False}
        )

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        tstat = daikin_client.get_thermostats()["onelite123"]
        assert DaikinThermostatCapability.HEAT in tstat.capabilities
        assert DaikinThermostatCapability.COOL not in tstat.capabilities

    async def test_one_lite_cool_only_capabilities(self, daikin_client: DaikinOne) -> None:
        device_data = _make_one_lite_device(
            data={"heat1": False, "cool1": True, "w1ObTerminal": False, "y1Terminal": False}
        )

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        tstat = daikin_client.get_thermostats()["onelite123"]
        assert DaikinThermostatCapability.HEAT not in tstat.capabilities
        assert DaikinThermostatCapability.COOL in tstat.capabilities

    async def test_one_lite_defensive_defaults_for_missing_keys(self, daikin_client: DaikinOne) -> None:
        minimal_data = {
            "coolSP": 22.0,
            "spaceTemp": 21.0,
            "spaceHum": 50,
            "mode": 2,
            "eqStatus": 1,
            "progOn": False,
            "away": True,
            "cool1": True,
        }
        device_data = {
            "id": "onelite_minimal",
            "locationId": "loc456",
            "name": "Minimal One Lite",
            "model": "D2271",
            "firmware": "1.0.0",
            "online": True,
            "data": minimal_data,
        }

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        tstat = daikin_client.get_thermostats()["onelite_minimal"]
        assert tstat.is_one_lite is True
        assert tstat.outdoor_temperature is None
        assert tstat.outdoor_humidity is None
        assert tstat.air_quality_outdoor is None
        assert tstat.air_quality_indoor is None
        assert tstat.set_point_heat is None
        assert tstat.set_point_cool is not None
        assert tstat.set_point_cool.celsius == 22.0
        assert tstat.schedule.enabled is False
        assert tstat.status is DaikinThermostatStatus.COOLING
