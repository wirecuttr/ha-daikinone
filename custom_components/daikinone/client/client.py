"""DaikinOne orchestration: holds transport + thermostat cache, exposes the public API."""

import copy
import logging
from typing import Any

from custom_components.daikinone.client.mapping import map_location, map_thermostat
from custom_components.daikinone.client.models import (
    DAIKIN_DAY_PREFIXES,
    SCHEDULE_PARTS,
    DaikinDaySchedule,
    DaikinLocation,
    DaikinSchedulePeriod,
    DaikinThermostat,
    DaikinThermostatFanCirculateDuration,
    DaikinThermostatFanMode,
    DaikinThermostatFanSpeed,
    DaikinThermostatMode,
    DaikinUserCredentials,
)
from custom_components.daikinone.client.transport import DaikinTransport
from custom_components.daikinone.client.wire import (
    DAIKIN_API_URL_DEVICE_DATA,
    DAIKIN_API_URL_LOCATIONS,
    DaikinDeviceDataResponse,
    DaikinLocationResponse,
)
from custom_components.daikinone.utils import Temperature

log = logging.getLogger(__name__)


class DaikinOne:
    """Manages connection to Daikin API and fetching device data."""

    __thermostats: dict[str, DaikinThermostat] = {}  # noqa: RUF012
    __locations: dict[str, DaikinLocation] = {}  # noqa: RUF012

    def __init__(self, creds: DaikinUserCredentials) -> None:
        self._transport = DaikinTransport(creds)
        self._unsupported_device_ids: set[str] = set()
        self.__locations: dict[str, DaikinLocation] = {}
        self.__thermostats: dict[str, DaikinThermostat] = {}

    async def login(self) -> bool:
        return await self._transport.login()

    async def get_locations(self) -> dict[str, DaikinLocation]:
        """Fetch and cache property locations from Daikin Skyport."""
        raw = await self._transport.request(DAIKIN_API_URL_LOCATIONS)
        locations: dict[str, DaikinLocation] = {}
        for item in raw:
            loc = map_location(DaikinLocationResponse(**item))
            locations[loc.id] = loc
        self.__locations = locations
        return copy.deepcopy(self.__locations)

    @property
    def locations(self) -> dict[str, DaikinLocation]:
        """Return cached locations."""
        return copy.deepcopy(self.__locations)

    async def get_all_raw_device_data(self) -> list[dict[str, Any]]:
        """Get raw device data"""
        return await self._transport.request(DAIKIN_API_URL_DEVICE_DATA)

    async def get_raw_device_data(self, device_id: str) -> dict[str, Any]:
        """Get raw device data"""
        return await self._transport.request(f"{DAIKIN_API_URL_DEVICE_DATA}/{device_id}")

    async def update(self) -> None:
        if not self.__locations:
            try:
                await self.get_locations()
            except Exception as err:  # noqa: BLE001
                log.warning("Failed to fetch locations: %s", err)

        raw = await self._transport.request(DAIKIN_API_URL_DEVICE_DATA)
        responses = [DaikinDeviceDataResponse(**d) for d in raw]

        for r in responses:
            if not r.online and len(r.data) == 0:
                if r.id in self.__thermostats:
                    self.__thermostats[r.id].online = False
                log.warning("Device %s (%s) reported offline with no data", r.name, r.id)
                continue
            try:
                self.__thermostats[r.id] = map_thermostat(r)
            except (KeyError, ValueError, TypeError) as err:
                if r.id not in self._unsupported_device_ids:
                    self._unsupported_device_ids.add(r.id)
                    log.warning(
                        "Skipping unsupported device: %s (%s) - %s",
                        r.name,
                        r.id,
                        err,
                    )
                log.debug("Failed to map device %s (%s)", r.name, r.id, exc_info=True)
                continue

        log.info(f"Cached {len(self.__thermostats)} thermostats")

    def get_thermostat(self, thermostat_id: str) -> DaikinThermostat:
        return copy.deepcopy(self.__thermostats[thermostat_id])

    def get_thermostats(self) -> dict[str, DaikinThermostat]:
        return copy.deepcopy(self.__thermostats)

    @property
    def thermostats(self) -> dict[str, DaikinThermostat]:
        """Return cached thermostats."""
        return self.get_thermostats()

    async def set_thermostat_mode(self, thermostat_id: str, mode: DaikinThermostatMode) -> None:
        """Set thermostat mode"""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"mode": mode.value},
        )

    async def set_thermostat_home_set_points(
        self,
        thermostat_id: str,
        heat: Temperature | None = None,
        cool: Temperature | None = None,
        override_schedule: bool = False,
    ) -> None:
        """Set thermostat home set points"""
        if not heat and not cool:
            raise ValueError("At least one of heat or cool set points must be set")

        payload: dict[str, Any] = {}
        if heat:
            payload["hspHome"] = heat.celsius
        if cool:
            payload["cspHome"] = cool.celsius
        if override_schedule:
            payload["schedOverride"] = 1

        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body=payload,
        )

    async def set_thermostat_fan_mode(self, thermostat_id: str, fan_mode: DaikinThermostatFanMode) -> None:
        """Set thermostat fan mode"""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"fanCirculate": fan_mode.value},
        )

    async def set_thermostat_fan_speed(self, thermostat_id: str, fan_speed: DaikinThermostatFanSpeed) -> None:
        """Set thermostat fan speed"""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"fanCirculateSpeed": fan_speed.value},
        )

    async def set_thermostat_schedule_enabled(self, thermostat_id: str, enabled: bool) -> None:
        """Enable or disable thermostat schedule"""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"schedEnabled": enabled, "schedOverride": 0},
        )

    async def resume_thermostat_schedule(self, thermostat_id: str) -> None:
        """Resume scheduled set points by clearing schedule override and ensuring schedule is enabled"""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"schedOverride": 0, "schedEnabled": True},
        )

    async def set_one_clean_fan_active(self, thermostat_id: str, active: bool) -> None:
        """Start or stop the One Clean fan cycle"""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"oneCleanFanActive": active},
        )

    async def set_thermostat_away_mode(self, thermostat_id: str, away: bool) -> None:
        """Set thermostat geofencing away mode."""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"geofencingAway": away},
        )

    async def set_dual_fuel_furnace_lockout_enable(self, thermostat_id: str, enabled: bool) -> None:
        """Enable or disable dual-fuel furnace lockout (prioritize efficiency)."""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"ctDualFuelFurnaceLockoutEnable": enabled},
        )

    async def set_thermostat_fan_circulate_start(self, thermostat_id: str, start: int) -> None:
        """Set fan circulation schedule start time slot (0-95)."""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"fanCirculateStart": start},
        )

    async def set_thermostat_fan_circulate_stop(self, thermostat_id: str, stop: int) -> None:
        """Set fan circulation schedule stop time slot (0-95)."""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"fanCirculateStop": stop},
        )

    async def set_thermostat_fan_circulate_duration(
        self, thermostat_id: str, duration: DaikinThermostatFanCirculateDuration
    ) -> None:
        """Set fan circulation duty cycle duration."""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"fanCirculateDuration": duration.value},
        )

    async def set_thermostat_night_mode(self, thermostat_id: str, enabled: bool) -> None:
        """Enable or disable thermostat night mode."""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"nightModeEnabled": enabled},
        )

    async def set_thermostat_night_mode_start(self, thermostat_id: str, start: int) -> None:
        """Set thermostat night mode start time slot (0-95)."""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"nightModeStart": start},
        )

    async def set_thermostat_night_mode_stop(self, thermostat_id: str, stop: int) -> None:
        """Set thermostat night mode stop time slot (0-95)."""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"nightModeStop": stop},
        )

    async def set_thermostat_aux_heat_lockout_temp(self, thermostat_id: str, temp: float) -> None:
        """Set auxiliary heat lockout balance point temperature."""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"auxHeatLockoutTemp": temp},
        )

    async def set_thermostat_schedule(self, thermostat_id: str, payload: dict[str, Any]) -> None:
        """Send an atomic batch PUT request to update thermostat schedule keys and update cache."""
        if not payload:
            raise ValueError("Schedule payload must not be empty")

        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body=payload,
        )

        # Optimistically apply the modified wire keys to the in-memory cached thermostat
        self._apply_optimistic_schedule_payload(thermostat_id, payload)

    def _apply_optimistic_schedule_payload(self, thermostat_id: str, payload: dict[str, Any]) -> None:
        """Update the cached DaikinThermostat.schedule in place from a wire key payload."""
        thermostat = self.__thermostats.get(thermostat_id)
        if thermostat is None:
            return

        if "schedEnabled" in payload:
            thermostat.schedule.enabled = bool(payload["schedEnabled"])
        if "schedOverride" in payload:
            thermostat.schedule.override = bool(payload["schedOverride"])

        if thermostat.schedule.days is None:
            thermostat.schedule.days = {}

        for day_key, day_prefix in DAIKIN_DAY_PREFIXES.items():
            for part in SCHEDULE_PARTS:
                prefix = f"sched{day_prefix}Part{part}"
                time_key = f"{prefix}Time"
                enabled_key = f"{prefix}Enabled"
                hsp_key = f"{prefix}hsp"
                csp_key = f"{prefix}csp"
                label_key = f"{prefix}Label"
                action_key = f"{prefix}Action"

                if not any(k in payload for k in (time_key, enabled_key, hsp_key, csp_key, label_key, action_key)):
                    continue

                day_sched = thermostat.schedule.days.get(day_key)
                if day_sched is None:
                    day_sched = DaikinDaySchedule(day=day_key, periods={})
                    thermostat.schedule.days[day_key] = day_sched

                existing = day_sched.periods.get(part)
                new_slot = int(payload[time_key]) if time_key in payload else (existing.start_slot if existing else 0)
                new_enabled = (
                    bool(payload[enabled_key]) if enabled_key in payload else (existing.enabled if existing else False)
                )
                new_hsp = (
                    Temperature.from_celsius(float(payload[hsp_key]))
                    if hsp_key in payload
                    else (existing.heat_setpoint if existing else Temperature.from_celsius(20.0))
                )
                new_csp = (
                    Temperature.from_celsius(float(payload[csp_key]))
                    if csp_key in payload
                    else (existing.cool_setpoint if existing else Temperature.from_celsius(24.0))
                )
                new_label = (
                    str(payload[label_key]).strip() if label_key in payload else (existing.label if existing else "")
                )
                new_action = int(payload[action_key]) if action_key in payload else (existing.action if existing else 0)

                day_sched.periods[part] = DaikinSchedulePeriod(
                    part=part,
                    enabled=new_enabled,
                    start_slot=new_slot,
                    heat_setpoint=new_hsp,
                    cool_setpoint=new_csp,
                    label=new_label,
                    action=new_action,
                )

    async def set_thermostat_quiet_mode_enabled(self, thermostat_id: str, enabled: bool) -> None:
        """Set outdoor unit inverter quiet mode state."""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"ctOutdoorQuietModeEnabled": 1 if enabled else 0},
        )
        if thermostat_id in self.__thermostats:
            self.__thermostats[thermostat_id].quiet_mode_enabled = enabled

    async def set_thermostat_quiet_mode_start_time(self, thermostat_id: str, slot: int) -> None:
        """Set outdoor unit inverter quiet mode start time slot (0-95)."""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"quietModeStartTime": slot},
        )
        if thermostat_id in self.__thermostats:
            self.__thermostats[thermostat_id].quiet_mode_start_time = slot

    async def set_thermostat_quiet_mode_stop_time(self, thermostat_id: str, slot: int) -> None:
        """Set outdoor unit inverter quiet mode stop time slot (0-95)."""
        await self._transport.request(
            url=f"{DAIKIN_API_URL_DEVICE_DATA}/{thermostat_id}",
            method="PUT",
            body={"quietModeStopTime": slot},
        )
        if thermostat_id in self.__thermostats:
            self.__thermostats[thermostat_id].quiet_mode_stop_time = slot
