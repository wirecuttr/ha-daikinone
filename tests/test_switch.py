from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikinone import DOMAIN, DaikinOneData
from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.models import DaikinUserCredentials
from custom_components.daikinone.client.wire import DAIKIN_API_URL_DEVICE_DATA
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.switch import DaikinOneAwayModeSwitch, async_setup_entry
from tests.test_mapping import _make_device


@pytest.fixture
def daikin_client() -> DaikinOne:
    creds = DaikinUserCredentials(email="test@example.com", password="password")
    client = DaikinOne(creds)
    client._DaikinOne__thermostats.clear()  # type: ignore[attr-defined]
    return client


@pytest.fixture
def data_v1(daikin_client: DaikinOne) -> DaikinOneData:
    entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
    return DaikinOneData(_hass=None, entry=entry, daikin=daikin_client)  # type: ignore[arg-type]


@pytest.fixture
def data_v0(daikin_client: DaikinOne) -> DaikinOneData:
    entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 0})
    return DaikinOneData(_hass=None, entry=entry, daikin=daikin_client)  # type: ignore[arg-type]


class TestAwayModeSwitchSetup:
    async def test_entity_created_when_away_mode_true(self, daikin_client: DaikinOne, data_v1: DaikinOneData) -> None:
        device_data = _make_device({"geofencingAway": True})
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        hass = MagicMock()
        hass.data = {DOMAIN: data_v1}
        entities: list[DaikinOneAwayModeSwitch] = []

        await async_setup_entry(hass, data_v1.entry, lambda ents, _: entities.extend(ents))  # type: ignore[arg-type]

        assert len(entities) == 1
        switch = entities[0]
        assert isinstance(switch, DaikinOneAwayModeSwitch)
        assert switch.is_on is True
        assert switch.name == "Away Mode"
        assert switch.device_name == "Test Thermostat Thermostat"

    async def test_entity_created_when_away_mode_false(self, daikin_client: DaikinOne, data_v1: DaikinOneData) -> None:
        device_data = _make_device({"geofencingAway": False})
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        hass = MagicMock()
        hass.data = {DOMAIN: data_v1}
        entities: list[DaikinOneAwayModeSwitch] = []

        await async_setup_entry(hass, data_v1.entry, lambda ents, _: entities.extend(ents))  # type: ignore[arg-type]

        assert len(entities) == 1
        assert entities[0].is_on is False

    async def test_entity_skipped_when_away_mode_none(self, daikin_client: DaikinOne, data_v1: DaikinOneData) -> None:
        device_data = _make_device()
        assert "geofencingAway" not in device_data["data"]

        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostats()["device123"]
        assert thermostat.away_mode is None

        hass = MagicMock()
        hass.data = {DOMAIN: data_v1}
        entities: list[DaikinOneAwayModeSwitch] = []

        await async_setup_entry(hass, data_v1.entry, lambda ents, _: entities.extend(ents))  # type: ignore[arg-type]

        assert len(entities) == 0


class TestAwayModeSwitchUniqueId:
    async def test_unique_id_schema_v0(self, daikin_client: DaikinOne, data_v0: DaikinOneData) -> None:
        device_data = _make_device({"geofencingAway": False})
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostat("device123")
        switch = DaikinOneAwayModeSwitch(data=data_v0, thermostat=thermostat)
        assert switch.unique_id == "device123-away_mode"

    async def test_unique_id_schema_v1(self, daikin_client: DaikinOne, data_v1: DaikinOneData) -> None:
        device_data = _make_device({"geofencingAway": False})
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostat("device123")
        switch = DaikinOneAwayModeSwitch(data=data_v1, thermostat=thermostat)
        assert switch.unique_id == "device123-away_mode"

    async def test_unexpected_schema_version_raises(self, daikin_client: DaikinOne) -> None:
        entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 99})
        bad_data = DaikinOneData(_hass=None, entry=entry, daikin=daikin_client)  # type: ignore[arg-type]

        device_data = _make_device({"geofencingAway": False})
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostat("device123")
        with pytest.raises(ValueError, match="unexpected entity uid schema version"):
            DaikinOneAwayModeSwitch(data=bad_data, thermostat=thermostat)


class TestAwayModeSwitchControl:
    async def test_async_turn_on(self, daikin_client: DaikinOne, data_v1: DaikinOneData) -> None:
        device_data = _make_device({"geofencingAway": False})
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostat("device123")
        switch = DaikinOneAwayModeSwitch(data=data_v1, thermostat=thermostat)
        assert switch.is_on is False

        put_calls: list[dict[str, Any]] = []

        async def fake_request(url: str, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
            if method == "PUT":
                put_calls.append({"url": url, "body": body})
                return {}
            return [_make_device({"geofencingAway": True})]

        with patch.object(daikin_client._transport, "request", side_effect=fake_request):
            with patch.object(switch, "async_write_ha_state") as mock_write_state:
                await switch.async_turn_on(dummy_arg=42)
                assert mock_write_state.call_count >= 1

        assert len(put_calls) == 1
        assert put_calls[0]["url"] == f"{DAIKIN_API_URL_DEVICE_DATA}/device123"
        assert put_calls[0]["body"] == {"geofencingAway": True}
        assert switch.is_on is True

    async def test_async_turn_off(self, daikin_client: DaikinOne, data_v1: DaikinOneData) -> None:
        device_data = _make_device({"geofencingAway": True})
        with patch.object(daikin_client._transport, "request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [device_data]
            await daikin_client.update()

        thermostat = daikin_client.get_thermostat("device123")
        switch = DaikinOneAwayModeSwitch(data=data_v1, thermostat=thermostat)
        assert switch.is_on is True

        put_calls: list[dict[str, Any]] = []

        async def fake_request(url: str, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
            if method == "PUT":
                put_calls.append({"url": url, "body": body})
                return {}
            return [_make_device({"geofencingAway": False})]

        with patch.object(daikin_client._transport, "request", side_effect=fake_request):
            with patch.object(switch, "async_write_ha_state") as mock_write_state:
                await switch.async_turn_off(dummy_arg=99)
                assert mock_write_state.call_count >= 1

        assert len(put_calls) == 1
        assert put_calls[0]["url"] == f"{DAIKIN_API_URL_DEVICE_DATA}/device123"
        assert put_calls[0]["body"] == {"geofencingAway": False}
        assert switch.is_on is False
