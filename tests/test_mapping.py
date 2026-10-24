from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.mapping import (
    determine_heat_source,
    map_location,
    map_thermostat,
)
from custom_components.daikinone.client.models import (
    DaikinEEVCoil,
    DaikinHeatSource,
    DaikinIndoorUnit,
    DaikinOneAirQualitySensorSummaryLevel,
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
)
from custom_components.daikinone.client.wire import DaikinDeviceDataResponse, DaikinLocationResponse


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


class TestBalancePointMapping:
    @pytest.mark.parametrize(
        ("raw_value", "expected"),
        [
            (4.5, 4.5),
            (4, 4.0),
            ("4.5", 4.5),
            (None, None),
            ("invalid", None),
            (float("nan"), None),
            (float("inf"), None),
            (255, None),
            (65535, None),
            (-32768, None),
        ],
    )
    async def test_aux_heat_lockout_temperature_mapping(
        self, daikin_client: DaikinOne, raw_value: Any, expected: float | None
    ) -> None:
        device_data = _make_device()
        device_data["data"]["auxHeatLockoutTemp"] = raw_value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        assert daikin_client.get_thermostats()["device123"].aux_heat_lockout_temp == expected

    async def test_aux_heat_lockout_temperature_missing(self, daikin_client: DaikinOne) -> None:
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [_make_device()]
            await daikin_client.update()

        assert daikin_client.get_thermostats()["device123"].aux_heat_lockout_temp is None


class TestAdditionalValidMappings:
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

    async def test_dual_fuel_fields_absent_are_none(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.dual_fuel_furnace_lockout_enable is None


class TestFanCirculationAndNightModeMapping:
    async def test_optional_fields_map_when_present(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"].update(
            {
                "fanCirculateStart": 4,
                "fanCirculateStop": 92,
                "fanCirculateDuration": 2,
                "nightModeEnabled": True,
                "nightModeActive": False,
                "nightModeStart": 88,
                "nightModeStop": 28,
                "nightModeLightBarAllowed": True,
            }
        )

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.fan_circulate_start == 4
        assert thermostat.fan_circulate_stop == 92
        assert thermostat.fan_circulate_duration is DaikinThermostatFanCirculateDuration.MIN_15
        assert thermostat.night_mode_enabled is True
        assert thermostat.night_mode_active is False
        assert thermostat.night_mode_start == 88
        assert thermostat.night_mode_stop == 28
        assert thermostat.night_mode_light_bar_allowed is True

    async def test_optional_fields_are_none_when_absent(self, daikin_client: DaikinOne) -> None:
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [_make_device()]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.fan_circulate_start is None
        assert thermostat.fan_circulate_stop is None
        assert thermostat.fan_circulate_duration is None
        assert thermostat.night_mode_enabled is None
        assert thermostat.night_mode_active is None
        assert thermostat.night_mode_start is None
        assert thermostat.night_mode_stop is None
        assert thermostat.night_mode_light_bar_allowed is None

    async def test_unknown_duty_cycle_uses_unknown_enum(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"]["fanCirculateDuration"] = 255

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        assert (
            daikin_client.get_thermostats()["device123"].fan_circulate_duration
            is DaikinThermostatFanCirculateDuration.UNKNOWN
        )

    async def test_sentinel_schedule_values_are_treated_as_unavailable(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"].update(
            {
                "fanCirculateStart": 255,
                "fanCirculateStop": 65535,
                "nightModeEnabled": 255,
                "nightModeActive": 65535,
                "nightModeStart": -32768,
                "nightModeStop": 255,
                "nightModeLightBarAllowed": 255,
            }
        )

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.fan_circulate_start is None
        assert thermostat.fan_circulate_stop is None
        assert thermostat.night_mode_enabled is None
        assert thermostat.night_mode_active is None
        assert thermostat.night_mode_start is None
        assert thermostat.night_mode_stop is None
        assert thermostat.night_mode_light_bar_allowed is None


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


class TestMapLocation:
    """Tests for map_location parsing of Daikin Skyport location responses."""

    def test_map_location_valid_json_address(self) -> None:
        raw = {
            "id": "e0a388d4-629b-11ec-a89c-4f75309dfd56",
            "name": "homeHA",
            "address": '{"address":"88 Canada Olympic Rd","apt":"Suite 100"}',
            "city": "Calgary",
            "province": "AB",
            "postalCode": "T3B5R5",
            "country": "CA",
            "timeZone": "America/Regina",
            "latitude": 51.087439,
            "longitude": -114.206518,
            "hasOwner": True,
        }
        loc = map_location(DaikinLocationResponse(**raw))

        assert loc.id == "e0a388d4-629b-11ec-a89c-4f75309dfd56"
        assert loc.name == "homeHA"
        assert loc.street_address == "88 Canada Olympic Rd"
        assert loc.apt == "Suite 100"
        assert loc.city == "Calgary"
        assert loc.province == "AB"
        assert loc.postal_code == "T3B5R5"
        assert loc.country == "CA"
        assert loc.time_zone == "America/Regina"
        assert loc.latitude == pytest.approx(51.087439)
        assert loc.longitude == pytest.approx(-114.206518)
        assert loc.has_owner is True

    def test_map_location_plain_string_address(self) -> None:
        raw = {
            "id": "loc-plain",
            "name": "Mountain Cabin",
            "address": "123 Aspen Way",
            "city": "Banff",
            "province": "AB",
            "postalCode": "T0L 0C0",
            "country": "CA",
            "timeZone": "America/Edmonton",
            "latitude": 51.1784,
            "longitude": -115.5708,
            "hasOwner": False,
        }
        loc = map_location(DaikinLocationResponse(**raw))

        assert loc.id == "loc-plain"
        assert loc.name == "Mountain Cabin"
        assert loc.street_address == "123 Aspen Way"
        assert loc.apt == ""
        assert loc.city == "Banff"
        assert loc.has_owner is False

    def test_map_location_missing_optional_fields(self) -> None:
        raw = {
            "id": "loc-min",
            "name": "Minimal Property",
        }
        loc = map_location(DaikinLocationResponse(**raw))

        assert loc.id == "loc-min"
        assert loc.name == "Minimal Property"
        assert loc.street_address == ""
        assert loc.apt == ""
        assert loc.city == ""
        assert loc.province == ""
        assert loc.postal_code == ""
        assert loc.country == ""
        assert loc.time_zone == ""
        assert loc.latitude is None
        assert loc.longitude is None
        assert loc.has_owner is False

    def test_map_location_null_and_malformed_address(self) -> None:
        raw_null = {
            "id": "loc-null",
            "name": "Null Address Property",
            "address": None,
            "city": None,
            "province": None,
            "postalCode": None,
        }
        loc_null = map_location(DaikinLocationResponse(**raw_null))
        assert loc_null.street_address == ""
        assert loc_null.apt == ""
        assert loc_null.city == ""

        raw_malformed = {
            "id": "loc-malformed",
            "name": "Malformed JSON Address",
            "address": "{invalid json: 'no quotes'}",
        }
        loc_malformed = map_location(DaikinLocationResponse(**raw_malformed))
        assert loc_malformed.street_address == "{invalid json: 'no quotes'}"
        assert loc_malformed.apt == ""


class TestThermostatScheduleMapping:
    """Tests for 7-day x 6-period thermostat schedule mapping in mapping.py."""

    @staticmethod
    def _build_full_42_slot_schedule_data() -> dict[str, Any]:
        """Generate a complete 252-key schedule block matching live Daikin One+ telemetry."""
        sched: dict[str, Any] = {
            "schedEnabled": True,
            "schedOverride": 0,
            "tempDeltaMin": 2,
            "hspSched": 18.0,
            "cspSched": 24.0,
        }
        days = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        default_parts = [
            (1, True, 24, 20.0, 24.0, "wake"),
            (2, True, 51, 20.0, 24.0, "afternoon"),
            (3, True, 68, 20.0, 24.0, "dinner"),
            (4, True, 76, 20.0, 24.0, "evening"),
            (5, True, 84, 18.0, 24.0, "sleep"),
            (6, False, 0, 17.5, 22.0, ""),
        ]
        for day in days:
            for part, enabled, slot, hsp, csp, label in default_parts:
                prefix = f"sched{day}Part{part}"
                sched[f"{prefix}Action"] = 0
                sched[f"{prefix}Enabled"] = enabled
                sched[f"{prefix}Label"] = label
                sched[f"{prefix}Time"] = slot
                sched[f"{prefix}hsp"] = hsp
                sched[f"{prefix}csp"] = csp
        return sched

    async def test_full_42_slot_schedule_mapped(self, daikin_client: DaikinOne) -> None:
        """Verify all 7 days and 6 periods per day are accurately parsed into domain models."""
        device_data = _make_device(self._build_full_42_slot_schedule_data())

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.schedule.enabled is True
        assert thermostat.schedule.override is False
        assert thermostat.schedule.min_temp_delta == 2.0
        assert thermostat.schedule.scheduled_heat_setpoint is not None
        assert thermostat.schedule.scheduled_heat_setpoint.celsius == 18.0
        assert thermostat.schedule.scheduled_cool_setpoint is not None
        assert thermostat.schedule.scheduled_cool_setpoint.celsius == 24.0

        assert thermostat.schedule.days is not None
        assert set(thermostat.schedule.days.keys()) == {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}

        mon = thermostat.schedule.days["mon"]
        assert len(mon.periods) == 6

        p1 = mon.periods[1]
        assert p1.part == 1
        assert p1.enabled is True
        assert p1.start_slot == 24
        assert p1.start_time_str == "06:00"
        assert p1.heat_setpoint.celsius == 20.0
        assert p1.cool_setpoint.celsius == 24.0
        assert p1.label == "wake"
        assert p1.action == 0

        p2 = mon.periods[2]
        assert p2.start_slot == 51
        assert p2.start_time_str == "12:45"

        p6 = mon.periods[6]
        assert p6.part == 6
        assert p6.enabled is False
        assert p6.start_slot == 0
        assert p6.start_time_str == "00:00"
        assert p6.heat_setpoint.celsius == 17.5
        assert p6.cool_setpoint.celsius == 22.0
        assert p6.label == ""

    async def test_schedule_days_none_when_no_part_keys_in_payload(self, daikin_client: DaikinOne) -> None:
        """Verify schedule.days is None when payload only has schedEnabled and no sched<Day>Part<N> keys."""
        device_data = _make_device()

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.schedule.enabled is True
        assert thermostat.schedule.override is False
        assert thermostat.schedule.days is None

    async def test_schedule_handles_sentinel_or_invalid_slot_values_gracefully(self, daikin_client: DaikinOne) -> None:
        """Verify out-of-range slots (e.g. 255 sentinel) clamp/reset to 0 without crashing."""
        sched_data = {
            "schedMonPart1Time": 255,
            "schedMonPart1Enabled": False,
            "schedMonPart1hsp": "invalid",
            "schedMonPart1csp": None,
            "schedMonPart1Label": None,
            "tempDeltaMin": "bad",
        }
        device_data = _make_device(sched_data)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.schedule.min_temp_delta == 2.0
        assert thermostat.schedule.days is not None
        p1 = thermostat.schedule.days["mon"].periods[1]
        assert p1.start_slot == 0
        assert p1.start_time_str == "00:00"
        assert p1.enabled is False
        assert p1.heat_setpoint.celsius == 20.0
        assert p1.cool_setpoint.celsius == 24.0
        assert p1.label == ""

    async def test_thermostat_schedule_defaults_when_unpopulated(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.schedule.enabled is True
        assert thermostat.schedule.override is False
        assert thermostat.sched_resume_time is None
        assert thermostat.sched_override_duration is None

    async def test_thermostat_schedule_active_override_mapping(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device(
            {
                "schedEnabled": True,
                "schedOverride": 1,
                "schedResumeTime": 1792864800,
                "schedOverrideDuration": 120,
            }
        )

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.schedule.enabled is True
        assert thermostat.schedule.override is True
        assert thermostat.sched_resume_time == datetime(2026, 10, 24, 18, 0, 0, tzinfo=UTC)
        assert thermostat.sched_override_duration == 120

    async def test_thermostat_schedule_zero_or_negative_resume_time(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device(
            {
                "schedEnabled": True,
                "schedOverride": 0,
                "schedResumeTime": 0,
                "schedOverrideDuration": 0,
            }
        )

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.schedule.override is False
        assert thermostat.sched_resume_time is None
        assert thermostat.sched_override_duration == 0

        # Negative epoch also returns None
        device_data["data"]["schedResumeTime"] = -1
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.sched_resume_time is None


class TestDetermineHeatSource:
    """Tests for determine_heat_source logic."""

    async def test_off_mode(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device(OUTDOOR_UNIT_DATA, FURNACE_DATA)
        device_data["data"]["mode"] = DaikinThermostatMode.OFF.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert determine_heat_source(thermostat) == DaikinHeatSource.NONE

    async def test_idle_status(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device(OUTDOOR_UNIT_DATA, FURNACE_DATA)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.IDLE.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert determine_heat_source(thermostat) == DaikinHeatSource.NONE

    async def test_cooling_status(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device(OUTDOOR_UNIT_DATA, FURNACE_DATA)
        device_data["data"]["mode"] = DaikinThermostatMode.COOL.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.COOLING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert determine_heat_source(thermostat) == DaikinHeatSource.NONE

    async def test_circulating_air_status(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device(OUTDOOR_UNIT_DATA, FURNACE_DATA)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.CIRCULATING_AIR.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert determine_heat_source(thermostat) == DaikinHeatSource.NONE

    async def test_gas_furnace_active(self, daikin_client: DaikinOne) -> None:
        furnace = {
            **FURNACE_DATA,
            "ctIFCCurrentHeatActualStatus": 70,
            "ctIFCIndoorBlowerAirflow": 450,
        }
        device_data = _make_device(OUTDOOR_UNIT_DATA, furnace)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert determine_heat_source(thermostat) == DaikinHeatSource.GAS

    async def test_heat_pump_steady_state(self, daikin_client: DaikinOne) -> None:
        od = {
            **OUTDOOR_UNIT_DATA,
            "ctOutdoorMode": "heat",
            "ctOutdoorHeatRequestedDemand": 80,
            "ctCurrentCompressorRPS": 50,
        }
        ah = {
            **AIR_HANDLER_DATA,
            "ctAHCurrentIndoorAirflow": 450,
            "ctAHHeatCurrentDemandStatus": 0,
        }
        device_data = _make_device(od, ah)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert determine_heat_source(thermostat) == DaikinHeatSource.HEAT_PUMP

    async def test_resistive_air_handler_heat_strips(self, daikin_client: DaikinOne) -> None:
        od = {
            **OUTDOOR_UNIT_DATA,
            "ctCurrentCompressorRPS": 0,
            "ctOutdoorHeatRequestedDemand": 0,
        }
        ah = {
            **AIR_HANDLER_DATA,
            "ctAHHeatCurrentDemandStatus": 80,
            "ctAHCurrentIndoorAirflow": 400,
        }
        device_data = _make_device(od, ah)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert determine_heat_source(thermostat) == DaikinHeatSource.RESISTIVE

    async def test_supplemental_electric_heat_reports_heat_pump(self, daikin_client: DaikinOne) -> None:
        od = {
            **OUTDOOR_UNIT_DATA,
            "ctOutdoorMode": "heat",
            "ctOutdoorHeatRequestedDemand": 100,
            "ctCurrentCompressorRPS": 60,
        }
        ah = {
            **AIR_HANDLER_DATA,
            "ctAHHeatCurrentDemandStatus": 50,
            "ctAHCurrentIndoorAirflow": 600,
        }
        device_data = _make_device(od, ah)
        device_data["data"]["mode"] = DaikinThermostatMode.HEAT.value
        device_data["data"]["equipmentStatus"] = DaikinThermostatStatus.HEATING.value

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert determine_heat_source(thermostat) == DaikinHeatSource.HEAT_PUMP
