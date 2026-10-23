"""Tests for DaikinOne client orchestration, error handling, and device caching."""

import logging
from typing import Any
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

import pytest

from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.models import DaikinThermostatFanCirculateDuration, DaikinUserCredentials
from custom_components.daikinone.client.wire import DAIKIN_API_URL_DEVICE_DATA
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
