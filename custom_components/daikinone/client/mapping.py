"""Pure functions that turn a Daikin device-data payload into domain models."""

import logging

from custom_components.daikinone.client import fields as f
from custom_components.daikinone.client.models import (
    DaikinEEVCoil,
    DaikinEquipment,
    DaikinIndoorUnit,
    DaikinOneAirQualitySensorIndoor,
    DaikinOneAirQualitySensorOutdoor,
    DaikinOperatingState,
    DaikinOutdoorUnit,
    DaikinOutdoorUnitHeaterStatus,
    DaikinOutdoorUnitReversingValveStatus,
    DaikinThermostat,
    DaikinThermostatCapability,
    DaikinThermostatFanCirculateDuration,
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


def map_thermostat(payload: DaikinDeviceDataResponse) -> DaikinThermostat:
    capabilities: set[DaikinThermostatCapability] = set()
    if payload.data.get("ctSystemCapHeat"):
        capabilities.add(DaikinThermostatCapability.HEAT)
    if payload.data.get("ctSystemCapCool"):
        capabilities.add(DaikinThermostatCapability.COOL)
    if payload.data.get("ctSystemCapEmergencyHeat") and payload.data.get("modeEmHeatAvailable", True):
        capabilities.add(DaikinThermostatCapability.EMERGENCY_HEAT)

    away_mode = payload.data.get("geofencingAway")
    if away_mode is not None:
        away_mode = bool(away_mode)

    fan_circulate_duration_raw = payload.data.get("fanCirculateDuration")
    fan_circulate_duration = (
        DaikinThermostatFanCirculateDuration(fan_circulate_duration_raw)
        if fan_circulate_duration_raw is not None
        else None
    )

    return DaikinThermostat(
        id=payload.id,
        location_id=payload.locationId,
        name=payload.name,
        model=payload.model,
        firmware_version=payload.firmware,
        online=payload.online,
        capabilities=capabilities,
        mode=DaikinThermostatMode(payload.data["mode"]),
        status=DaikinThermostatStatus(payload.data["equipmentStatus"]),
        fan_mode=DaikinThermostatFanMode(payload.data["fanCirculate"]),
        fan_speed=DaikinThermostatFanSpeed(payload.data["fanCirculateSpeed"]),
        schedule=DaikinThermostatSchedule(
            enabled=payload.data["schedEnabled"],
            override=bool(payload.data.get("schedOverride", 0)),
        ),
        indoor_temperature=read(payload.data, f.F_TEMP_INDOOR),
        indoor_humidity=read(payload.data, f.F_HUM_INDOOR),
        set_point_heat=read(payload.data, f.F_SETPOINT_HEAT),
        set_point_heat_min=read(payload.data, f.F_SETPOINT_HEAT_MIN),
        set_point_heat_max=read(payload.data, f.F_SETPOINT_HEAT_MAX),
        set_point_cool=read(payload.data, f.F_SETPOINT_COOL),
        set_point_cool_min=read(payload.data, f.F_SETPOINT_COOL_MIN),
        set_point_cool_max=read(payload.data, f.F_SETPOINT_COOL_MAX),
        outdoor_temperature=read(payload.data, f.F_TEMP_OUTDOOR),
        outdoor_humidity=read(payload.data, f.F_HUM_OUTDOOR),
        air_quality_outdoor=map_air_quality_outdoor(payload),
        air_quality_indoor=map_air_quality_indoor(payload),
        one_clean_fan_active=payload.data.get("oneCleanFanActive"),
        dual_fuel_furnace_lockout_enable=payload.data.get("ctDualFuelFurnaceLockoutEnable"),
        equipment=map_equipment(payload),
        away_mode=away_mode,
        fan_circulate_start=payload.data.get("fanCirculateStart"),
        fan_circulate_stop=payload.data.get("fanCirculateStop"),
        fan_circulate_duration=fan_circulate_duration,
    )


def map_air_quality_outdoor(
    payload: DaikinDeviceDataResponse,
) -> DaikinOneAirQualitySensorOutdoor | None:
    if not payload.data["aqOutdoorAvailable"]:
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
    if not payload.data["aqIndoorAvailable"]:
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
        operation_mode=read(payload.data, f.F_OD_OPERATION_MODE),
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


def determine_operating_state(thermostat: DaikinThermostat) -> tuple[str, str | None]:
    """Determine the operating state and fuel type matching physical on-wall unit."""
    if thermostat.mode == DaikinThermostatMode.OFF:
        return DaikinOperatingState.OFF.value, None

    if thermostat.status == DaikinThermostatStatus.IDLE:
        return DaikinOperatingState.IDLE.value, None

    if thermostat.status == DaikinThermostatStatus.COOLING:
        return DaikinOperatingState.COOLING.value, "electric"

    if thermostat.status == DaikinThermostatStatus.DRYING:
        return DaikinOperatingState.DRYING.value, "electric"

    if thermostat.status == DaikinThermostatStatus.CIRCULATING_AIR:
        return DaikinOperatingState.FAN_ONLY.value, None

    if thermostat.status == DaikinThermostatStatus.HEATING:
        outdoor: DaikinOutdoorUnit | None = next(
            (e for e in thermostat.equipment.values() if isinstance(e, DaikinOutdoorUnit)),
            None,
        )
        furnace: DaikinIndoorUnit | None = next(
            (e for e in thermostat.equipment.values() if isinstance(e, DaikinIndoorUnit) and e.name == "Furnace"),
            None,
        )
        air_handler: DaikinIndoorUnit | None = next(
            (e for e in thermostat.equipment.values() if isinstance(e, DaikinIndoorUnit) and e.name == "Air Handler"),
            None,
        )
        indoor: DaikinIndoorUnit | None = (
            furnace
            or air_handler
            or next(
                (e for e in thermostat.equipment.values() if isinstance(e, DaikinIndoorUnit)),
                None,
            )
        )

        # 1. Defrost cycle takes priority over tempering auxiliary heat
        if outdoor is not None and outdoor.mode and outdoor.mode.lower() == "defrost":
            return DaikinOperatingState.DEFROST.value, "electric"

        # 2. Emergency mode (user forced AUX_HEAT) while heating call active
        if thermostat.mode == DaikinThermostatMode.AUX_HEAT:
            fuel = "gas" if furnace is not None else "electric"
            return DaikinOperatingState.EMERGENCY_HEATING.value, fuel

        # 3. Gas furnace actively firing strictly overrides heat pump Mode 12 spin-down
        if furnace is not None and (furnace.heat_demand_current_percent or 0) > 0:
            return DaikinOperatingState.GAS_HEATING.value, "gas"

        is_decel = (outdoor is not None and outdoor.mode is not None and outdoor.mode.lower() == "decel") or (
            outdoor is not None and outdoor.operation_mode == 12
        )
        hp_running = (
            outdoor is not None
            and (outdoor.heat_demand_percent or 0) > 0
            and (outdoor.compressor_speed_current or 0) > 0
            and indoor is not None
            and (indoor.current_airflow or 0) > 0
            and not is_decel
        )

        # 4. Air handler electric heat strips active while compressor idle
        if air_handler is not None and (air_handler.heat_demand_current_percent or 0) > 0 and not hp_running:
            return DaikinOperatingState.ELECTRIC_HEATING.value, "electric"

        # 5. Inverter heat pump actively delivering heat (including supplemental heat with electric strips)
        if hp_running:
            return DaikinOperatingState.HEAT_PUMP_HEATING.value, "electric"

        # 6. Communicating equipment present but heat delivery not yet proven (warm-up / pre-heat delay)
        if outdoor is not None or indoor is not None:
            return DaikinOperatingState.HEATING_STARTUP.value, None

        # 7. Non-communicating fallback (sub-equipment loads unavailable)
        return DaikinOperatingState.HEATING.value, None

    return DaikinOperatingState.IDLE.value, None
