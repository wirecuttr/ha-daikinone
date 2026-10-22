"""Domain models exposed by the Daikin client to the rest of the integration."""

from datetime import timedelta
from enum import Enum, StrEnum, auto

from pydantic.dataclasses import dataclass

from custom_components.daikinone.utils import Temperature


@dataclass
class DaikinUserCredentials:
    email: str
    password: str


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
    def _missing_(cls, value: object) -> "DaikinOutdoorUnitReversingValveStatus":
        return cls.UNKNOWN


class DaikinOutdoorUnitHeaterStatus(Enum):
    OFF = 0
    ON = 1
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> "DaikinOutdoorUnitHeaterStatus":
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
    def _missing_(cls, value: object) -> "DaikinOneAirQualitySensorSummaryLevel":
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
    def _missing_(cls, value: object) -> "DaikinThermostatMode":
        return cls.UNKNOWN


class DaikinThermostatStatus(Enum):
    COOLING = 1
    DRYING = 2
    HEATING = 3
    CIRCULATING_AIR = 4
    IDLE = 5
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> "DaikinThermostatStatus":
        return cls.UNKNOWN


class DaikinOperatingState(StrEnum):
    IDLE = "idle"
    HEATING_STARTUP = "heating_startup"
    HEATING = "heating"
    HEAT_PUMP_HEATING = "heat_pump_heating"
    GAS_HEATING = "gas_heating"
    ELECTRIC_HEATING = "electric_heating"
    EMERGENCY_HEATING = "emergency_heating"
    COOLING = "cooling"
    DRYING = "drying"
    DEFROST = "defrost"
    FAN_ONLY = "fan_only"
    OFF = "off"


@dataclass
class DaikinThermostatSchedule:
    enabled: bool
    override: bool = False


class DaikinThermostatFanMode(Enum):
    OFF = 0
    ALWAYS_ON = 1
    SCHEDULED = 2
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> "DaikinThermostatFanMode":
        return cls.UNKNOWN


class DaikinThermostatFanSpeed(Enum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> "DaikinThermostatFanSpeed":
        return cls.UNKNOWN


class DaikinThermostatFanCirculateDuration(Enum):
    CONTINUOUS = 0
    MIN_5 = 1
    MIN_15 = 2
    MIN_30 = 3
    MIN_45 = 4
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> "DaikinThermostatFanCirculateDuration":
        return cls.UNKNOWN


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
    aux_heat_lockout_temp: float | None = None
    night_mode_enabled: bool | None = None
    night_mode_active: bool | None = None
    night_mode_start: int | None = None
    night_mode_stop: int | None = None
    night_mode_light_bar_allowed: bool | None = None

    # Consumables & Maintenance Hardware Inventory Counters
    num_media_filters: int | None = None
    num_electronic_filters: int | None = None
    num_hepa_filters: int | None = None
    num_uv_bulbs: int | None = None
    ct_humidifier_num_pads: int | None = None
    aux_humidifier_status: bool | None = None
    aux_dehumidifier_status: bool | None = None
    aux_ventilator_status: bool | None = None
    ct_system_cap_ventilation: bool | None = None

    # Media Air Filter Reminders
    media_air_filter_days: int | None = None
    media_air_filter_days_limit: int | None = None
    media_air_filter_runtime: int | None = None
    media_air_filter_runtime_limit: int | None = None
    media_air_filter_active: bool | None = None
    media_air_filter_date: str | None = None

    # Service Inspection Reminders
    service_days: int | None = None
    service_days_limit: int | None = None
    service_active: bool | None = None
    service_date: str | None = None

    # Humidifier Pad Reminders
    hum_pad_days: int | None = None
    hum_pad_days_limit: int | None = None
    hum_pad_runtime: int | None = None
    hum_pad_runtime_limit: int | None = None
    hum_pad_active: bool | None = None
    hum_pad_date: str | None = None

    # UV Disinfection Lamp Reminders
    uv_days: int | None = None
    uv_days_limit: int | None = None
    uv_runtime: int | None = None
    uv_runtime_limit: int | None = None
    uv_active: bool | None = None
    uv_date: str | None = None

    # HEPA Air Filter Reminders
    hepa_filter_days: int | None = None
    hepa_filter_days_limit: int | None = None
    hepa_filter_runtime: int | None = None
    hepa_filter_runtime_limit: int | None = None
    hepa_filter_active: bool | None = None
    hepa_filter_date: str | None = None

    # Electronic Air Filter Reminders
    electronic_filter_days: int | None = None
    electronic_filter_days_limit: int | None = None
    electronic_filter_runtime: int | None = None
    electronic_filter_runtime_limit: int | None = None
    electronic_filter_active: bool | None = None
    electronic_filter_date: str | None = None

    # Dehumidifier Filter Reminders
    dehum_filter_days: int | None = None
    dehum_filter_days_limit: int | None = None
    dehum_filter_runtime: int | None = None
    dehum_filter_runtime_limit: int | None = None
    dehum_filter_active: bool | None = None
    dehum_filter_date: str | None = None

    # Ventilator Core Reminders
    ventilation_days: int | None = None
    ventilation_days_limit: int | None = None
    ventilation_active: bool | None = None
    ventilation_date: str | None = None
