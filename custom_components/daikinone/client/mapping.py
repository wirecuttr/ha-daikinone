"""Pure functions that turn a Daikin device-data payload into domain models."""

import logging
from typing import Any

from custom_components.daikinone.client import fields as f
from custom_components.daikinone.client.models import (
    DaikinEEVCoil,
    DaikinEquipment,
    DaikinIndoorUnit,
    DaikinOneAirQualitySensorIndoor,
    DaikinOneAirQualitySensorOutdoor,
    DaikinOutdoorUnit,
    DaikinOutdoorUnitHeaterStatus,
    DaikinOutdoorUnitReversingValveStatus,
    DaikinThermostat,
    DaikinThermostatCapability,
    DaikinThermostatFanMode,
    DaikinThermostatFanSpeed,
    DaikinThermostatMode,
    DaikinThermostatSchedule,
    DaikinThermostatStatus,
)
from custom_components.daikinone.client.wire import (
    DaikinDeviceDataResponse,
    capitalize,
    read,
)

log = logging.getLogger(__name__)


def _read_field(data: dict[str, Any], field: Any) -> Any:
    if field.key not in data or data[field.key] is None:
        return None
    return read(data, field)


def _normalize_one_lite_payload(data: dict[str, Any], model: str | None = None) -> bool:
    """Normalize One Lite (D2271 / ONELITE_24V) payload keys to canonical Skyport field names.

    Returns True if One Lite schema is detected and normalized, False otherwise.
    """
    is_one_lite = (
        model in ("ONELITE_24V", "D2271", "ONELITE")
        or data.get("model") in ("ONELITE_24V", "D2271", "ONELITE")
        or "coolSP" in data
    )
    if not is_one_lite:
        return False

    aliases = {
        "cspActive": "coolSP",
        "hspActive": "heatSP",
        "cspHome": "coolSP",
        "hspHome": "heatSP",
        "tempIndoor": "spaceTemp",
        "humIndoor": "spaceHum",
        "equipmentStatus": "eqStatus",
        "geofencingAway": "away",
        "schedEnabled": "progOn",
        "schedOverride": "progOn",
        "statFirmware": "firmwareVersion",
        "nightModeEnabled": "nightDimmer",
        "nightModeActive": "nightDimmer",
        "displayLockPIN": "security",
        "alertMediaAirFilterDays": "filterDaysRun",
    }
    for canonical, native in aliases.items():
        if native in data:
            data[canonical] = data[native]

    data.setdefault("fanCirculate", 0)
    data.setdefault("fanCirculateSpeed", 0)
    data.setdefault("schedOverrideDuration", 0)

    has_heat = bool(data.get("heat1") or data.get("heat2") or data.get("w1ObTerminal"))
    data.setdefault("ctSystemCapHeat", has_heat)

    has_cool = bool(data.get("cool1") or data.get("cool2") or data.get("y1Terminal"))
    cool_stages = int(has_cool)
    data.setdefault("ctOutdoorNoofCoolStages", cool_stages)
    data.setdefault("ctSystemCapCool", has_cool)
    data.setdefault("ctSystemCapEmergencyHeat", False)

    data.setdefault("aqOutdoorAvailable", False)
    data.setdefault("aqIndoorAvailable", False)

    return True


def map_thermostat(payload: DaikinDeviceDataResponse) -> DaikinThermostat:
    is_one_lite = _normalize_one_lite_payload(payload.data, model=payload.model)

    capabilities: set[DaikinThermostatCapability] = set()
    if payload.data.get("ctSystemCapHeat"):
        capabilities.add(DaikinThermostatCapability.HEAT)
    if payload.data.get("ctSystemCapCool"):
        capabilities.add(DaikinThermostatCapability.COOL)
    if payload.data.get("ctSystemCapEmergencyHeat"):
        capabilities.add(DaikinThermostatCapability.EMERGENCY_HEAT)

    return DaikinThermostat(
        id=payload.id,
        location_id=payload.locationId,
        name=payload.name,
        model=payload.model,
        firmware_version=payload.firmware,
        online=payload.online,
        capabilities=capabilities,
        mode=DaikinThermostatMode(payload.data.get("mode", 0)),
        status=DaikinThermostatStatus(payload.data.get("equipmentStatus", 255)),
        fan_mode=DaikinThermostatFanMode(payload.data.get("fanCirculate", 0)),
        fan_speed=DaikinThermostatFanSpeed(payload.data.get("fanCirculateSpeed", 0)),
        schedule=DaikinThermostatSchedule(enabled=bool(payload.data.get("schedEnabled", False))),
        indoor_temperature=_read_field(payload.data, f.F_TEMP_INDOOR),
        indoor_humidity=_read_field(payload.data, f.F_HUM_INDOOR),
        set_point_heat=_read_field(payload.data, f.F_SETPOINT_HEAT),
        set_point_heat_min=_read_field(payload.data, f.F_SETPOINT_HEAT_MIN),
        set_point_heat_max=_read_field(payload.data, f.F_SETPOINT_HEAT_MAX),
        set_point_cool=_read_field(payload.data, f.F_SETPOINT_COOL),
        set_point_cool_min=_read_field(payload.data, f.F_SETPOINT_COOL_MIN),
        set_point_cool_max=_read_field(payload.data, f.F_SETPOINT_COOL_MAX),
        outdoor_temperature=_read_field(payload.data, f.F_TEMP_OUTDOOR),
        outdoor_humidity=_read_field(payload.data, f.F_HUM_OUTDOOR),
        air_quality_outdoor=map_air_quality_outdoor(payload),
        air_quality_indoor=map_air_quality_indoor(payload),
        equipment=map_equipment(payload),
        is_one_lite=is_one_lite,
    )


def map_air_quality_outdoor(
    payload: DaikinDeviceDataResponse,
) -> DaikinOneAirQualitySensorOutdoor | None:
    if not payload.data.get("aqOutdoorAvailable"):
        return None

    return DaikinOneAirQualitySensorOutdoor(
        aqi=payload.data["aqOutdoorValue"],
        aqi_summary_level=payload.data["aqOutdoorLevel"],
        particles_microgram_m3=payload.data["aqOutdoorParticles"],
        ozone_microgram_m3=payload.data["aqOutdoorOzone"],
    )


def map_air_quality_indoor(
    payload: DaikinDeviceDataResponse,
) -> DaikinOneAirQualitySensorIndoor | None:
    if not payload.data.get("aqIndoorAvailable"):
        return None

    return DaikinOneAirQualitySensorIndoor(
        aqi=payload.data["aqIndoorValue"],
        aqi_summary_level=payload.data["aqIndoorLevel"],
        particles=payload.data["aqIndoorParticlesValue"],
        particles_summary_level=payload.data["aqIndoorParticlesLevel"],
        voc=payload.data["aqIndoorVOCValue"],
        voc_summary_level=payload.data["aqIndoorVOCLevel"],
    )


def map_equipment(payload: DaikinDeviceDataResponse) -> dict[str, DaikinEquipment]:
    units: list[DaikinEquipment | None] = [
        _map_air_handler(payload),
        _map_furnace(payload),
        _map_outdoor_unit(payload),
        _map_eev_coil(payload),
    ]
    return {u.id: u for u in units if u is not None}


def _map_air_handler(payload: DaikinDeviceDataResponse) -> DaikinIndoorUnit | None:
    if not read(payload.data, f.F_AH_UNIT_TYPE):
        return None

    model = read(payload.data, f.F_AH_MODEL)
    serial = read(payload.data, f.F_AH_SERIAL)
    if not model or not serial:
        log.warning(
            "Skipping air handler for thermostat %s: model or serial unavailable in this response",
            payload.id,
        )
        return None
    eid = f"{model}-{serial}"

    return DaikinIndoorUnit(
        id=eid,
        thermostat_id=payload.id,
        name="Air Handler",
        model=model,
        firmware_version=read(payload.data, f.F_AH_FIRMWARE),
        serial=serial,
        mode=capitalize(read(payload.data, f.F_AH_MODE)),
        current_airflow=read(payload.data, f.F_AH_AIRFLOW),
        fan_demand_requested_percent=read(payload.data, f.F_AH_FAN_REQ_DEMAND),
        fan_demand_current_percent=read(payload.data, f.F_AH_FAN_CUR_DEMAND),
        heat_demand_requested_percent=read(payload.data, f.F_AH_HEAT_REQ_DEMAND),
        heat_demand_current_percent=read(payload.data, f.F_AH_HEAT_CUR_DEMAND),
        cool_demand_requested_percent=None,
        cool_demand_current_percent=None,
        humidification_demand_requested_percent=read(payload.data, f.F_AH_HUM_REQ_DEMAND),
        dehumidification_demand_requested_percent=None,
        power_usage=read(payload.data, f.F_INDOOR_POWER),
    )


def _map_furnace(payload: DaikinDeviceDataResponse) -> DaikinIndoorUnit | None:
    if not read(payload.data, f.F_IFC_UNIT_TYPE):
        return None

    model = read(payload.data, f.F_IFC_MODEL)
    serial = read(payload.data, f.F_IFC_SERIAL)
    if not model or not serial:
        log.warning(
            "Skipping furnace for thermostat %s: model or serial unavailable in this response",
            payload.id,
        )
        return None
    eid = f"{model}-{serial}"

    return DaikinIndoorUnit(
        id=eid,
        thermostat_id=payload.id,
        name="Furnace",
        model=model,
        firmware_version=read(payload.data, f.F_IFC_FIRMWARE),
        serial=serial,
        mode=capitalize(read(payload.data, f.F_IFC_MODE)),
        current_airflow=read(payload.data, f.F_IFC_AIRFLOW),
        fan_demand_requested_percent=read(payload.data, f.F_IFC_FAN_REQ_DEMAND),
        fan_demand_current_percent=read(payload.data, f.F_IFC_FAN_CUR_DEMAND),
        heat_demand_requested_percent=read(payload.data, f.F_IFC_HEAT_REQ_DEMAND),
        heat_demand_current_percent=read(payload.data, f.F_IFC_HEAT_CUR_DEMAND),
        cool_demand_requested_percent=read(payload.data, f.F_IFC_COOL_REQ_DEMAND),
        cool_demand_current_percent=read(payload.data, f.F_IFC_COOL_CUR_DEMAND),
        humidification_demand_requested_percent=read(payload.data, f.F_IFC_HUM_REQ_DEMAND),
        dehumidification_demand_requested_percent=read(payload.data, f.F_IFC_DEHUM_REQ_DEMAND),
        power_usage=read(payload.data, f.F_INDOOR_POWER),
    )


def _map_outdoor_unit(payload: DaikinDeviceDataResponse) -> DaikinOutdoorUnit | None:
    if not read(payload.data, f.F_OD_UNIT_TYPE):
        return None

    model = read(payload.data, f.F_OD_MODEL)
    serial = read(payload.data, f.F_OD_SERIAL)
    if not model or not serial:
        log.warning(
            "Skipping outdoor unit for thermostat %s: model or serial unavailable in this response",
            payload.id,
        )
        return None
    eid = f"{model}-{serial}"

    # assume it can cool, and if it can also heat it should be a heat pump
    heat_max_rps = read(payload.data, f.F_OD_HEAT_MAX_RPS)
    name = "Heat Pump" if heat_max_rps else "Condensing Unit"

    return DaikinOutdoorUnit(
        id=eid,
        thermostat_id=payload.id,
        name=name,
        model=model,
        serial=serial,
        firmware_version=read(payload.data, f.F_OD_FIRMWARE),
        inverter_software_version=read(payload.data, f.F_OD_INVERTER_FIRMWARE),
        total_runtime=read(payload.data, f.F_OD_COMPRESSOR_RUNTIME),
        mode=capitalize(read(payload.data, f.F_OD_MODE)),
        compressor_speed_target=read(payload.data, f.F_OD_COMPRESSOR_SPEED_TARGET),
        compressor_speed_current=read(payload.data, f.F_OD_COMPRESSOR_SPEED_CURRENT),
        outdoor_fan_target_rpm=read(payload.data, f.F_OD_FAN_TARGET_RPM),
        outdoor_fan_rpm=read(payload.data, f.F_OD_FAN_RPM),
        suction_pressure_psi=read(payload.data, f.F_OD_SUCTION_PRESSURE),
        eev_opening_percent=read(payload.data, f.F_OD_EEV_OPENING),
        reversing_valve=DaikinOutdoorUnitReversingValveStatus(payload.data["ctReversingValve"]),
        heat_demand_percent=read(payload.data, f.F_OD_HEAT_REQ_DEMAND),
        cool_demand_percent=read(payload.data, f.F_OD_COOL_REQ_DEMAND),
        fan_demand_percent=read(payload.data, f.F_OD_FAN_REQ_DEMAND),
        fan_demand_airflow=read(payload.data, f.F_OD_FAN_REQ_AIRFLOW),
        dehumidify_demand_percent=read(payload.data, f.F_OD_DEHUM_REQ_DEMAND),
        air_temperature=read(payload.data, f.F_OD_AIR_TEMP),
        coil_temperature=read(payload.data, f.F_OD_COIL_TEMP),
        discharge_temperature=read(payload.data, f.F_OD_DISCHARGE_TEMP),
        liquid_temperature=read(payload.data, f.F_OD_LIQUID_TEMP),
        defrost_sensor_temperature=read(payload.data, f.F_OD_DEFROST_TEMP),
        inverter_fin_temperature=read(payload.data, f.F_OD_INVERTER_FIN_TEMP),
        power_usage=read(payload.data, f.F_OD_POWER),
        compressor_amps=read(payload.data, f.F_OD_COMPRESSOR_AMPS),
        inverter_amps=read(payload.data, f.F_OD_INVERTER_AMPS),
        fan_motor_amps=read(payload.data, f.F_OD_FAN_MOTOR_AMPS),
        crank_case_heater=DaikinOutdoorUnitHeaterStatus(payload.data["ctCrankCaseHeaterOnOff"]),
        drain_pan_heater=DaikinOutdoorUnitHeaterStatus(payload.data["ctDrainPanHeaterOnOff"]),
        preheat_heater=DaikinOutdoorUnitHeaterStatus(payload.data["ctPreHeatOnOff"]),
    )


def _map_eev_coil(payload: DaikinDeviceDataResponse) -> DaikinEEVCoil | None:
    if not read(payload.data, f.F_COIL_UNIT_TYPE):
        return None

    serial = read(payload.data, f.F_EEV_SERIAL)
    if not serial:
        log.warning(
            "Skipping EEV coil for thermostat %s: serial unavailable in this response",
            payload.id,
        )
        return None
    eid = f"eevcoil-{serial}"

    return DaikinEEVCoil(
        id=eid,
        thermostat_id=payload.id,
        name="EEV Coil",
        model="EEV Coil",
        serial=serial,
        firmware_version=read(payload.data, f.F_EEV_FIRMWARE),
        pressure_psi=read(payload.data, f.F_EEV_PRESSURE),
        indoor_superheat_temperature=read(payload.data, f.F_EEV_SUPERHEAT_TEMP),
        liquid_temperature=read(payload.data, f.F_EEV_SUBCOOL_TEMP),
        suction_temperature=read(payload.data, f.F_EEV_SUCTION_TEMP),
    )
