"""Tests for DaikinOne client orchestration, error handling, device caching, and schedule methods."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.climate import ClimateEntityDescription
from homeassistant.components.climate.const import ClimateEntityFeature

from custom_components.daikinone import DOMAIN, DaikinOneData
from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.models import (
    DaikinThermostat,
    DaikinThermostatCapability,
    DaikinThermostatFanCirculateDuration,
    DaikinThermostatFanMode,
    DaikinThermostatFanSpeed,
    DaikinThermostatMode,
    DaikinThermostatSchedule,
    DaikinThermostatStatus,
    DaikinUserCredentials,
)
from custom_components.daikinone.client.wire import DAIKIN_API_URL_DEVICE_DATA, DAIKIN_API_URL_LOCATIONS
from custom_components.daikinone.climate import DaikinOneThermostat
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.select import async_setup_entry as async_setup_select_entry
from custom_components.daikinone.utils import Temperature
from tests.test_mapping import _make_device


@pytest.fixture
def daikin_client() -> DaikinOne:
    creds = DaikinUserCredentials(email="test@example.com", password="password")
    client = DaikinOne(creds)
    client._DaikinOne__thermostats.clear()  # type: ignore[attr-defined]
    return client


def _make_unsupported_device(
    device_id: str = "unsupported_device_1",
    name: str = "Unsupported Sensor",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": device_id,
        "locationId": "loc456",
        "name": name,
        "model": "UNKNOWN_DEVICE",
        "firmware": "1.0.0",
        "online": True,
        "data": data if data is not None else {},
    }


class TestUnsupportedDeviceHandling:
    async def test_valid_thermostat_mapped_and_unsupported_device_skipped(
        self, daikin_client: DaikinOne, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify that a valid thermostat is mapped while an unsupported device (missing required
        keys) is skipped cleanly without aborting the update."""
        valid_dev = _make_device()
        valid_dev["id"] = "valid_tstat"
        valid_dev["name"] = "Living Room Thermostat"

        unsupported_dev = _make_unsupported_device(
            device_id="unsupported_999",
            name="Wireless Sensor",
            data={},
        )

        with (
            caplog.at_level(logging.WARNING),
            patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req,
        ):
            mock_req.return_value = [valid_dev, unsupported_dev]
            await daikin_client.update()

        thermostats = daikin_client.get_thermostats()
        assert "valid_tstat" in thermostats
        assert "unsupported_999" not in thermostats
        assert daikin_client.get_thermostat("valid_tstat").name == "Living Room Thermostat"

        # Verify warning was logged for the unsupported device
        warn_records = [
            r for r in caplog.records if r.levelno == logging.WARNING and "Skipping unsupported device" in r.message
        ]
        assert len(warn_records) == 1
        assert "Wireless Sensor" in warn_records[0].message
        assert "unsupported_999" in warn_records[0].message
        assert "unsupported_999" in daikin_client._unsupported_device_ids

    async def test_update_multiple_times_deduplicates_warning_logging(
        self, daikin_client: DaikinOne, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify that calling update() multiple times only logs the warning once per unsupported device ID."""
        valid_dev = _make_device()
        unsupported_dev = _make_unsupported_device(
            device_id="unsupported_repeat",
            name="Repeated Unsupported",
            data={},
        )

        with (
            caplog.at_level(logging.WARNING),
            patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req,
        ):
            mock_req.return_value = [valid_dev, unsupported_dev]

            # First update - warning should be logged
            await daikin_client.update()

            warn_count_1 = len(
                [
                    r
                    for r in caplog.records
                    if r.levelno == logging.WARNING
                    and "Skipping unsupported device: Repeated Unsupported (unsupported_repeat)" in r.message
                ]
            )
            assert warn_count_1 == 1

            # Second update - warning should NOT be logged again
            await daikin_client.update()

            warn_count_2 = len(
                [
                    r
                    for r in caplog.records
                    if r.levelno == logging.WARNING
                    and "Skipping unsupported device: Repeated Unsupported (unsupported_repeat)" in r.message
                ]
            )
            assert warn_count_2 == 1

            # Third update - still only 1 warning
            await daikin_client.update()

            warn_count_3 = len(
                [
                    r
                    for r in caplog.records
                    if r.levelno == logging.WARNING
                    and "Skipping unsupported device: Repeated Unsupported (unsupported_repeat)" in r.message
                ]
            )
            assert warn_count_3 == 1

        # Valid thermostat remains cached throughout
        assert "device123" in daikin_client.get_thermostats()
        assert "unsupported_repeat" not in daikin_client.get_thermostats()

    @pytest.mark.parametrize("exception_type", [KeyError, ValueError, TypeError])
    async def test_handles_typed_exceptions_from_mapping(
        self,
        daikin_client: DaikinOne,
        caplog: pytest.LogCaptureFixture,
        exception_type: type[Exception],
    ) -> None:
        """Verify that KeyError, ValueError, and TypeError during mapping are handled cleanly."""
        valid_dev = _make_device()

        with (
            caplog.at_level(logging.DEBUG),
            patch(
                "custom_components.daikinone.client.client.map_thermostat",
                side_effect=exception_type("simulated parsing failure"),
            ),
            patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req,
        ):
            mock_req.return_value = [valid_dev]
            await daikin_client.update()

        assert len(daikin_client.get_thermostats()) == 0
        assert "device123" in daikin_client._unsupported_device_ids

        warn_records = [
            r for r in caplog.records if r.levelno == logging.WARNING and "Skipping unsupported device" in r.message
        ]
        assert len(warn_records) == 1
        assert "simulated parsing failure" in warn_records[0].message

        debug_records = [
            r for r in caplog.records if r.levelno == logging.DEBUG and "Failed to map device" in r.message
        ]
        assert len(debug_records) == 1

    async def test_unexpected_exceptions_are_not_swallowed(self, daikin_client: DaikinOne) -> None:
        """Verify that unexpected exceptions (e.g. RuntimeError) are not swallowed by the handler."""
        valid_dev = _make_device()

        with (
            patch(
                "custom_components.daikinone.client.client.map_thermostat",
                side_effect=RuntimeError("unexpected crash"),
            ),
            patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req,
        ):
            mock_req.return_value = [valid_dev]
            with pytest.raises(RuntimeError, match="unexpected crash"):
                await daikin_client.update()

    async def test_set_thermostat_away_mode(self, daikin_client: DaikinOne) -> None:
        """Verify set_thermostat_away_mode sends PUT request with geofencingAway payload."""
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_thermostat_away_mode("device123", True)
            mock_req.assert_called_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/device123",
                method="PUT",
                body={"geofencingAway": True},
            )

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_thermostat_away_mode("device123", False)
            mock_req.assert_called_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/device123",
                method="PUT",
                body={"geofencingAway": False},
            )


class TestOfflineDeviceHandling:
    async def test_offline_device_with_empty_data_marks_cached_thermostat_offline(
        self, daikin_client: DaikinOne, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify that an offline device payload with empty data sets online=False on the cached thermostat."""
        valid_dev = _make_device()
        valid_dev["id"] = "device123"
        valid_dev["name"] = "MainFloor"

        offline_empty_dev = {
            "id": "device123",
            "name": "MainFloor",
            "online": False,
            "data": {},
        }

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            # First poll: device is online with full data
            mock_req.return_value = [valid_dev]
            await daikin_client.update()

            thermostat = daikin_client.get_thermostat("device123")
            assert thermostat.online is True
            assert thermostat.name == "MainFloor"
            assert thermostat.indoor_temperature is not None

            # Second poll: device reports offline with empty data (power cut / outage)
            mock_req.return_value = [offline_empty_dev]
            with caplog.at_level(logging.WARNING):
                await daikin_client.update()

            # Thermostat must remain cached, but with online=False
            updated_thermostat = daikin_client.get_thermostat("device123")
            assert updated_thermostat.online is False
            # Previous attributes (indoor_temperature, equipment, etc.) should be preserved from cache
            assert updated_thermostat.name == "MainFloor"
            assert updated_thermostat.indoor_temperature == thermostat.indoor_temperature

            # Warning should be logged
            assert any(
                "Device MainFloor (device123) reported offline with no data" in r.message for r in caplog.records
            )

    async def test_offline_device_not_previously_cached_does_not_crash(
        self, daikin_client: DaikinOne, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify that an offline device with empty data not previously in cache is skipped cleanly."""
        offline_empty_dev = {
            "id": "unknown_device",
            "name": "Unknown",
            "online": False,
            "data": {},
        }

        with (
            caplog.at_level(logging.WARNING),
            patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req,
        ):
            mock_req.return_value = [offline_empty_dev]
            await daikin_client.update()

        assert "unknown_device" not in daikin_client.get_thermostats()
        assert any("Device Unknown (unknown_device) reported offline with no data" in r.message for r in caplog.records)

    async def test_thermostats_property_returns_cached_thermostats(self, daikin_client: DaikinOne) -> None:
        """Verify thermostats property returns a copy of cached thermostats."""
        valid_dev = _make_device()
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [valid_dev]
            await daikin_client.update()

        assert "device123" in daikin_client.thermostats


class TestClientLocations:
    """Tests for property location fetching, mapping, and caching."""

    async def test_get_locations_fetching_mapping_and_caching(self, daikin_client: DaikinOne) -> None:
        """Verify get_locations requests locations API, maps models, and caches them."""
        raw_locations = [
            {
                "id": "loc-1",
                "name": "homeHA",
                "address": '{"address":"88 Canada Olympic Rd","apt":""}',
                "city": "Calgary",
                "province": "AB",
                "postalCode": "T3B5R5",
                "country": "CA",
                "timeZone": "America/Regina",
                "latitude": 51.087439,
                "longitude": -114.206518,
                "hasOwner": True,
            },
            {
                "id": "loc-2",
                "name": "Cabin",
                "address": "456 Pine Rd",
                "city": "Canmore",
                "province": "AB",
                "postalCode": "T1W 1A1",
                "country": "CA",
                "timeZone": "America/Edmonton",
                "latitude": 51.089,
                "longitude": -115.359,
                "hasOwner": False,
            },
        ]

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = raw_locations
            locations = await daikin_client.get_locations()

        mock_req.assert_awaited_once_with(DAIKIN_API_URL_LOCATIONS)
        assert len(locations) == 2
        assert "loc-1" in locations
        assert "loc-2" in locations
        assert locations["loc-1"].name == "homeHA"
        assert locations["loc-1"].street_address == "88 Canada Olympic Rd"
        assert locations["loc-2"].name == "Cabin"

        # Verify cached property and deepcopy behavior
        assert daikin_client.locations["loc-1"].name == "homeHA"
        locations["loc-1"].name = "Mutated"
        assert daikin_client.locations["loc-1"].name == "homeHA"

    async def test_update_populates_locations_if_empty(self, daikin_client: DaikinOne) -> None:
        """Verify client.update() fetches locations when the internal cache is empty."""
        raw_locations = [
            {
                "id": "loc-1",
                "name": "homeHA",
                "address": "88 Canada Olympic Rd",
            }
        ]
        valid_dev = _make_device()

        async def fake_request(url: str, **kwargs: Any) -> list[dict[str, Any]]:
            if url == DAIKIN_API_URL_LOCATIONS:
                return raw_locations
            return [valid_dev]

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock, side_effect=fake_request):
            await daikin_client.update()

        assert "loc-1" in daikin_client.locations
        assert daikin_client.locations["loc-1"].name == "homeHA"
        assert "device123" in daikin_client.thermostats

    async def test_update_continues_if_locations_fetch_fails(
        self, daikin_client: DaikinOne, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify client.update() logs a warning and proceeds to update devices if locations request fails."""
        valid_dev = _make_device()

        async def fake_request(url: str, **kwargs: Any) -> list[dict[str, Any]]:
            if url == DAIKIN_API_URL_LOCATIONS:
                raise RuntimeError("Cloud location service unavailable")
            return [valid_dev]

        with (
            caplog.at_level(logging.WARNING),
            patch.object(daikin_client._transport, "request", new_callable=AsyncMock, side_effect=fake_request),
        ):
            await daikin_client.update()

        assert "device123" in daikin_client.thermostats
        assert any("Failed to fetch locations" in r.message for r in caplog.records)


@pytest.mark.parametrize(
    ("method", "value", "key"),
    [
        ("set_thermostat_fan_circulate_start", 12, "fanCirculateStart"),
        ("set_thermostat_fan_circulate_stop", 84, "fanCirculateStop"),
        ("set_thermostat_fan_circulate_duration", DaikinThermostatFanCirculateDuration.MIN_15, "fanCirculateDuration"),
        ("set_thermostat_night_mode", True, "nightModeEnabled"),
        ("set_thermostat_night_mode_start", 88, "nightModeStart"),
        ("set_thermostat_night_mode_stop", 28, "nightModeStop"),
    ],
)
async def test_schedule_api_writes(method: str, value: object, key: str) -> None:
    client = object.__new__(DaikinOne)
    client._transport = SimpleNamespace(request=AsyncMock())
    if method == "set_thermostat_fan_circulate_duration":
        expected_value = DaikinThermostatFanCirculateDuration.MIN_15.value
    else:
        expected_value = value

    await getattr(client, method)("thermostat-id", value)

    client._transport.request.assert_awaited_once_with(
        url=f"{DAIKIN_API_URL_DEVICE_DATA}/thermostat-id",
        method="PUT",
        body={key: expected_value},
    )


class TestClientScheduleMethods:
    """Tests for DaikinOne schedule client methods."""

    async def test_set_thermostat_schedule_atomic_put_and_optimistic_cache(self, daikin_client: DaikinOne) -> None:
        """Verify set_thermostat_schedule sends a single atomic PUT and updates cached thermostat schedule."""
        valid_dev = _make_device(
            {
                "schedMonPart1Time": 24,
                "schedMonPart1Enabled": True,
                "schedMonPart1hsp": 20.0,
                "schedMonPart1csp": 24.0,
                "schedMonPart1Label": "wake",
            }
        )
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [valid_dev]
            await daikin_client.update()

        batch_payload = {
            "schedEnabled": True,
            "schedOverride": 0,
            "schedMonPart1Time": 26,
            "schedMonPart1Enabled": True,
            "schedMonPart1hsp": 21.0,
            "schedMonPart1csp": 25.0,
            "schedMonPart1Label": "morning",
            "schedTuePart1Time": 28,
            "schedTuePart1Enabled": True,
            "schedTuePart1hsp": 19.5,
            "schedTuePart1csp": 24.0,
            "schedTuePart1Label": "work",
        }

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_put:
            await daikin_client.set_thermostat_schedule("device123", batch_payload)
            mock_put.assert_called_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/device123",
                method="PUT",
                body=batch_payload,
            )

        # Verify optimistic update in client RAM cache
        cached = daikin_client.get_thermostat("device123")
        assert cached.schedule.days is not None
        mon_p1 = cached.schedule.days["mon"].periods[1]
        assert mon_p1.start_slot == 26
        assert mon_p1.start_time_str == "06:30"
        assert mon_p1.heat_setpoint.celsius == 21.0
        assert mon_p1.cool_setpoint.celsius == 25.0
        assert mon_p1.label == "morning"

        tue_p1 = cached.schedule.days["tue"].periods[1]
        assert tue_p1.start_slot == 28
        assert tue_p1.start_time_str == "07:00"
        assert tue_p1.heat_setpoint.celsius == 19.5
        assert tue_p1.cool_setpoint.celsius == 24.0
        assert tue_p1.label == "work"

    async def test_set_thermostat_schedule_empty_payload_raises(self, daikin_client: DaikinOne) -> None:
        """Verify set_thermostat_schedule rejects an empty dictionary."""
        with pytest.raises(ValueError, match="Schedule payload must not be empty"):
            await daikin_client.set_thermostat_schedule("device123", {})


@pytest.mark.parametrize(
    ("method", "value", "key", "expected_value"),
    [
        ("set_thermostat_quiet_mode_enabled", True, "ctOutdoorQuietModeEnabled", 1),
        ("set_thermostat_quiet_mode_enabled", False, "ctOutdoorQuietModeEnabled", 0),
        ("set_thermostat_quiet_mode_start_time", 88, "quietModeStartTime", 88),
        ("set_thermostat_quiet_mode_stop_time", 28, "quietModeStopTime", 28),
    ],
)
async def test_quiet_mode_api_writes(method: str, value: object, key: str, expected_value: object) -> None:
    client = object.__new__(DaikinOne)
    client._transport = SimpleNamespace(request=AsyncMock())

    await getattr(client, method)("thermostat-id", value)

    client._transport.request.assert_awaited_once_with(
        url=f"{DAIKIN_API_URL_DEVICE_DATA}/thermostat-id",
        method="PUT",
        body={key: expected_value},
    )


async def test_quiet_mode_optimistic_cache_mutation() -> None:
    client = object.__new__(DaikinOne)
    client._transport = SimpleNamespace(request=AsyncMock())
    thermostat = SimpleNamespace(
        id="dev1",
        quiet_mode_enabled=False,
        quiet_mode_start_time=0,
        quiet_mode_stop_time=0,
    )
    client._DaikinOne__thermostats = {"dev1": thermostat}

    await client.set_thermostat_quiet_mode_enabled("dev1", True)
    assert thermostat.quiet_mode_enabled is True

    await client.set_thermostat_quiet_mode_start_time("dev1", 88)
    assert thermostat.quiet_mode_start_time == 88

    await client.set_thermostat_quiet_mode_stop_time("dev1", 28)
    assert thermostat.quiet_mode_stop_time == 28


def _create_thermostat(
    thermostat_id: str,
    name: str = "Test Stat",
    model: str = "ONEPLUS",
    is_one_lite: bool = False,
    set_point_heat: Temperature | None = None,
    set_point_cool: Temperature | None = None,
) -> DaikinThermostat:
    return DaikinThermostat(
        id=thermostat_id,
        location_id="loc123",
        name=name,
        model=model,
        firmware_version="1.0.0",
        online=True,
        capabilities={DaikinThermostatCapability.HEAT, DaikinThermostatCapability.COOL},
        mode=DaikinThermostatMode.HEAT,
        status=DaikinThermostatStatus.IDLE,
        fan_mode=DaikinThermostatFanMode.OFF,
        fan_speed=DaikinThermostatFanSpeed.LOW,
        schedule=DaikinThermostatSchedule(enabled=True),
        indoor_temperature=Temperature.from_celsius(21.0),
        indoor_humidity=45,
        set_point_heat=set_point_heat or Temperature.from_celsius(20.0),
        set_point_heat_min=Temperature.from_celsius(10.0),
        set_point_heat_max=Temperature.from_celsius(30.0),
        set_point_cool=set_point_cool or Temperature.from_celsius(24.0),
        set_point_cool_min=Temperature.from_celsius(18.0),
        set_point_cool_max=Temperature.from_celsius(32.0),
        outdoor_temperature=Temperature.from_celsius(15.0),
        outdoor_humidity=50,
        air_quality_outdoor=None,
        air_quality_indoor=None,
        equipment={},
        is_one_lite=is_one_lite,
    )


class TestOneLiteClientWritePaths:
    async def test_set_temperature_dispatches_heatsp_and_coolsp_for_one_lite(self, daikin_client: DaikinOne) -> None:
        tstat = _create_thermostat("onelite_1", model="ONELITE_24V", is_one_lite=True)
        daikin_client._DaikinOne__thermostats["onelite_1"] = tstat  # type: ignore[attr-defined]

        heat = Temperature.from_celsius(21.5)
        cool = Temperature.from_celsius(25.0)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_temperature("onelite_1", heat=heat, cool=cool)

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/onelite_1",
                method="PUT",
                body={"heatSP": 21.5, "coolSP": 25.0},
            )

        cached = daikin_client.get_thermostat("onelite_1")
        assert cached.set_point_heat == heat
        assert cached.set_point_cool == cool

    async def test_set_temperature_dispatches_hspactive_and_cspactive_for_one_plus(
        self, daikin_client: DaikinOne
    ) -> None:
        tstat = _create_thermostat("oneplus_1", model="ONEPLUS", is_one_lite=False)
        daikin_client._DaikinOne__thermostats["oneplus_1"] = tstat  # type: ignore[attr-defined]

        heat = Temperature.from_celsius(22.0)
        cool = Temperature.from_celsius(26.0)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_temperature("oneplus_1", heat=heat, cool=cool)

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/oneplus_1",
                method="PUT",
                body={"hspActive": 22.0, "cspActive": 26.0},
            )

        cached = daikin_client.get_thermostat("oneplus_1")
        assert cached.set_point_heat == heat
        assert cached.set_point_cool == cool

    async def test_set_thermostat_home_set_points_dispatches_heatsp_and_coolsp_for_one_lite(
        self, daikin_client: DaikinOne
    ) -> None:
        tstat = _create_thermostat("onelite_1", model="ONELITE_24V", is_one_lite=True)
        daikin_client._DaikinOne__thermostats["onelite_1"] = tstat  # type: ignore[attr-defined]

        heat = Temperature.from_celsius(19.0)
        cool = Temperature.from_celsius(23.0)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_thermostat_home_set_points(
                "onelite_1", heat=heat, cool=cool, override_schedule=True
            )

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/onelite_1",
                method="PUT",
                body={"heatSP": 19.0, "coolSP": 23.0},
            )

        cached = daikin_client.get_thermostat("onelite_1")
        assert cached.set_point_heat == heat
        assert cached.set_point_cool == cool

    async def test_set_thermostat_home_set_points_dispatches_hsphome_and_csphome_for_one_plus(
        self, daikin_client: DaikinOne
    ) -> None:
        tstat = _create_thermostat("oneplus_1", model="ONEPLUS", is_one_lite=False)
        daikin_client._DaikinOne__thermostats["oneplus_1"] = tstat  # type: ignore[attr-defined]

        heat = Temperature.from_celsius(20.0)
        cool = Temperature.from_celsius(24.0)

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_thermostat_home_set_points(
                "oneplus_1", heat=heat, cool=cool, override_schedule=True
            )

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/oneplus_1",
                method="PUT",
                body={"hspHome": 20.0, "cspHome": 24.0, "schedOverride": 1},
            )

        cached = daikin_client.get_thermostat("oneplus_1")
        assert cached.set_point_heat == heat
        assert cached.set_point_cool == cool

    async def test_set_thermostat_home_set_points_raises_value_error_if_no_temperatures(
        self, daikin_client: DaikinOne
    ) -> None:
        with pytest.raises(ValueError, match="At least one of heat or cool set points must be set"):
            await daikin_client.set_thermostat_home_set_points("some_id", heat=None, cool=None)

    async def test_set_away_dispatches_away_for_one_lite(self, daikin_client: DaikinOne) -> None:
        tstat = _create_thermostat("onelite_1", model="ONELITE_24V", is_one_lite=True)
        daikin_client._DaikinOne__thermostats["onelite_1"] = tstat  # type: ignore[attr-defined]

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_away("onelite_1", away=True)

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/onelite_1",
                method="PUT",
                body={"away": True},
            )

    async def test_set_away_dispatches_geofencing_away_for_one_plus(self, daikin_client: DaikinOne) -> None:
        tstat = _create_thermostat("oneplus_1", model="ONEPLUS", is_one_lite=False)
        daikin_client._DaikinOne__thermostats["oneplus_1"] = tstat  # type: ignore[attr-defined]

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_away("oneplus_1", away=False)

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/oneplus_1",
                method="PUT",
                body={"geofencingAway": False},
            )


class TestOneLitePlatformIntegrations:
    def test_climate_entity_omits_fan_mode_for_one_lite(self, daikin_client: DaikinOne) -> None:
        tstat = _create_thermostat("onelite_1", model="ONELITE_24V", is_one_lite=True)
        entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
        data = DaikinOneData(_hass=None, entry=entry, daikin=daikin_client)  # type: ignore[arg-type]

        entity = DaikinOneThermostat(
            description=ClimateEntityDescription(key="onelite_1", has_entity_name=True),
            data=data,
            thermostat=tstat,
        )

        assert not (entity.supported_features & ClimateEntityFeature.FAN_MODE)
        assert entity.fan_modes == []

    async def test_climate_entity_set_fan_mode_raises_for_one_lite(self, daikin_client: DaikinOne) -> None:
        tstat = _create_thermostat("onelite_1", model="ONELITE_24V", is_one_lite=True)
        entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
        data = DaikinOneData(_hass=None, entry=entry, daikin=daikin_client)  # type: ignore[arg-type]

        entity = DaikinOneThermostat(
            description=ClimateEntityDescription(key="onelite_1", has_entity_name=True),
            data=data,
            thermostat=tstat,
        )

        with pytest.raises(NotImplementedError, match="Fan mode control is not supported on Daikin One Lite"):
            await entity.async_set_fan_mode("always_on")

    async def test_select_platform_skips_one_lite(self, daikin_client: DaikinOne) -> None:
        tstat = _create_thermostat("onelite_1", model="ONELITE_24V", is_one_lite=True)
        daikin_client._DaikinOne__thermostats["onelite_1"] = tstat  # type: ignore[attr-defined]

        added_entities: list[Any] = []
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.data = {CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1}
        mock_hass.data = {DOMAIN: DaikinOneData(_hass=mock_hass, entry=mock_entry, daikin=daikin_client)}

        await async_setup_select_entry(
            mock_hass,
            mock_entry,
            lambda entities, update_before_add=False: added_entities.extend(entities),
        )
        assert len(added_entities) == 0
