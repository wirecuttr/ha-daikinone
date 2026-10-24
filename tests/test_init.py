from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from custom_components.daikinone import DaikinOneData, async_setup_entry
from custom_components.daikinone.client.models import DaikinLocation
from custom_components.daikinone.const import DOMAIN, MANUFACTURER
from custom_components.daikinone.exceptions import DaikinAuthException, DaikinServiceException


def _entry_with_data(entry_id: str = "test_entry_id", title: str = "Daikin One", **data: str) -> SimpleNamespace:
    return SimpleNamespace(entry_id=entry_id, title=title, data=data, async_start_reauth=MagicMock())


class TestAsyncSetupEntry:
    async def test_raises_config_entry_not_ready_on_initial_update_failure(self) -> None:
        """Regression test: a transient setup failure must be retryable, not permanently failed."""
        hass = SimpleNamespace(data={})
        entry = _entry_with_data(**{CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password"})

        with patch("custom_components.daikinone.DaikinOne") as mock_daikin_cls:
            mock_daikin_cls.return_value.update = AsyncMock(side_effect=DaikinServiceException("boom", status=503))

            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, entry)  # type: ignore[arg-type]

        assert DOMAIN not in hass.data

    async def test_raises_config_entry_auth_failed_on_rejected_credentials(self) -> None:
        """Rejected credentials must surface distinctly from a transient outage, so HA marks the
        entry as needing re-authentication instead of retrying forever with dead credentials."""
        hass = SimpleNamespace(data={})
        entry = _entry_with_data(**{CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password"})

        with patch("custom_components.daikinone.DaikinOne") as mock_daikin_cls:
            mock_daikin_cls.return_value.update = AsyncMock(side_effect=DaikinAuthException("boom"))

            with pytest.raises(ConfigEntryAuthFailed):
                await async_setup_entry(hass, entry)  # type: ignore[arg-type]

        assert DOMAIN not in hass.data

    async def test_location_hub_device_registration_and_empty_location_filtering(self) -> None:
        """Verify setup registers location hub devices in Device Registry and filters out empty locations."""
        hass = SimpleNamespace(
            data={},
            config_entries=SimpleNamespace(
                async_forward_entry_setups=AsyncMock(return_value=True),
                async_update_entry=MagicMock(),
            ),
        )
        entry = _entry_with_data(
            entry_id="entry_abc",
            title="Daikin One",
            **{CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password"},
        )

        loc1 = DaikinLocation(
            id="loc1",
            name="homeHA",
            street_address="88 Canada Olympic Rd",
            apt="",
            city="Calgary",
            province="AB",
            postal_code="T3B5R5",
            country="CA",
            time_zone="America/Regina",
            latitude=51.08,
            longitude=-114.20,
            has_owner=True,
        )
        loc2_empty = DaikinLocation(
            id="loc2_empty",
            name="Empty Cabin",
            street_address="123 Nowhere",
            apt="",
            city="Banff",
            province="AB",
            postal_code="T0L 0C0",
            country="CA",
            time_zone="America/Edmonton",
            latitude=51.17,
            longitude=-115.57,
            has_owner=False,
        )

        mock_thermostat = SimpleNamespace(id="t1", location_id="loc1")
        mock_dr = MagicMock()

        with (
            patch("custom_components.daikinone.DaikinOne") as mock_daikin_cls,
            patch("custom_components.daikinone.dr.async_get", return_value=mock_dr),
        ):
            instance = mock_daikin_cls.return_value
            instance.update = AsyncMock()
            instance.get_locations = AsyncMock(return_value={"loc1": loc1, "loc2_empty": loc2_empty})
            instance.thermostats = {"t1": mock_thermostat}

            await async_setup_entry(hass, entry)  # type: ignore[arg-type]

        # loc1 has an active thermostat -> registered
        mock_dr.async_get_or_create.assert_called_once_with(
            config_entry_id="entry_abc",
            identifiers={(DOMAIN, "loc1")},
            name="homeHA",
            manufacturer=MANUFACTURER,
            model="Skyport Location",
            entry_type=dr.DeviceEntryType.SERVICE,
            configuration_url="https://api.daikinskyport.com/locations/loc1",
        )

        # entry title migrated from "Daikin One" to "homeHA"
        hass.config_entries.async_update_entry.assert_called_once_with(entry, title="homeHA")

    async def test_dynamic_title_migration_skips_when_title_already_customized(self) -> None:
        """Verify dynamic title migration does not overwrite custom user titles."""
        hass = SimpleNamespace(
            data={},
            config_entries=SimpleNamespace(
                async_forward_entry_setups=AsyncMock(return_value=True),
                async_update_entry=MagicMock(),
            ),
        )
        entry = _entry_with_data(
            entry_id="entry_abc",
            title="Custom User Title",
            **{CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password"},
        )

        loc1 = DaikinLocation(
            id="loc1",
            name="homeHA",
            street_address="88 Canada Olympic Rd",
            apt="",
            city="Calgary",
            province="AB",
            postal_code="T3B5R5",
            country="CA",
            time_zone="America/Regina",
            latitude=51.08,
            longitude=-114.20,
            has_owner=True,
        )

        mock_dr = MagicMock()

        with (
            patch("custom_components.daikinone.DaikinOne") as mock_daikin_cls,
            patch("custom_components.daikinone.dr.async_get", return_value=mock_dr),
        ):
            instance = mock_daikin_cls.return_value
            instance.update = AsyncMock()
            instance.get_locations = AsyncMock(return_value={"loc1": loc1})
            instance.thermostats = {"t1": SimpleNamespace(id="t1", location_id="loc1")}

            await async_setup_entry(hass, entry)  # type: ignore[arg-type]

        hass.config_entries.async_update_entry.assert_not_called()


class TestDaikinOneDataUpdate:
    async def test_auth_failure_during_runtime_poll_starts_reauth_and_reraises(self) -> None:
        """Regression test: credentials revoked after setup (e.g. a changed password) must
        prompt the user to re-authenticate, not just fail every poll silently forever until
        someone notices and manually reloads the integration."""
        entry = SimpleNamespace(async_start_reauth=MagicMock())
        daikin = MagicMock()
        daikin.update = AsyncMock(side_effect=DaikinAuthException("boom"))

        data = DaikinOneData(None, entry, daikin)  # type: ignore[arg-type]

        with pytest.raises(DaikinAuthException):
            await data.update()

        entry.async_start_reauth.assert_called_once_with(None)
