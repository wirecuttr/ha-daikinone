"""Domain models exposed by the Daikin client to the rest of the integration."""

from datetime import datetime, timedelta
from enum import Enum, StrEnum, auto
from typing import Literal

from pydantic.dataclasses import dataclass

from custom_components.daikinone.utils import Temperature


@dataclass
class DaikinUserCredentials:
    email: str
    password: str


@dataclass
class DaikinLocation:
    """Parsed and validated Daikin Skyport property location."""

    id: str
    name: str
    street_address: str
    apt: str
    city: str
    province: str
    postal_code: str
    country: str
    time_zone: str
    latitude: float | None
    longitude: float | None
    has_owner: bool


@dataclass
class DaikinDevice:
    id: str
    name: str
    model: str | None
    firmware_version: str | None


@dataclass
class DaikinEquipment(DaikinDevice):
    thermostat_id: str
    serial: str | None


@dataclass
class DaikinIndoorUnit(DaikinEquipment):
    mode: str | None
    current_airflow: int | None
    fan_demand_requested_percent: int | None
    fan_demand_current_percent: int | None
    heat_demand_requested_percent: int | None
    heat_demand_current_percent: int | None
    cool_demand_requested_percent: int | None
    cool_demand_current_percent: int | None
    humidification_demand_requested_percent: int | None
    dehumidification_demand_requested_percent: int | None
    power_usage: float | None


class DaikinOutdoorUnitReversingValveStatus(Enum):
    OFF = 0
    ON = 1
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> DaikinOutdoorUnitReversingValveStatus:
        return cls.UNKNOWN


class DaikinOutdoorUnitHeaterStatus(Enum):
    OFF = 0
    ON = 1
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> DaikinOutdoorUnitHeaterStatus:
        return cls.UNKNOWN


@dataclass
class DaikinOutdoorUnit(DaikinEquipment):
    inverter_software_version: str | None
    total_runtime: timedelta | None
    mode: str | None
    compressor_speed_target: int | None
    compressor_speed_current: int | None
    outdoor_fan_target_rpm: int | None
    outdoor_fan_rpm: int | None
    suction_pressure_psi: int | None
    eev_opening_percent: int | None
    reversing_valve: DaikinOutdoorUnitReversingValveStatus
    heat_demand_percent: int | None
    cool_demand_percent: int | None
    fan_demand_percent: int | None
    fan_demand_airflow: int | None
    dehumidify_demand_percent: int | None
    air_temperature: Temperature | None
    coil_temperature: Temperature | None
    discharge_temperature: Temperature | None
    liquid_temperature: Temperature | None
    defrost_sensor_temperature: Temperature | None
    inverter_fin_temperature: Temperature | None
    power_usage: float | None
    compressor_amps: float | None
    inverter_amps: float | None
    fan_motor_amps: float | None
    crank_case_heater: DaikinOutdoorUnitHeaterStatus
    drain_pan_heater: DaikinOutdoorUnitHeaterStatus
    preheat_heater: DaikinOutdoorUnitHeaterStatus
    operation_mode: int | None = None

    # needs confirmation on unit in raw data
    # preheat_output_watts: int | None

    # compressor reduction mode - ctOutdoorCompressorReductionMode - 1=off, ?


class DaikinOneAirQualitySensorSummaryLevel(Enum):
    UNKNOWN = 255
    GOOD = 0
    MODERATE = 1
    UNHEALTHY_SENSITIVE = 2
    UNHEALTHY = 3
    VERY_UNHEALTHY = 4
    HAZARDOUS = 5

    @classmethod
    def _missing_(cls, value: object) -> DaikinOneAirQualitySensorSummaryLevel:
        return cls.UNKNOWN


@dataclass
class DaikinOneAirQualitySensorOutdoor:
    aqi: int
    aqi_summary_level: DaikinOneAirQualitySensorSummaryLevel
    particles_microgram_m3: int
    # even though the app displays ppb, the levels seem to be µg/m³ based on my local weather data
    ozone_microgram_m3: int


@dataclass
class DaikinOneAirQualitySensorIndoor:
    aqi: int
    aqi_summary_level: DaikinOneAirQualitySensorSummaryLevel
    # TODO: see if there is unit data available from somewhere
    particles: int
    particles_summary_level: DaikinOneAirQualitySensorSummaryLevel
    voc: int
    voc_summary_level: DaikinOneAirQualitySensorSummaryLevel


@dataclass
class DaikinEEVCoil(DaikinEquipment):
    indoor_superheat_temperature: Temperature | None
    liquid_temperature: Temperature | None
    suction_temperature: Temperature | None
    pressure_psi: int | None


class DaikinHeatSource(StrEnum):
    NONE = "none"
    HEAT_PUMP = "heat_pump"
    GAS = "gas"
    RESISTIVE = "resistive"


class DaikinThermostatCapability(Enum):
    HEAT = auto()
    COOL = auto()
    EMERGENCY_HEAT = auto()


class DaikinThermostatMode(Enum):
    OFF = 0
    HEAT = 1
    COOL = 2
    AUTO = 3
    AUX_HEAT = 4
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> DaikinThermostatMode:
        return cls.UNKNOWN


class DaikinThermostatStatus(Enum):
    COOLING = 1
    DRYING = 2
    HEATING = 3
    CIRCULATING_AIR = 4
    IDLE = 5
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> DaikinThermostatStatus:
        return cls.UNKNOWN


SCHEDULE_DAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAIKIN_DAY_PREFIXES: dict[str, str] = {
    "mon": "Mon",
    "tue": "Tue",
    "wed": "Wed",
    "thu": "Thu",
    "fri": "Fri",
    "sat": "Sat",
    "sun": "Sun",
}
SCHEDULE_PARTS: tuple[int, ...] = (1, 2, 3, 4, 5, 6)


@dataclass
class DaikinSchedulePeriod:
    """Represents one of the 6 daily schedule periods on a Daikin thermostat."""

    part: int
    enabled: bool
    start_slot: int
    heat_setpoint: Temperature
    cool_setpoint: Temperature
    label: str = ""
    action: int = 0

    @property
    def start_time_str(self) -> str:
        """Return the start time formatted as HH:MM (00:00 to 23:45)."""
        clamped = max(0, min(95, self.start_slot))
        total_minutes = clamped * 15
        return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


@dataclass
class DaikinDaySchedule:
    """Represents the 6 schedule periods for a single day of the week."""

    day: str
    periods: dict[int, DaikinSchedulePeriod]


@dataclass
class DaikinThermostatSchedule:
    """Represents the thermostat schedule state and 7-day x 6-period matrix."""

    enabled: bool
    override: bool = False
    days: dict[str, DaikinDaySchedule] | None = None
    min_temp_delta: float = 2.0
    scheduled_heat_setpoint: Temperature | None = None
    scheduled_cool_setpoint: Temperature | None = None


class DaikinThermostatFanMode(Enum):
    OFF = 0
    ALWAYS_ON = 1
    SCHEDULED = 2
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> DaikinThermostatFanMode:
        return cls.UNKNOWN


class DaikinThermostatFanSpeed(Enum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> DaikinThermostatFanSpeed:
        return cls.UNKNOWN


class DaikinThermostatFanCirculateDuration(Enum):
    CONTINUOUS = 0
    MIN_5 = 1
    MIN_15 = 2
    MIN_30 = 3
    MIN_45 = 4
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> DaikinThermostatFanCirculateDuration:
        return cls.UNKNOWN


def format_error_code(raw_code: int | None) -> str | None:
    """Format a valid raw fault code as a two-character uppercase hexadecimal string."""
    if raw_code is None or isinstance(raw_code, bool) or not 0 < raw_code < 255:
        return None
    return f"{raw_code:02X}"


@dataclass
class DaikinEquipmentError:
    timestamp: datetime
    code: str
    raw_code: int
    severity: Literal["critical", "minor"]
    level: int | None
    equipment_id: int | None


@dataclass
class DaikinSystemError:
    timestamp: datetime
    code: str
    raw_code: int


@dataclass
class DaikinThermostat(DaikinDevice):
    location_id: str
    online: bool
    capabilities: set[DaikinThermostatCapability]
    mode: DaikinThermostatMode
    status: DaikinThermostatStatus
    fan_mode: DaikinThermostatFanMode
    fan_speed: DaikinThermostatFanSpeed
    schedule: DaikinThermostatSchedule
    indoor_temperature: Temperature | None
    indoor_humidity: int | None
    set_point_heat: Temperature | None
    set_point_heat_min: Temperature | None
    set_point_heat_max: Temperature | None
    set_point_cool: Temperature | None
    set_point_cool_min: Temperature | None
    set_point_cool_max: Temperature | None
    outdoor_temperature: Temperature | None
    outdoor_humidity: int | None
    air_quality_outdoor: DaikinOneAirQualitySensorOutdoor | None
    air_quality_indoor: DaikinOneAirQualitySensorIndoor | None
    # One Clean: 3-hour full-speed fan cycle to clean the air; None when the
    # payload does not report the feature
    one_clean_fan_active: bool | None
    dual_fuel_furnace_lockout_enable: bool | None
    equipment: dict[str, DaikinEquipment]
    # Away Mode: True when geofencing away setback is active; None when unsupported
    away_mode: bool | None = None
    fan_circulate_start: int | None = None
    fan_circulate_stop: int | None = None
    fan_circulate_duration: DaikinThermostatFanCirculateDuration | None = None
    night_mode_enabled: bool | None = None
    night_mode_active: bool | None = None
    night_mode_start: int | None = None
    night_mode_stop: int | None = None
    night_mode_light_bar_allowed: bool | None = None
    aux_heat_lockout_temp: float | None = None

    num_media_filters: int | None = None
    num_electronic_filters: int | None = None
    num_hepa_filters: int | None = None
    num_uv_bulbs: int | None = None
    ct_humidifier_num_pads: int | None = None
    aux_humidifier_status: bool | None = None
    aux_dehumidifier_status: bool | None = None
    aux_ventilator_status: bool | None = None
    ct_system_cap_ventilation: bool | None = None

    media_air_filter_days: int | None = None
    media_air_filter_days_limit: int | None = None
    media_air_filter_runtime: int | None = None
    media_air_filter_runtime_limit: int | None = None
    media_air_filter_active: bool | None = None
    media_air_filter_date: str | None = None

    service_days: int | None = None
    service_days_limit: int | None = None
    service_active: bool | None = None
    service_date: str | None = None

    hum_pad_days: int | None = None
    hum_pad_days_limit: int | None = None
    hum_pad_runtime: int | None = None
    hum_pad_runtime_limit: int | None = None
    hum_pad_active: bool | None = None
    hum_pad_date: str | None = None

    uv_days: int | None = None
    uv_days_limit: int | None = None
    uv_runtime: int | None = None
    uv_runtime_limit: int | None = None
    uv_active: bool | None = None
    uv_date: str | None = None

    hepa_filter_days: int | None = None
    hepa_filter_days_limit: int | None = None
    hepa_filter_runtime: int | None = None
    hepa_filter_runtime_limit: int | None = None
    hepa_filter_active: bool | None = None
    hepa_filter_date: str | None = None

    electronic_filter_days: int | None = None
    electronic_filter_days_limit: int | None = None
    electronic_filter_runtime: int | None = None
    electronic_filter_runtime_limit: int | None = None
    electronic_filter_active: bool | None = None
    electronic_filter_date: str | None = None

    dehum_filter_days: int | None = None
    dehum_filter_days_limit: int | None = None
    dehum_filter_runtime: int | None = None
    dehum_filter_runtime_limit: int | None = None
    dehum_filter_active: bool | None = None
    dehum_filter_date: str | None = None

    ventilation_days: int | None = None
    ventilation_days_limit: int | None = None
    ventilation_active: bool | None = None
    ventilation_date: str | None = None
    equipment_errors: list[DaikinEquipmentError] | None = None
    system_errors: list[DaikinSystemError] | None = None
    sched_resume_time: datetime | None = None
    sched_override_duration: int | None = None

    @property
    def outdoor(self) -> DaikinOutdoorUnit | None:
        return next(
            (e for e in self.equipment.values() if isinstance(e, DaikinOutdoorUnit)),
            None,
        )

    @property
    def furnace(self) -> DaikinIndoorUnit | None:
        return next(
            (e for e in self.equipment.values() if isinstance(e, DaikinIndoorUnit) and e.name == "Furnace"),
            None,
        )

    @property
    def air_handler(self) -> DaikinIndoorUnit | None:
        return next(
            (e for e in self.equipment.values() if isinstance(e, DaikinIndoorUnit) and e.name == "Air Handler"),
            None,
        )

    @property
    def indoor(self) -> DaikinIndoorUnit | None:
        return (
            self.furnace
            or self.air_handler
            or next(
                (e for e in self.equipment.values() if isinstance(e, DaikinIndoorUnit)),
                None,
            )
        )
