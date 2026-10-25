"""Tests for DaikinOne client calibration offset methods."""

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.models import DaikinUserCredentials
from custom_components.daikinone.client.wire import DAIKIN_API_URL_DEVICE_DATA
from tests.test_mapping import _make_device


@pytest.fixture
def daikin_client() -> DaikinOne:
    creds = DaikinUserCredentials(email="test@example.com", password="password")
    client = DaikinOne(creds)
    client._DaikinOne__thermostats.clear()  # type: ignore[attr-defined]
    return client


class TestCalibrationOffsetClientMethods:
    async def test_set_temperature_offset(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"]["tempOffset"] = 0.0

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        tstat = daikin_client.get_thermostats()["device123"]
        assert tstat.temp_offset == 0.0

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_temperature_offset("device123", -1.5)

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/device123",
                method="PUT",
                body={"tempOffset": -1.5},
            )

        # In-memory cache is mutated optimistically
        updated = daikin_client.get_thermostat("device123")
        assert updated.temp_offset == -1.5

    async def test_set_humidity_offset(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"]["humOffset"] = 0

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        tstat = daikin_client.get_thermostats()["device123"]
        assert tstat.hum_offset == 0

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_humidity_offset("device123", -3)

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/device123",
                method="PUT",
                body={"humOffset": -3},
            )

        # In-memory cache is mutated optimistically
        updated = daikin_client.get_thermostat("device123")
        assert updated.hum_offset == -3

    async def test_set_thermostat_temperature_offset_alias(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"]["tempOffset"] = 0.0

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_thermostat_temperature_offset("device123", 2.0)

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/device123",
                method="PUT",
                body={"tempOffset": 2.0},
            )

        assert daikin_client.get_thermostat("device123").temp_offset == 2.0

    async def test_set_thermostat_humidity_offset_alias(self, daikin_client: DaikinOne) -> None:
        device_data = _make_device()
        device_data["data"]["humOffset"] = 0

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            await daikin_client.set_thermostat_humidity_offset("device123", 5)

            mock_req.assert_awaited_once_with(
                url=f"{DAIKIN_API_URL_DEVICE_DATA}/device123",
                method="PUT",
                body={"humOffset": 5},
            )

        assert daikin_client.get_thermostat("device123").hum_offset == 5
