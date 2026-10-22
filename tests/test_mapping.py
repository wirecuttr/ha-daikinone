from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.mapping import determine_operating_state, map_thermostat
from custom_components.daikinone.client.wire import DaikinDeviceDataResponse
from custom_components.daikinone.client.models import (
    DaikinEEVCoil,
    DaikinIndoorUnit,
    DaikinOneAirQualitySensorSummaryLevel,
    DaikinOperatingState,
    DaikinOutdoorUnit,
    DaikinOutdoorUnitHeaterStatus,
    DaikinOutdoorUnitReversingValveStatus,
    DaikinThermostatCapability,
    DaikinThermostatFanCirculateDuration,
    DaikinThermostatFanMode,
    DaikinThermostatFanSpeed,
    DaikinThermostatMode,
    DaikinThermostatStatus,
    DaikinUserCredentials,
    format_error_code,
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

FURNACE_DATA: dict[str, Any] = {
    "ctIFCUnitType": 1,
    "ctIFCModelNoCharacter1_15": "IFC-MODEL       ",
    "ctIFCSerialNoCharacter1_15": "IFC-SERIAL      ",
    "ctIFCControlSoftwareVersion": "1.0.0           ",
    "ctIFCOperatingHeatCoolMode": "heat            ",
    "ctIFCIndoorBlowerAirflow": 450,
    "ctIFCFanRequestedDemandPercent": 50,
    "ctIFCCurrentFanActualStatus": 48,
    "ctIFCHeatRequestedDemandPercent": 100,
    "ctIFCCurrentHeatActualStatus": 70,
    "ctIFCCoolRequestedDemandPercent": 0,
    "ctIFCCurrentCoolActualStatus": 0,
    "ctIFCHumRequestedDemandPercent": 0,
    "ctIFCDehumRequestedDemandPercent": 0,
    "ctIndoorPower": 150,
}

OUTDOOR_UNIT_DATA: dict[str, Any] = {
    "ctOutdoorUnitType": 1,
    "ctOutdoorModelNoCharacter1_15": "OD-MODEL        ",
    "ctOutdoorSerialNoCharacter1_15": "OD-SERIAL       ",
    "ctOutdoorControlSoftwareVersion": "2.0.0           ",
    "ctOutdoorInverterSoftwareVersion": "1.5.0           ",
    "ctOutdoorCompressorRunTime": 1000,
    "ctOutdoorMode": "cool            ",
    "ctOutdoorOperationMode": 9,
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

    async def test_dual_fuel_fields_mapped(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"]["ctDualFuelFurnaceLockoutEnable"] = True
        device_data["data"]["auxHeatLockoutTemp"] = 4.5

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.dual_fuel_furnace_lockout_enable is True
        assert thermostat.aux_heat_lockout_temp == 4.5

    async def test_dual_fuel_fields_absent_are_none(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.dual_fuel_furnace_lockout_enable is None
        assert thermostat.aux_heat_lockout_temp is None

    @pytest.mark.parametrize(
        ("raw_val", "expected"),
        [
            (4.5, 4.5),
            (5, 5.0),
            (-15.0, -15.0),
            ("3.5", 3.5),
            (None, None),
            ("invalid", None),
        ],
    )
    async def test_aux_heat_lockout_temp_mapping(
        self, daikin_client: DaikinOne, raw_val: Any, expected: float | None
    ) -> None:
        device_data = _make_device()
        device_data["data"]["auxHeatLockoutTemp"] = raw_val

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.aux_heat_lockout_temp == expected

    async def test_aux_heat_lockout_temp_absent_key(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"].pop("auxHeatLockoutTemp", None)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.aux_heat_lockout_temp is None


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

    @pytest.mark.parametrize(
        ("wire_value", "expected_enum"),
        [
            (0, DaikinOneAirQualitySensorSummaryLevel.GOOD),
            (1, DaikinOneAirQualitySensorSummaryLevel.MODERATE),
            (2, DaikinOneAirQualitySensorSummaryLevel.UNHEALTHY_SENSITIVE),
            (3, DaikinOneAirQualitySensorSummaryLevel.UNHEALTHY),
            (4, DaikinOneAirQualitySensorSummaryLevel.VERY_UNHEALTHY),
            (5, DaikinOneAirQualitySensorSummaryLevel.HAZARDOUS),
        ],
    )
    async def test_outdoor_air_quality_epa_levels_mapped(
        self,
        daikin_client: DaikinOne,
        wire_value: int,
        expected_enum: DaikinOneAirQualitySensorSummaryLevel,
    ) -> None:
        device_data = _make_device()
        device_data["data"].update(
            {
                "aqOutdoorAvailable": True,
                "aqOutdoorValue": 50,
                "aqOutdoorLevel": wire_value,
                "aqOutdoorParticles": 10,
                "aqOutdoorOzone": 20,
            }
        )

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.air_quality_outdoor is not None
        assert thermostat.air_quality_outdoor.aqi_summary_level is expected_enum

    @pytest.mark.parametrize(
        "wire_value",
        [255, -1, 6],
    )
    async def test_outdoor_air_quality_unexpected_values_fallback_to_unknown(
        self, daikin_client: DaikinOne, wire_value: int
    ) -> None:
        device_data = _make_device()
        device_data["data"].update(
            {
                "aqOutdoorAvailable": True,
                "aqOutdoorValue": 50,
                "aqOutdoorLevel": wire_value,
                "aqOutdoorParticles": 10,
                "aqOutdoorOzone": 20,
            }
        )

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.air_quality_outdoor is not None
        assert thermostat.air_quality_outdoor.aqi_summary_level is DaikinOneAirQualitySensorSummaryLevel.UNKNOWN

    @pytest.mark.parametrize(
        ("wire_value", "expected_enum"),
        [
            (0, DaikinOneAirQualitySensorSummaryLevel.GOOD),
            (1, DaikinOneAirQualitySensorSummaryLevel.MODERATE),
            (2, DaikinOneAirQualitySensorSummaryLevel.UNHEALTHY_SENSITIVE),
            (3, DaikinOneAirQualitySensorSummaryLevel.UNHEALTHY),
            (4, DaikinOneAirQualitySensorSummaryLevel.VERY_UNHEALTHY),
            (5, DaikinOneAirQualitySensorSummaryLevel.HAZARDOUS),
            (255, DaikinOneAirQualitySensorSummaryLevel.UNKNOWN),
            (-1, DaikinOneAirQualitySensorSummaryLevel.UNKNOWN),
            (6, DaikinOneAirQualitySensorSummaryLevel.UNKNOWN),
        ],
    )
    def test_air_quality_summary_level_enum_direct(
        self, wire_value: int, expected_enum: DaikinOneAirQualitySensorSummaryLevel
    ) -> None:
        assert DaikinOneAirQualitySensorSummaryLevel(wire_value) is expected_enum


class TestOneCleanFan:
    """oneCleanFanActive maps to the thermostat's One Clean state; payloads that
    don't report the feature (e.g. P1/P2 mini-splits) map to None so the switch
    entity is not created."""

    async def _thermostat(self, daikin_client: DaikinOne, device_data: dict[str, Any]):
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        return daikin_client.get_thermostats()["device123"]

    async def test_inactive_state_mapped(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"]["oneCleanFanActive"] = False

        thermostat = await self._thermostat(daikin_client, device_data)
        assert thermostat.one_clean_fan_active is False

    async def test_active_state_mapped(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"]["oneCleanFanActive"] = True

        thermostat = await self._thermostat(daikin_client, device_data)
        assert thermostat.one_clean_fan_active is True

    async def test_missing_key_maps_to_none(self, daikin_client: DaikinOne) -> None:
        thermostat = await self._thermostat(daikin_client, _make_device())
        assert thermostat.one_clean_fan_active is None


class TestOutdoorOperationModeMapping:
    async def test_operation_mode_mapped(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device({**OUTDOOR_UNIT_DATA, "ctOutdoorOperationMode": 9})

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        unit = next(
            e
            for e in daikin_client.get_thermostats()["device123"].equipment.values()
            if isinstance(e, DaikinOutdoorUnit)
        )
        assert unit.operation_mode == 9

    async def test_operation_mode_sentinel_becomes_none(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device({**OUTDOOR_UNIT_DATA, "ctOutdoorOperationMode": 255})

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        unit = next(
            e
            for e in daikin_client.get_thermostats()["device123"].equipment.values()
            if isinstance(e, DaikinOutdoorUnit)
        )
        assert unit.operation_mode is None


class TestDetermineOperatingState:
    async def test_off_mode(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device(OUTDOOR_UNIT_DATA, FURNACE_DATA)
        device_data["data"]["mode"] = DaikinThermostatMode.OFF.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.IDLE.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.OFF
        assert fuel is None

    async def test_idle_status(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device(OUTDOOR_UNIT_DATA, FURNACE_DATA)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.IDLE.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.IDLE
        assert fuel is None

    async def test_cooling_status(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device(OUTDOOR_UNIT_DATA, FURNACE_DATA)
        device_data["data"]["mode"] = DaikinThermostatMode.COOL.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.COOLING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.COOLING
        assert fuel == "electric"

    async def test_drying_status(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device(OUTDOOR_UNIT_DATA, FURNACE_DATA)
        device_data["data"]["mode"] = DaikinThermostatMode.COOL.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.DRYING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.DRYING
        assert fuel == "electric"

    async def test_circulating_air_status(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device(OUTDOOR_UNIT_DATA, FURNACE_DATA)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.CIRCULATING_AIR.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.FAN_ONLY
        assert fuel is None

    async def test_defrost_cycle_priority(self, daikin_client: DaikinOne) -> None:
        od = {
            **OUTDOOR_UNIT_DATA,
            "ctOutdoorMode": "defrost",
            "ctOutdoorHeatRequestedDemand": 100,
            "ctCurrentCompressorRPS": 48,
        }
        furnace = {
            **FURNACE_DATA,
            "ctIFCCurrentHeatActualStatus": 70,  # tempering heat active
            "ctIFCIndoorBlowerAirflow": 450,
        }
        device_data = _make_device(od, furnace)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.DEFROST
        assert fuel == "electric"

    async def test_emergency_heat_with_gas_furnace(self, daikin_client: DaikinOne) -> None:
        furnace = {
            **FURNACE_DATA,
            "ctIFCCurrentHeatActualStatus": 70,
            "ctIFCIndoorBlowerAirflow": 450,
        }
        device_data = _make_device(OUTDOOR_UNIT_DATA, furnace)
        device_data["data"]["mode"] = DaikinThermostatMode.AUX_HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.EMERGENCY_HEATING
        assert fuel == "gas"

    async def test_emergency_heat_with_air_handler(self, daikin_client: DaikinOne) -> None:
        ah = {
            **AIR_HANDLER_DATA,
            "ctAHHeatCurrentDemandStatus": 98,
            "ctAHCurrentIndoorAirflow": 400,
        }
        device_data = _make_device(OUTDOOR_UNIT_DATA, ah)
        device_data["data"]["mode"] = DaikinThermostatMode.AUX_HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.EMERGENCY_HEATING
        assert fuel == "electric"

    async def test_furnace_firing_overrides_hp_mode_12_deceleration(self, daikin_client: DaikinOne) -> None:
        """Physical overlap resolution: when furnace flame is proven, it immediately overrides
        the heat pump compressor ramp-down deceleration (Sequence B)."""
        od = {
            **OUTDOOR_UNIT_DATA,
            "ctOutdoorMode": "heat",
            "ctOutdoorOperationMode": 12,  # Mode 12 deceleration
            "ctCurrentCompressorRPS": 37,  # Still spinning down
            "ctOutdoorHeatRequestedDemand": 0,
        }
        furnace = {
            **FURNACE_DATA,
            "ctIFCCurrentHeatActualStatus": 70,  # 35% burner active
            "ctIFCIndoorBlowerAirflow": 200,
        }
        device_data = _make_device(od, furnace)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.GAS_HEATING
        assert fuel == "gas"

    async def test_furnace_firing_overrides_hp_decel_mode_string(self, daikin_client: DaikinOne) -> None:
        od = {
            **OUTDOOR_UNIT_DATA,
            "ctOutdoorMode": "decel",
            "ctCurrentCompressorRPS": 25,
            "ctOutdoorHeatRequestedDemand": 0,
        }
        furnace = {
            **FURNACE_DATA,
            "ctIFCCurrentHeatActualStatus": 70,
            "ctIFCIndoorBlowerAirflow": 200,
        }
        device_data = _make_device(od, furnace)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.GAS_HEATING
        assert fuel == "gas"

    async def test_heat_pump_steady_state_heating(self, daikin_client: DaikinOne) -> None:
        od = {
            **OUTDOOR_UNIT_DATA,
            "ctOutdoorMode": "heat",
            "ctOutdoorOperationMode": 9,
            "ctCurrentCompressorRPS": 48,
            "ctOutdoorHeatRequestedDemand": 80,
            "ctOutdoorHeatMaxRPS": 100,
        }
        furnace = {
            **FURNACE_DATA,
            "ctIFCCurrentHeatActualStatus": 0,
            "ctIFCIndoorBlowerAirflow": 476,
        }
        device_data = _make_device(od, furnace)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.HEAT_PUMP_HEATING
        assert fuel == "electric"

    async def test_all_electric_hp_supplemental_electric_heat(self, daikin_client: DaikinOne) -> None:
        """When HP compressor and auxiliary electric strips run simultaneously on an all-electric
        system, report heat_pump_heating to match physical wall unit (Decision 2)."""
        od = {
            **OUTDOOR_UNIT_DATA,
            "ctOutdoorMode": "heat",
            "ctOutdoorOperationMode": 9,
            "ctCurrentCompressorRPS": 48,
            "ctOutdoorHeatRequestedDemand": 100,
            "ctOutdoorHeatMaxRPS": 100,
        }
        ah = {
            **AIR_HANDLER_DATA,
            "ctAHHeatCurrentDemandStatus": 98,  # Electric heat strips actively firing
            "ctAHCurrentIndoorAirflow": 476,
        }
        device_data = _make_device(od, ah)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.HEAT_PUMP_HEATING
        assert fuel == "electric"

    async def test_all_electric_electric_heat_alone(self, daikin_client: DaikinOne) -> None:
        """When compressor is idle and auxiliary electric strips run alone, report electric_heating."""
        od = {
            **OUTDOOR_UNIT_DATA,
            "ctOutdoorMode": "heat",
            "ctCurrentCompressorRPS": 0,
            "ctOutdoorHeatRequestedDemand": 0,
        }
        ah = {
            **AIR_HANDLER_DATA,
            "ctAHHeatCurrentDemandStatus": 98,
            "ctAHCurrentIndoorAirflow": 400,
        }
        device_data = _make_device(od, ah)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.ELECTRIC_HEATING
        assert fuel == "electric"

    async def test_heating_startup_preheat_delay(self, daikin_client: DaikinOne) -> None:
        """During startup soft-start / coil pre-heat delay before blower runs (Sequence A),
        report heating_startup."""
        od = {
            **OUTDOOR_UNIT_DATA,
            "ctOutdoorMode": "heating startup",
            "ctCurrentCompressorRPS": 24,
            "ctOutdoorHeatRequestedDemand": 100,
        }
        furnace = {
            **FURNACE_DATA,
            "ctIFCCurrentHeatActualStatus": 0,
            "ctIFCIndoorBlowerAirflow": 0,  # Cold blow prevention delay
        }
        device_data = _make_device(od, furnace)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.HEATING_STARTUP
        assert fuel is None

    async def test_straight_ac_with_furnace(self, daikin_client: DaikinOne) -> None:
        od = {
            **OUTDOOR_UNIT_DATA,
            "ctOutdoorHeatMaxRPS": 0,  # Condensing unit only (no HP heating)
            "ctOutdoorHeatRequestedDemand": 0,
            "ctCurrentCompressorRPS": 0,
        }
        furnace = {
            **FURNACE_DATA,
            "ctIFCCurrentHeatActualStatus": 70,
            "ctIFCIndoorBlowerAirflow": 450,
        }
        device_data = _make_device(od, furnace)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.GAS_HEATING
        assert fuel == "gas"

    async def test_straight_ac_with_furnace_startup(self, daikin_client: DaikinOne) -> None:
        od = {
            **OUTDOOR_UNIT_DATA,
            "ctOutdoorHeatMaxRPS": 0,
            "ctOutdoorHeatRequestedDemand": 0,
            "ctCurrentCompressorRPS": 0,
        }
        furnace = {
            **FURNACE_DATA,
            "ctIFCCurrentHeatActualStatus": 0,  # Pre-purge delay
            "ctIFCIndoorBlowerAirflow": 0,
        }
        device_data = _make_device(od, furnace)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.HEATING_STARTUP
        assert fuel is None

    async def test_non_communicating_fallback(self, daikin_client: DaikinOne) -> None:
        """When sub-equipment loads are not available (conventional system), fall back to
        generic heating (Decision 3)."""
        device_data = _make_device()  # NO_EQUIPMENT
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        state, fuel = determine_operating_state(thermostat)
        assert state == DaikinOperatingState.HEATING
        assert fuel is None


class TestMapThermostatAwayMode:
    def test_map_thermostat_away_mode_active(self) -> None:
        """Verify that geofencingAway: true maps to away_mode=True."""
        device_data = _make_device()
        device_data["data"]["geofencingAway"] = True
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.away_mode is True

    def test_map_thermostat_away_mode_inactive(self) -> None:
        """Verify that geofencingAway: false maps to away_mode=False."""
        device_data = _make_device()
        device_data["data"]["geofencingAway"] = False
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.away_mode is False

    def test_map_thermostat_away_mode_absent(self) -> None:
        """Verify that missing geofencingAway preserves away_mode=None (nullable guard)."""
        device_data = _make_device()
        device_data["data"].pop("geofencingAway", None)
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.away_mode is None


class TestThermostatEmergencyHeatCapability:
    """Test emergency heat capability detection with modeEmHeatAvailable guard (Issue #25)."""

    def test_emergency_heat_capability_when_em_heat_available_true(self) -> None:
        device_data = _make_device()
        device_data["data"]["ctSystemCapEmergencyHeat"] = True
        device_data["data"]["modeEmHeatAvailable"] = True
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert DaikinThermostatCapability.EMERGENCY_HEAT in thermostat.capabilities

    def test_emergency_heat_capability_omitted_when_em_heat_available_false(self) -> None:
        device_data = _make_device()
        device_data["data"]["ctSystemCapEmergencyHeat"] = True
        device_data["data"]["modeEmHeatAvailable"] = False
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert DaikinThermostatCapability.EMERGENCY_HEAT not in thermostat.capabilities

    def test_emergency_heat_capability_backward_compatibility_when_field_absent(self) -> None:
        device_data = _make_device()
        device_data["data"]["ctSystemCapEmergencyHeat"] = True
        device_data["data"].pop("modeEmHeatAvailable", None)
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert DaikinThermostatCapability.EMERGENCY_HEAT in thermostat.capabilities

    def test_emergency_heat_capability_when_system_cap_false(self) -> None:
        device_data = _make_device()
        device_data["data"]["ctSystemCapEmergencyHeat"] = False
        device_data["data"]["modeEmHeatAvailable"] = True
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert DaikinThermostatCapability.EMERGENCY_HEAT not in thermostat.capabilities


class TestMapThermostatFanCirculation:
    """Test mapping of fan circulation scheduling and duration fields."""

    def test_fan_circulate_scheduling_valid_mapping(self) -> None:
        """Verify valid integers for fanCirculateStart, fanCirculateStop, and fanCirculateDuration."""
        device_data = _make_device()
        device_data["data"]["fanCirculateStart"] = 32
        device_data["data"]["fanCirculateStop"] = 88
        device_data["data"]["fanCirculateDuration"] = 2
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.fan_circulate_start == 32
        assert thermostat.fan_circulate_stop == 88
        assert thermostat.fan_circulate_duration == DaikinThermostatFanCirculateDuration.MIN_15

    @pytest.mark.parametrize(
        ("raw_value", "expected_enum"),
        [
            (0, DaikinThermostatFanCirculateDuration.CONTINUOUS),
            (1, DaikinThermostatFanCirculateDuration.MIN_5),
            (2, DaikinThermostatFanCirculateDuration.MIN_15),
            (3, DaikinThermostatFanCirculateDuration.MIN_30),
            (4, DaikinThermostatFanCirculateDuration.MIN_45),
        ],
    )
    def test_fan_circulate_duration_enum_values(
        self, raw_value: int, expected_enum: DaikinThermostatFanCirculateDuration
    ) -> None:
        """Verify each documented duty cycle raw integer maps to the expected enum member."""
        device_data = _make_device()
        device_data["data"]["fanCirculateDuration"] = raw_value
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.fan_circulate_duration == expected_enum

    @pytest.mark.parametrize("unknown_value", [255, 99, -1])
    def test_fan_circulate_duration_unknown_fallback(self, unknown_value: int) -> None:
        """Verify undocumented or sentinel duration values fall back to UNKNOWN via _missing_."""
        device_data = _make_device()
        device_data["data"]["fanCirculateDuration"] = unknown_value
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.fan_circulate_duration == DaikinThermostatFanCirculateDuration.UNKNOWN

    def test_fan_circulate_fields_absent(self) -> None:
        """Verify missing fan circulation keys map to None."""
        device_data = _make_device()
        device_data["data"].pop("fanCirculateStart", None)
        device_data["data"].pop("fanCirculateStop", None)
        device_data["data"].pop("fanCirculateDuration", None)
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.fan_circulate_start is None
        assert thermostat.fan_circulate_stop is None
        assert thermostat.fan_circulate_duration is None

    def test_fan_circulate_duration_none_in_payload(self) -> None:
        """Verify fanCirculateDuration with explicit None maps to None."""
        device_data = _make_device()
        device_data["data"]["fanCirculateDuration"] = None
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.fan_circulate_duration is None


class TestMapThermostatNightMode:
    """Test mapping of thermostat night mode fields."""

    def test_night_mode_valid_mapping(self) -> None:
        """Verify valid values for nightModeEnabled, nightModeActive, nightModeStart, nightModeStop, and nightModeLightBarAllowed."""
        device_data = _make_device()
        device_data["data"]["nightModeEnabled"] = True
        device_data["data"]["nightModeActive"] = False
        device_data["data"]["nightModeStart"] = 88
        device_data["data"]["nightModeStop"] = 28
        device_data["data"]["nightModeLightBarAllowed"] = True
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.night_mode_enabled is True
        assert thermostat.night_mode_active is False
        assert thermostat.night_mode_start == 88
        assert thermostat.night_mode_stop == 28
        assert thermostat.night_mode_light_bar_allowed is True

    def test_night_mode_fields_absent(self) -> None:
        """Verify missing night mode keys map to None."""
        device_data = _make_device()
        device_data["data"].pop("nightModeEnabled", None)
        device_data["data"].pop("nightModeActive", None)
        device_data["data"].pop("nightModeStart", None)
        device_data["data"].pop("nightModeStop", None)
        device_data["data"].pop("nightModeLightBarAllowed", None)
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.night_mode_enabled is None
        assert thermostat.night_mode_active is None
        assert thermostat.night_mode_start is None
        assert thermostat.night_mode_stop is None
        assert thermostat.night_mode_light_bar_allowed is None


class TestMapThermostatConsumablesAndMaintenance:
    """Test mapping of consumable inventory counters and maintenance telemetry."""

    def test_consumable_mapping_full_payload(self) -> None:
        """Verify complete mapping of all 8 consumable blocks with limits and active flags."""
        device_data = _make_device()
        device_data["data"].update(
            {
                # Hardware inventory
                "NumMediafilters": 1,
                "NumElectronicfilters": 1,
                "NumHEPAfilters": 1,
                "NumUVBulbs": 2,
                "ctHumidifierNumPads": 1,
                "AuxHumidifierStatus": True,
                "AuxDehumidifierStatus": True,
                "AuxVentilatorStatus": True,
                "ctSystemCapVentilation": True,
                # Media Filter
                "alertMediaAirFilterDays": 105,
                "alertMediaAirFilterDaysLimit": 186,
                "alertMediaAirFilterRuntime": 500,
                "alertMediaAirFilterRuntimeLimit": 1000,
                "alertMediaAirFilterActive": False,
                "alertMediaAirFilterDate": "2026-04-15",
                # Service
                "alertServiceDays": 96,
                "alertServiceDaysLimit": 372,
                "alertServiceActive": False,
                "alertServiceDate": "2026-10-01",
                # Humidifier Pad
                "alertHumPadDays": 45,
                "alertHumPadDaysLimit": 180,
                "alertHumPadRuntime": 200,
                "alertHumPadRuntimeLimit": 800,
                "alertHumPadActive": False,
                "alertHumPadDate": "2026-05-01",
                # UV Lamp
                "alertUVDays": 300,
                "alertUVDaysLimit": 365,
                "alertUVRuntime": 7000,
                "alertUVRuntimeLimit": 8760,
                "alertUVActive": False,
                "alertUVDate": "2026-11-20",
                # HEPA Filter
                "alertHEPAAirFilterDays": 50,
                "alertHEPAAirFilterDaysLimit": 365,
                "alertHEPAAirFilterRuntime": 300,
                "alertHEPAAirFilterRuntimeLimit": 2000,
                "alertHEPAAirFilterActive": False,
                "alertHEPAAirFilterDate": "2026-12-01",
                # Electronic Filter
                "alertElectronicAirFilterDays": 10,
                "alertElectronicAirFilterDaysLimit": 90,
                "alertElectronicAirFilterRuntime": 100,
                "alertElectronicAirFilterRuntimeLimit": 500,
                "alertElectronicAirFilterActive": False,
                "alertElectronicAirFilterDate": "2026-02-01",
                # Dehumidifier Filter
                "alertDehumFilterDays": 20,
                "alertDehumFilterDaysLimit": 180,
                "alertDehumFilterRuntime": 150,
                "alertDehumFilterRuntimeLimit": 600,
                "alertDehumFilterActive": False,
                "alertDehumFilterDate": "2026-06-01",
                # Ventilator Core
                "alertVentilationDays": 60,
                "alertVentilationDaysLimit": 180,
                "alertVentilationActive": False,
                "alertVentilationDate": "2026-07-01",
            }
        )
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))

        # Assert hardware inventory
        assert thermostat.num_media_filters == 1
        assert thermostat.num_electronic_filters == 1
        assert thermostat.num_hepa_filters == 1
        assert thermostat.num_uv_bulbs == 2
        assert thermostat.ct_humidifier_num_pads == 1
        assert thermostat.aux_humidifier_status is True
        assert thermostat.aux_dehumidifier_status is True
        assert thermostat.aux_ventilator_status is True
        assert thermostat.ct_system_cap_ventilation is True

        # Assert Media filter
        assert thermostat.media_air_filter_days == 105
        assert thermostat.media_air_filter_days_limit == 186
        assert thermostat.media_air_filter_runtime == 500
        assert thermostat.media_air_filter_runtime_limit == 1000
        assert thermostat.media_air_filter_active is False
        assert thermostat.media_air_filter_date == "2026-04-15"

        # Assert Service
        assert thermostat.service_days == 96
        assert thermostat.service_days_limit == 372
        assert thermostat.service_active is False

    def test_consumable_mapping_absent_fields_default_to_none(self) -> None:
        """Verify missing consumable and inventory keys map to None."""
        device_data = _make_device()
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.num_media_filters is None
        assert thermostat.media_air_filter_days is None
        assert thermostat.media_air_filter_days_limit is None
        assert thermostat.media_air_filter_active is None
        assert thermostat.service_days is None
        assert thermostat.service_days_limit is None
        assert thermostat.service_active is None

    def test_consumable_mapping_live_mainfloor_data(self) -> None:
        """Verify mapping matches live MainFloor telemetry (media filter only, service limit 0)."""
        device_data = _make_device()
        device_data["data"].update(
            {
                "NumMediafilters": 1,
                "NumElectronicfilters": 0,
                "NumHEPAfilters": 0,
                "NumUVBulbs": 0,
                "ctHumidifierNumPads": 0,
                "AuxDehumidifierStatus": False,
                "AuxHumidifierStatus": False,
                "AuxVentilatorStatus": False,
                "ctSystemCapVentilation": False,
                "alertMediaAirFilterDays": 105,
                "alertMediaAirFilterDaysLimit": 186,
                "alertMediaAirFilterActive": False,
                "alertServiceDaysLimit": 0,
                "alertServiceActive": False,
            }
        )
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.num_media_filters == 1
        assert thermostat.media_air_filter_days == 105
        assert thermostat.media_air_filter_days_limit == 186
        assert thermostat.media_air_filter_active is False
        assert thermostat.service_days_limit == 0

    def test_consumable_mapping_zero_date_maps_to_none(self) -> None:
        """Verify alert*Date with 0 maps to None instead of failing pydantic validation."""
        device_data = _make_device()
        device_data["data"]["alertMediaAirFilterDate"] = 0
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.media_air_filter_date is None


class TestMapEquipmentAndSystemErrors:
    """Test mapping of equipment (fault1..25) and system (sysFault1..20) error history."""

    def test_format_error_code(self) -> None:
        assert format_error_code(None) is None
        assert format_error_code(0) is None
        assert format_error_code(255) is None
        assert format_error_code(5) == "05"
        assert format_error_code(16) == "10"
        assert format_error_code(20) == "14"
        assert format_error_code(180) == "B4"
        assert format_error_code(236) == "EC"

    def test_map_equipment_errors_returns_top_3_sorted_and_formats_hex(self) -> None:
        device_data = _make_device()
        device_data["data"].update(
            {
                "fault1Code": 20,
                "fault1Date": 1792128343,
                "fault1Level": 1,
                "fault1Equipment": 6,
                "fault2Code": 180,
                "fault2Date": 1791019718,
                "fault2Level": 2,
                "fault2Equipment": 3,
                "fault3Code": 236,
                "fault3Date": 1789548186,
                "fault3Level": 2,
                "fault3Equipment": 3,
                "fault4Code": 208,
                "fault4Date": 1729524703,
                "fault4Level": 2,
                "fault4Equipment": 3,
                "fault5Code": 0,
                "fault5Date": 0,
                "fault6Code": 255,
                "fault6Date": 1793000000,
            }
        )
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.equipment_errors is not None
        assert len(thermostat.equipment_errors) == 3

        assert [e.code for e in thermostat.equipment_errors] == ["14", "B4", "EC"]
        assert [e.raw_code for e in thermostat.equipment_errors] == [20, 180, 236]
        assert [e.severity for e in thermostat.equipment_errors] == ["minor", "critical", "critical"]
        assert [e.level for e in thermostat.equipment_errors] == [1, 2, 2]
        assert [e.equipment_id for e in thermostat.equipment_errors] == [6, 3, 3]
        assert thermostat.equipment_errors[0].timestamp == datetime(2026, 10, 16, 5, 25, 43, tzinfo=UTC)

    def test_map_system_errors_filters_pre_ntp_22_and_returns_top_3(self) -> None:
        device_data = _make_device()
        device_data["data"].update(
            {
                "sysFault1Code": 16,
                "sysFault1Date": 22,  # Pre-NTP boot uptime, must be skipped
                "sysFault2Code": 16,
                "sysFault2Date": 1784579020,
                "sysFault3Code": 16,
                "sysFault3Date": 22,
                "sysFault4Code": 16,
                "sysFault4Date": 1783311641,
                "sysFault5Code": 5,
                "sysFault5Date": 1760384142,
                "sysFault6Code": 16,
                "sysFault6Date": 1756383856,
            }
        )
        thermostat = map_thermostat(DaikinDeviceDataResponse(**device_data))
        assert thermostat.system_errors is not None
        assert len(thermostat.system_errors) == 3

        assert [e.code for e in thermostat.system_errors] == ["10", "10", "05"]
        assert [e.raw_code for e in thermostat.system_errors] == [16, 16, 5]
        assert thermostat.system_errors[0].timestamp == datetime(2026, 7, 20, 20, 23, 40, tzinfo=UTC)
