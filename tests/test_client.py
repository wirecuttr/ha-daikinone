"""Tests for DaikinOne client."""

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.models import DaikinUserCredentials
from custom_components.daikinone.client.wire import DAIKIN_API_URL_DEVICE_DATA


@pytest.fixture
def daikin_client() -> DaikinOne:
    creds = DaikinUserCredentials(email="test@example.com", password="password")
    client = DaikinOne(creds)
    client._DaikinOne__thermostats.clear()  # type: ignore[attr-defined]
    return client


class TestDaikinClientAwayMode:
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
