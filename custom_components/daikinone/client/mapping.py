"""Pure functions that turn a Daikin device-data payload into domain models."""

import json
import logging
import math
from datetime import UTC, datetime
from typing import Any

from custom_components.daikinone.client import fields as f
from custom_components.daikinone.client.fields import (
    F_CAP_COOL,
    F_CAP_EMERGENCY_HEAT,
    F_CAP_HEAT,
    F_MODE_EM_HEAT_AVAILABLE,
    F_P1P2_CAP_COOL,
    F_P1P2_CAP_HEAT,
    F_P1P2_SETPOINT_COOL_MAX,
    F_P1P2_SETPOINT_COOL_MIN,
    F_P1P2_SETPOINT_HEAT_MAX,
    F_P1P2_SETPOINT_HEAT_MIN,
    F_SETPOINT_COOL_MAX,
    F_SETPOINT_COOL_MIN,
    F_SETPOINT_HEAT_MAX,
    F_SETPOINT_HEAT_MIN,
    F_TEMP_SP_MAX,
    F_TEMP_SP_MIN,
)
from custom_components.daikinone.client.models import (
    DAIKIN_DAY_PREFIXES,
    SCHEDULE_PARTS,
    DaikinDaySchedule,
    DaikinEEVCoil,
    DaikinEquipment,
    DaikinEquipmentError,
    DaikinHeatSource,
    DaikinIndoorUnit,
    DaikinLocation,
    DaikinOneAirQualitySensorIndoor,
    DaikinOneAirQualitySensorOutdoor,
    DaikinOutdoorUnit,
    DaikinOutdoorUnitHeaterStatus,
    DaikinOutdoorUnitReversingValveStatus,
    DaikinSchedulePeriod,
    DaikinSystemError,
    DaikinThermostat,
    DaikinThermostatCapability,
    DaikinThermostatFanCirculateDuration,
    DaikinThermostatFanMode,
    DaikinThermostatFanSpeed,
    DaikinThermostatMode,
    DaikinThermostatSchedule,
    DaikinThermostatStatus,
    format_error_code,
)
from custom_components.daikinone.client.wire import (
    DaikinDeviceDataResponse,
    DaikinLocationResponse,
    capitalize,
    read,
)
from custom_components.daikinone.utils import Temperature

log = logging.getLogger(__name__)

MIN_VALID_EPOCH_TIMESTAMP = 1_000_000_000
MAX_VALID_EPOCH_TIMESTAMP = 253_402_300_799


def map_equipment_errors(data: dict[str, Any], max_entries: int = 3) -> list[DaikinEquipmentError]:
    """Map the most recent valid equipment faults from fault1Code..fault25Code."""
    events: list[DaikinEquipmentError] = []

    for index in range(1, 26):
        raw_code = data.get(f"fault{index}Code")
        epoch = data.get(f"fault{index}Date")
        raw_level = data.get(f"fault{index}Level")
        raw_equipment_id = data.get(f"fault{index}Equipment")

        if not isinstance(raw_code, int) or isinstance(raw_code, bool):
            continue
        code = format_error_code(raw_code)
        if code is None or not isinstance(epoch, int) or isinstance(epoch, bool):
            continue
        if not MIN_VALID_EPOCH_TIMESTAMP <= epoch <= MAX_VALID_EPOCH_TIMESTAMP or epoch == 4_294_967_295:
            continue

        level = (
            raw_level
            if isinstance(raw_level, int) and not isinstance(raw_level, bool) and raw_level in (1, 2)
            else None
        )
        equipment_id = (
            raw_equipment_id
            if isinstance(raw_equipment_id, int)
            and not isinstance(raw_equipment_id, bool)
            and 0 <= raw_equipment_id <= 254
            else None
        )
        severity = "critical" if level == 2 else "minor"

        events.append(
            DaikinEquipmentError(
                timestamp=datetime.fromtimestamp(epoch, tz=UTC),
                code=code,
                raw_code=raw_code,
                severity=severity,
                level=level,
                equipment_id=equipment_id,
            )
        )

    events.sort(key=lambda event: event.timestamp, reverse=True)
    return events[: max(0, max_entries)]


def map_system_errors(data: dict[str, Any], max_entries: int = 3) -> list[DaikinSystemError]:
    """Map the most recent valid thermostat faults from sysFault1Code..sysFault20Code."""
    events: list[DaikinSystemError] = []

    for index in range(1, 21):
        raw_code = data.get(f"sysFault{index}Code")
        epoch = data.get(f"sysFault{index}Date")

        if not isinstance(raw_code, int) or isinstance(raw_code, bool):
            continue
        code = format_error_code(raw_code)
        if code is None or not isinstance(epoch, int) or isinstance(epoch, bool):
            continue
        if not MIN_VALID_EPOCH_TIMESTAMP <= epoch <= MAX_VALID_EPOCH_TIMESTAMP or epoch == 4_294_967_295:
            continue

        events.append(
            DaikinSystemError(
                timestamp=datetime.fromtimestamp(epoch, tz=UTC),
                code=code,
                raw_code=raw_code,
            )
        )

    events.sort(key=lambda event: event.timestamp, reverse=True)
    return events[: max(0, max_entries)]


def _time_slot(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 95:
        return value
    return None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


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
    d = payload.data
    capabilities: set[DaikinThermostatCapability] = set()
    if F_CAP_HEAT.read(d) or F_P1P2_CAP_HEAT.read(d):
        capabilities.add(DaikinThermostatCapability.HEAT)
    if F_CAP_COOL.read(d) or F_P1P2_CAP_COOL.read(d):
        capabilities.add(DaikinThermostatCapability.COOL)
    if F_CAP_EMERGENCY_HEAT.read(d) and F_MODE_EM_HEAT_AVAILABLE.read(d):
        capabilities.add(DaikinThermostatCapability.EMERGENCY_HEAT)

    away_mode = payload.data.get("geofencingAway")
    if away_mode is not None:
        away_mode = bool(away_mode)

    fan_circulate_duration_raw = payload.data.get("fanCirculateDuration")
    aux_heat_lockout_temp = payload.data.get("auxHeatLockoutTemp")
    if aux_heat_lockout_temp is not None:
        try:
            aux_heat_lockout_temp = float(aux_heat_lockout_temp)
        except TypeError, ValueError:
            aux_heat_lockout_temp = None
        else:
            if not math.isfinite(aux_heat_lockout_temp) or aux_heat_lockout_temp in {255, 65535, -32768}:
                aux_heat_lockout_temp = None

    def as_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            result = int(value)
        except ValueError, TypeError, OverflowError:
            return None
        if isinstance(value, float) and not value.is_integer():
            return None
        if result < 0 or result in (255, 65535, 4294967295):
            return None
        return result

    def as_bool(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("true", "1"):
                return True
            if normalized in ("false", "0"):
                return False
        return None

    def as_str(value: Any) -> str | None:
        if value is None or value == 0 or value == "0":
            return None
        if value in (255, 65535, -32768, 4294967295):
            return None
        return str(value)

    data = payload.data
    sched_resume_time_val = payload.data.get("schedResumeTime")
    sched_resume_time = (
        datetime.fromtimestamp(sched_resume_time_val, tz=UTC)
        if isinstance(sched_resume_time_val, (int, float)) and sched_resume_time_val > 0
        else None
    )
    sched_override_duration = payload.data.get("schedOverrideDuration")

    temp_offset: float | None = None
    if "tempOffset" in payload.data and payload.data["tempOffset"] is not None:
        temp_val = read(payload.data, f.F_TEMP_OFFSET)
        if temp_val is not None:
            temp_offset = temp_val.celsius

    hum_offset: int | None = None
    if "humOffset" in payload.data and payload.data["humOffset"] is not None:
        hum_offset = read(payload.data, f.F_HUM_OFFSET)

    set_point_heat_max = F_SETPOINT_HEAT_MAX.read(d) or F_P1P2_SETPOINT_HEAT_MAX.read(d) or F_TEMP_SP_MAX.read(d)
    set_point_heat_min = F_SETPOINT_HEAT_MIN.read(d) or F_P1P2_SETPOINT_HEAT_MIN.read(d) or F_TEMP_SP_MIN.read(d)
    set_point_cool_max = F_SETPOINT_COOL_MAX.read(d) or F_P1P2_SETPOINT_COOL_MAX.read(d) or F_TEMP_SP_MAX.read(d)
    set_point_cool_min = F_SETPOINT_COOL_MIN.read(d) or F_P1P2_SETPOINT_COOL_MIN.read(d) or F_TEMP_SP_MIN.read(d)

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
        schedule=(
            DaikinThermostatSchedule(enabled=bool(payload.data.get("schedEnabled", False)))
            if is_one_lite
            else map_thermostat_schedule(payload.data)
        ),
        indoor_temperature=_read_field(payload.data, f.F_TEMP_INDOOR),
        indoor_humidity=_read_field(payload.data, f.F_HUM_INDOOR),
        set_point_heat=_read_field(payload.data, f.F_SETPOINT_HEAT),
        set_point_heat_min=set_point_heat_min,
        set_point_heat_max=set_point_heat_max,
        set_point_cool=_read_field(payload.data, f.F_SETPOINT_COOL),
        set_point_cool_min=set_point_cool_min,
        set_point_cool_max=set_point_cool_max,
        outdoor_temperature=_read_field(payload.data, f.F_TEMP_OUTDOOR),
        outdoor_humidity=_read_field(payload.data, f.F_HUM_OUTDOOR),
        air_quality_outdoor=map_air_quality_outdoor(payload) if not is_one_lite else None,
        air_quality_indoor=map_air_quality_indoor(payload) if not is_one_lite else None,
        one_clean_fan_active=payload.data.get("oneCleanFanActive"),
        dual_fuel_furnace_lockout_enable=payload.data.get("ctDualFuelFurnaceLockoutEnable"),
        equipment=map_equipment(payload) if not is_one_lite else {},
        away_mode=away_mode,
        fan_circulate_start=_time_slot(payload.data.get("fanCirculateStart")),
        fan_circulate_stop=_time_slot(payload.data.get("fanCirculateStop")),
        fan_circulate_duration=(
            DaikinThermostatFanCirculateDuration(fan_circulate_duration_raw)
            if fan_circulate_duration_raw is not None
            else None
        ),
        night_mode_enabled=_optional_bool(payload.data.get("nightModeEnabled")),
        night_mode_active=_optional_bool(payload.data.get("nightModeActive")),
        night_mode_start=_time_slot(payload.data.get("nightModeStart")),
        night_mode_stop=_time_slot(payload.data.get("nightModeStop")),
        night_mode_light_bar_allowed=_optional_bool(payload.data.get("nightModeLightBarAllowed")),
        quiet_mode_enabled=_optional_bool(payload.data.get("ctOutdoorQuietModeEnabled")),
        quiet_mode_active=_optional_bool(payload.data.get("quietModeActive")),
        quiet_mode_start_time=_time_slot(payload.data.get("quietModeStartTime")),
        quiet_mode_stop_time=_time_slot(payload.data.get("quietModeStopTime")),
        quiet_mode_ho_display_enable=_optional_bool(payload.data.get("ctQuietModeHODisplayEnable")),
        aux_heat_lockout_temp=aux_heat_lockout_temp,
        num_media_filters=as_int(data.get("NumMediafilters")),
        num_electronic_filters=as_int(data.get("NumElectronicfilters")),
        num_hepa_filters=as_int(data.get("NumHEPAfilters")),
        num_uv_bulbs=as_int(data.get("NumUVBulbs")),
        ct_humidifier_num_pads=as_int(data.get("ctHumidifierNumPads")),
        aux_humidifier_status=as_bool(data.get("AuxHumidifierStatus")),
        aux_dehumidifier_status=as_bool(data.get("AuxDehumidifierStatus")),
        aux_ventilator_status=as_bool(data.get("AuxVentilatorStatus")),
        ct_system_cap_ventilation=as_bool(data.get("ctSystemCapVentilation")),
        media_air_filter_days=as_int(data.get("alertMediaAirFilterDays")),
        media_air_filter_days_limit=as_int(data.get("alertMediaAirFilterDaysLimit")),
        media_air_filter_runtime=as_int(data.get("alertMediaAirFilterRuntime")),
        media_air_filter_runtime_limit=as_int(data.get("alertMediaAirFilterRuntimeLimit")),
        media_air_filter_active=as_bool(data.get("alertMediaAirFilterActive")),
        media_air_filter_date=as_str(data.get("alertMediaAirFilterDate")),
        service_days=as_int(data.get("alertServiceDays")),
        service_days_limit=as_int(data.get("alertServiceDaysLimit")),
        service_active=as_bool(data.get("alertServiceActive")),
        service_date=as_str(data.get("alertServiceDate")),
        hum_pad_days=as_int(data.get("alertHumPadDays")),
        hum_pad_days_limit=as_int(data.get("alertHumPadDaysLimit")),
        hum_pad_runtime=as_int(data.get("alertHumPadRuntime")),
        hum_pad_runtime_limit=as_int(data.get("alertHumPadRuntimeLimit")),
        hum_pad_active=as_bool(data.get("alertHumPadActive")),
        hum_pad_date=as_str(data.get("alertHumPadDate")),
        uv_days=as_int(data.get("alertUVDays")),
        uv_days_limit=as_int(data.get("alertUVDaysLimit")),
        uv_runtime=as_int(data.get("alertUVRuntime")),
        uv_runtime_limit=as_int(data.get("alertUVRuntimeLimit")),
        uv_active=as_bool(data.get("alertUVActive")),
        uv_date=as_str(data.get("alertUVDate")),
        hepa_filter_days=as_int(data.get("alertHEPAAirFilterDays")),
        hepa_filter_days_limit=as_int(data.get("alertHEPAAirFilterDaysLimit")),
        hepa_filter_runtime=as_int(data.get("alertHEPAAirFilterRuntime")),
        hepa_filter_runtime_limit=as_int(data.get("alertHEPAAirFilterRuntimeLimit")),
        hepa_filter_active=as_bool(data.get("alertHEPAAirFilterActive")),
        hepa_filter_date=as_str(data.get("alertHEPAAirFilterDate")),
        electronic_filter_days=as_int(data.get("alertElectronicAirFilterDays")),
        electronic_filter_days_limit=as_int(data.get("alertElectronicAirFilterDaysLimit")),
        electronic_filter_runtime=as_int(data.get("alertElectronicAirFilterRuntime")),
        electronic_filter_runtime_limit=as_int(data.get("alertElectronicAirFilterRuntimeLimit")),
        electronic_filter_active=as_bool(data.get("alertElectronicAirFilterActive")),
        electronic_filter_date=as_str(data.get("alertElectronicAirFilterDate")),
        dehum_filter_days=as_int(data.get("alertDehumFilterDays")),
        dehum_filter_days_limit=as_int(data.get("alertDehumFilterDaysLimit")),
        dehum_filter_runtime=as_int(data.get("alertDehumFilterRuntime")),
        dehum_filter_runtime_limit=as_int(data.get("alertDehumFilterRuntimeLimit")),
        dehum_filter_active=as_bool(data.get("alertDehumFilterActive")),
        dehum_filter_date=as_str(data.get("alertDehumFilterDate")),
        ventilation_days=as_int(data.get("alertVentilationDays")),
        ventilation_days_limit=as_int(data.get("alertVentilationDaysLimit")),
        ventilation_active=as_bool(data.get("alertVentilationActive")),
        ventilation_date=as_str(data.get("alertVentilationDate")),
        equipment_errors=map_equipment_errors(payload.data),
        system_errors=map_system_errors(payload.data),
        sched_resume_time=sched_resume_time,
        sched_override_duration=sched_override_duration,
        hum_setpoint=read(payload.data, f.F_HUM_SETPOINT) if f.F_HUM_SETPOINT.key in payload.data else None,
        dehum_setpoint=read(payload.data, f.F_DEHUM_SETPOINT) if f.F_DEHUM_SETPOINT.key in payload.data else None,
        humidification_available=read(payload.data, f.F_CAP_HUMIDIFICATION),
        dehumidification_available=read(payload.data, f.F_CAP_DEHUMIDIFICATION),
        is_one_lite=is_one_lite,
        units=payload.data.get("units", 0),
        temp_offset=temp_offset,
        hum_offset=hum_offset,
    )


def map_thermostat_schedule(data: dict[str, Any]) -> DaikinThermostatSchedule:
    """Parse thermostat schedule state and 7-day x 6-part schedule matrix from raw payload data."""
    enabled = bool(data["schedEnabled"])
    override = bool(data.get("schedOverride", 0))

    raw_delta = data.get("tempDeltaMin", 2.0)
    try:
        min_temp_delta = float(raw_delta) if raw_delta is not None else 2.0
    except ValueError, TypeError:
        min_temp_delta = 2.0

    sched_hsp_raw = data.get("hspSched")
    scheduled_heat = (
        Temperature.from_celsius(float(sched_hsp_raw))
        if isinstance(sched_hsp_raw, (int, float)) and -60 <= float(sched_hsp_raw) <= 80
        else None
    )

    sched_csp_raw = data.get("cspSched")
    scheduled_cool = (
        Temperature.from_celsius(float(sched_csp_raw))
        if isinstance(sched_csp_raw, (int, float)) and -60 <= float(sched_csp_raw) <= 80
        else None
    )

    days: dict[str, DaikinDaySchedule] = {}
    has_any_schedule_keys = False

    for day_key, day_prefix in DAIKIN_DAY_PREFIXES.items():
        periods: dict[int, DaikinSchedulePeriod] = {}
        for part in SCHEDULE_PARTS:
            prefix = f"sched{day_prefix}Part{part}"
            time_key = f"{prefix}Time"
            enabled_key = f"{prefix}Enabled"
            hsp_key = f"{prefix}hsp"
            csp_key = f"{prefix}csp"
            label_key = f"{prefix}Label"
            action_key = f"{prefix}Action"

            if time_key not in data and enabled_key not in data and hsp_key not in data and csp_key not in data:
                continue

            has_any_schedule_keys = True

            raw_slot = data.get(time_key, 0)
            try:
                slot = int(raw_slot)
            except ValueError, TypeError:
                slot = 0
            # Guard against U8 sentinel (255) or out-of-bounds slots
            if not (0 <= slot <= 95):
                slot = 0

            part_enabled = bool(data.get(enabled_key, False))

            raw_hsp = data.get(hsp_key, 20.0)
            try:
                hsp_c = float(raw_hsp)
            except ValueError, TypeError:
                hsp_c = 20.0

            raw_csp = data.get(csp_key, 24.0)
            try:
                csp_c = float(raw_csp)
            except ValueError, TypeError:
                csp_c = 24.0

            raw_label = data.get(label_key, "")
            label = str(raw_label).strip() if raw_label is not None else ""

            raw_action = data.get(action_key, 0)
            try:
                action = int(raw_action)
            except ValueError, TypeError:
                action = 0

            periods[part] = DaikinSchedulePeriod(
                part=part,
                enabled=part_enabled,
                start_slot=slot,
                heat_setpoint=Temperature.from_celsius(hsp_c),
                cool_setpoint=Temperature.from_celsius(csp_c),
                label=label,
                action=action,
            )

        if periods:
            days[day_key] = DaikinDaySchedule(day=day_key, periods=periods)

    return DaikinThermostatSchedule(
        enabled=enabled,
        override=override,
        days=days if has_any_schedule_keys else None,
        min_temp_delta=min_temp_delta,
        scheduled_heat_setpoint=scheduled_heat,
        scheduled_cool_setpoint=scheduled_cool,
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


def determine_heat_source(thermostat: DaikinThermostat) -> DaikinHeatSource:
    """Determine the active heat source delivering heat to the space."""
    if thermostat.status != DaikinThermostatStatus.HEATING or thermostat.mode == DaikinThermostatMode.OFF:
        return DaikinHeatSource.NONE

    furnace = thermostat.furnace
    if furnace is not None:
        furnace_heat = (
            (furnace.heat_demand_current_percent or 0) > 0
            or (furnace.heat_demand_requested_percent or 0) > 0
            or (furnace.mode is not None and furnace.mode.lower() == "heating")
        )
        if furnace_heat:
            return DaikinHeatSource.GAS

    outdoor = thermostat.outdoor
    compressor_speed = outdoor.compressor_speed_current or 0 if outdoor is not None else 0
    compressor_idle = outdoor is None or compressor_speed == 0

    air_handler = thermostat.air_handler
    if air_handler is not None:
        ah_heat = (
            (air_handler.heat_demand_current_percent or 0) > 0
            or (air_handler.heat_demand_requested_percent or 0) > 0
            or (air_handler.mode is not None and air_handler.mode.lower() == "heating")
        )
        if ah_heat and compressor_idle:
            return DaikinHeatSource.RESISTIVE

    indoor = thermostat.indoor
    indoor_airflow = indoor.current_airflow or 0 if indoor is not None else 0
    outdoor_heat_demand = outdoor.heat_demand_percent or 0 if outdoor is not None else 0
    is_defrost = outdoor is not None and outdoor.mode is not None and "defrost" in outdoor.mode.lower()
    is_decel = outdoor is not None and outdoor.mode is not None and "decel" in outdoor.mode.lower()

    if (
        outdoor is not None
        and (outdoor.heat_demand_percent is None or outdoor_heat_demand > 0)
        and compressor_speed > 0
        and indoor_airflow > 0
        and not is_defrost
        and not is_decel
    ):
        return DaikinHeatSource.HEAT_PUMP

    return DaikinHeatSource.NONE


def map_location(response: DaikinLocationResponse) -> DaikinLocation:
    """Map a DaikinLocationResponse wire object to a DaikinLocation domain model."""
    raw_addr = response.address or ""
    street_address = raw_addr
    apt = ""
    if raw_addr:
        try:
            parsed = json.loads(raw_addr)
            if isinstance(parsed, dict):
                street_address = str(parsed.get("address", "") or "")
                apt = str(parsed.get("apt", "") or "")
            else:
                street_address = raw_addr
        except json.JSONDecodeError, TypeError, ValueError:
            street_address = raw_addr

    return DaikinLocation(
        id=response.id,
        name=response.name,
        street_address=street_address,
        apt=apt,
        city=response.city or "",
        province=response.province or "",
        postal_code=response.postalCode or "",
        country=response.country or "",
        time_zone=response.timeZone or "",
        latitude=response.latitude,
        longitude=response.longitude,
        has_owner=bool(response.hasOwner),
    )
