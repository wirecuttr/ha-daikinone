"""Tests for Daikin One switch platform, focusing on DaikinOneEmergencyHeatSwitch."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.const import EntityCategory

from custom_components.daikinone import DOMAIN, DaikinOneData
from custom_components.daikinone.client.client import DaikinOne
from custom_components.daikinone.client.mapping import map_thermostat
from custom_components.daikinone.client.models import (
    DaikinThermostat,
    DaikinThermostatCapability,
    DaikinThermostatFanMode,
    DaikinThermostatFanSpeed,
    DaikinThermostatMode,
    DaikinThermostatSchedule,
    DaikinThermostatStatus,
)
from custom_components.daikinone.client.wire import DaikinDeviceDataResponse
from custom_components.daikinone.const import CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY
from custom_components.daikinone.switch import (
    DaikinOneEmergencyHeatSwitch,
    DaikinOneNightModeSwitch,
    DaikinOneQuietModeSwitch,
    async_setup_entry,
)
from custom_components.daikinone.utils import Temperature
from tests.test_mapping import _make_device


def _create_mock_thermostat(
    thermostat_id: str = "device123",
    name: str = "Living Room",
    capabilities: set[DaikinThermostatCapability] | None = None,
    mode: DaikinThermostatMode = DaikinThermostatMode.HEAT,
    away_mode: bool | None = None,
    one_clean_fan_active: bool | None = None,
) -> DaikinThermostat:
    return DaikinThermostat(
        id=thermostat_id,
        location_id="loc456",
        name=name,
        model="ONEPLUS",
        firmware_version="1.0.0",
        online=True,
        capabilities=capabilities if capabilities is not None else {DaikinThermostatCapability.HEAT},
        mode=mode,
        status=DaikinThermostatStatus.IDLE,
        fan_mode=DaikinThermostatFanMode.OFF,
        fan_speed=DaikinThermostatFanSpeed.LOW,
        schedule=DaikinThermostatSchedule(enabled=True, override=False),
        indoor_temperature=Temperature.from_celsius(21.0),
        indoor_humidity=45,
        set_point_heat=Temperature.from_celsius(20.0),
        set_point_heat_min=Temperature.from_celsius(10.0),
        set_point_heat_max=Temperature.from_celsius(30.0),
        set_point_cool=Temperature.from_celsius(24.0),
        set_point_cool_min=Temperature.from_celsius(18.0),
        set_point_cool_max=Temperature.from_celsius(32.0),
        outdoor_temperature=Temperature.from_celsius(10.0),
        outdoor_humidity=60,
        air_quality_outdoor=None,
        air_quality_indoor=None,
        one_clean_fan_active=one_clean_fan_active,
        dual_fuel_furnace_lockout_enable=None,
        equipment={},
        away_mode=away_mode,
    )


@pytest.fixture
def mock_data() -> DaikinOneData:
    entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
    client = MagicMock(spec=DaikinOne)
    client.set_thermostat_mode = AsyncMock()
    client.get_thermostats = MagicMock(return_value={})
    data = DaikinOneData(_hass=None, entry=entry, daikin=client)  # type: ignore[arg-type]
    data.update = AsyncMock()  # type: ignore[method-assign]
    return data


class TestEmergencyHeatSwitch:
    async def test_emergency_heat_switch_creation_when_capable(self, mock_data: DaikinOneData) -> None:
        """Verify emergency heat switch is created when thermostat has EMERGENCY_HEAT capability."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.HEAT, DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.HEAT,
        )
        mock_data.daikin.get_thermostats.return_value = {thermostat.id: thermostat}
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        added_entities = []

        def async_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)  # type: ignore[arg-type]

        emergency_heat_switches = [s for s in added_entities if isinstance(s, DaikinOneEmergencyHeatSwitch)]
        assert len(emergency_heat_switches) == 1
        switch = emergency_heat_switches[0]
        assert switch.is_on is False
        assert switch.entity_description.key == "emergency_heat"
        assert switch.entity_description.icon == "mdi:radiator"
        assert switch.unique_id == "device123-emergency_heat"
        assert switch.device_name == "Living Room Thermostat"

    async def test_emergency_heat_switch_omitted_when_not_capable(self, mock_data: DaikinOneData) -> None:
        """Verify emergency heat switch is NOT created when thermostat lacks EMERGENCY_HEAT capability."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.HEAT},
            mode=DaikinThermostatMode.HEAT,
        )
        mock_data.daikin.get_thermostats.return_value = {thermostat.id: thermostat}
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        added_entities = []

        def async_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        hass = SimpleNamespace(data={DOMAIN: mock_data})
        await async_setup_entry(hass, mock_data.entry, async_add_entities)  # type: ignore[arg-type]

        emergency_heat_switches = [s for s in added_entities if isinstance(s, DaikinOneEmergencyHeatSwitch)]
        assert len(emergency_heat_switches) == 0

    async def test_emergency_heat_switch_is_on_state(self, mock_data: DaikinOneData) -> None:
        """Verify is_on reflects whether thermostat mode is AUX_HEAT."""
        thermostat_aux = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.AUX_HEAT,
        )
        switch_on = DaikinOneEmergencyHeatSwitch(
            SwitchEntityDescription(key="emergency_heat"), mock_data, thermostat_aux
        )
        assert switch_on.is_on is True

        thermostat_heat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.HEAT,
        )
        switch_off = DaikinOneEmergencyHeatSwitch(
            SwitchEntityDescription(key="emergency_heat"), mock_data, thermostat_heat
        )
        assert switch_off.is_on is False

    async def test_emergency_heat_switch_turn_on(self, mock_data: DaikinOneData) -> None:
        """Verify async_turn_on calls set_thermostat_mode with AUX_HEAT and updates optimistically."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.HEAT,
        )
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        switch = DaikinOneEmergencyHeatSwitch(SwitchEntityDescription(key="emergency_heat"), mock_data, thermostat)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_on()
        mock_data.daikin.set_thermostat_mode.assert_called_once_with(thermostat.id, DaikinThermostatMode.AUX_HEAT)
        assert switch.is_on is True

    async def test_emergency_heat_switch_turn_off(self, mock_data: DaikinOneData) -> None:
        """Verify async_turn_off calls set_thermostat_mode with HEAT and updates optimistically."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.AUX_HEAT,
        )
        mock_data.daikin.get_thermostat = MagicMock(return_value=thermostat)

        switch = DaikinOneEmergencyHeatSwitch(SwitchEntityDescription(key="emergency_heat"), mock_data, thermostat)
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_off()
        mock_data.daikin.set_thermostat_mode.assert_called_once_with(thermostat.id, DaikinThermostatMode.HEAT)
        assert switch.is_on is False

    async def test_emergency_heat_switch_uid_schema_v0(self, mock_data: DaikinOneData) -> None:
        """Verify unique_id generation for schema version 0."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.HEAT,
        )
        entry_v0 = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 0})
        data_v0 = DaikinOneData(_hass=None, entry=entry_v0, daikin=mock_data.daikin)  # type: ignore[arg-type]
        switch = DaikinOneEmergencyHeatSwitch(SwitchEntityDescription(key="emergency_heat"), data_v0, thermostat)
        assert switch.unique_id == "device123-emergency_heat"

    async def test_emergency_heat_switch_uid_invalid_schema(self, mock_data: DaikinOneData) -> None:
        """Verify invalid uid schema version raises ValueError."""
        thermostat = _create_mock_thermostat(
            capabilities={DaikinThermostatCapability.EMERGENCY_HEAT},
            mode=DaikinThermostatMode.HEAT,
        )
        entry_invalid = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 99})
        data_invalid = DaikinOneData(_hass=None, entry=entry_invalid, daikin=mock_data.daikin)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="unexpected entity uid schema version"):
            DaikinOneEmergencyHeatSwitch(SwitchEntityDescription(key="emergency_heat"), data_invalid, thermostat)


def _thermostat(enabled: bool | None = True) -> DaikinThermostat:
    payload = _make_device()
    payload["data"].update(
        {
            "nightModeEnabled": enabled,
            "nightModeActive": False,
            "nightModeLightBarAllowed": True,
        }
    )
    return map_thermostat(DaikinDeviceDataResponse(**payload))


def _data(thermostat: DaikinThermostat) -> DaikinOneData:
    entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: 1})
    daikin = MagicMock(spec=DaikinOne)
    daikin.get_thermostat.return_value = thermostat
    daikin.get_thermostats.return_value = {thermostat.id: thermostat}
    daikin.set_thermostat_night_mode = AsyncMock()
    return DaikinOneData(_hass=None, entry=entry, daikin=daikin)  # type: ignore[arg-type]


def _entity(thermostat: DaikinThermostat) -> tuple[DaikinOneNightModeSwitch, DaikinOneData]:
    data = _data(thermostat)
    entity = DaikinOneNightModeSwitch(
        data,
        thermostat,
        SimpleNamespace(key="night_mode", name="Night mode", icon="mdi:weather-night"),
    )
    return entity, data


@pytest.mark.asyncio
async def test_setup_only_creates_switch_when_register_is_available() -> None:
    thermostat = _thermostat()
    data = _data(thermostat)
    entities: list[object] = []

    await async_setup_entry(
        SimpleNamespace(data={DOMAIN: data}),  # type: ignore[arg-type]
        data.entry,
        lambda added, update_before_add=False: entities.extend(added),
    )

    night_mode_switches = [entity for entity in entities if isinstance(entity, DaikinOneNightModeSwitch)]
    assert len(night_mode_switches) == 1
    assert night_mode_switches[0].unique_id == "device123-night_mode"


def test_switch_state_and_optional_attributes() -> None:
    entity, _ = _entity(_thermostat())
    assert entity.is_on is True
    assert entity.extra_state_attributes == {
        "night_mode_active": False,
        "light_bar_allowed": True,
    }

    without_attributes, _ = _entity(_thermostat(enabled=False))
    without_attributes._device.night_mode_active = None
    without_attributes._device.night_mode_light_bar_allowed = None
    assert without_attributes.is_on is False
    assert without_attributes.extra_state_attributes == {}


@pytest.mark.asyncio
async def test_turn_on_uses_optimistic_update() -> None:
    entity, data = _entity(_thermostat(False))
    entity.update_state_optimistically = AsyncMock()  # type: ignore[method-assign]

    await entity.async_turn_on()

    kwargs = entity.update_state_optimistically.await_args.kwargs
    await kwargs["operation"]()
    kwargs["optimistic_update"](entity._device)
    data.daikin.set_thermostat_night_mode.assert_awaited_once_with("device123", True)
    assert entity.is_on is True


def _quiet_thermostat(
    enabled: bool | None = True,
    ho_display: bool | None = True,
    active: bool | None = False,
) -> DaikinThermostat:
    payload = _make_device()
    payload["data"].update(
        {
            "ctOutdoorQuietModeEnabled": 1 if enabled is True else (0 if enabled is False else None),
            "quietModeActive": 1 if active is True else (0 if active is False else None),
            "ctQuietModeHODisplayEnable": ho_display,
        }
    )
    return map_thermostat(DaikinDeviceDataResponse(**payload))


def _quiet_data(thermostat: DaikinThermostat, schema: int = 1) -> DaikinOneData:
    entry = SimpleNamespace(data={CONF_OPTION_ENTITY_UID_SCHEMA_VERSION_KEY: schema})
    daikin = MagicMock(spec=DaikinOne)
    daikin.get_thermostat.return_value = thermostat
    daikin.get_thermostats.return_value = {thermostat.id: thermostat}
    daikin.set_thermostat_quiet_mode_enabled = AsyncMock()
    return DaikinOneData(_hass=None, entry=entry, daikin=daikin)  # type: ignore[arg-type]


def _quiet_entity(
    thermostat: DaikinThermostat,
    schema: int = 1,
) -> tuple[DaikinOneQuietModeSwitch, DaikinOneData]:
    data = _quiet_data(thermostat, schema)
    entity = DaikinOneQuietModeSwitch(
        data,
        thermostat,
        SimpleNamespace(
            key="quiet_mode",
            name="Quiet mode",
            icon="mdi:volume-off",
            entity_category=EntityCategory.CONFIG,
            has_entity_name=True,
            translation_key="quiet_mode",
        ),
    )
    return entity, data


class TestQuietModeSwitch:
    @pytest.mark.asyncio
    async def test_setup_registers_switch_when_ho_display_true_and_enabled_not_none(self) -> None:
        thermostat = _quiet_thermostat(enabled=True, ho_display=True)
        data = _quiet_data(thermostat)
        entities: list = []

        await async_setup_entry(
            SimpleNamespace(data={DOMAIN: data}),  # type: ignore[arg-type]
            data.entry,
            lambda added, update_before_add=False: entities.extend(added),
        )

        quiet_switches = [e for e in entities if isinstance(e, DaikinOneQuietModeSwitch)]
        assert len(quiet_switches) == 1
        assert quiet_switches[0].unique_id == "device123-quiet_mode"
        assert quiet_switches[0].entity_description.entity_category is EntityCategory.CONFIG

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("enabled", "ho_display"),
        [
            (None, True),
            (True, False),
            (True, None),
            (None, None),
        ],
    )
    async def test_setup_suppresses_switch_when_gate_fails(self, enabled: bool | None, ho_display: bool | None) -> None:
        thermostat = _quiet_thermostat(enabled=enabled, ho_display=ho_display)
        data = _quiet_data(thermostat)
        entities: list = []

        await async_setup_entry(
            SimpleNamespace(data={DOMAIN: data}),  # type: ignore[arg-type]
            data.entry,
            lambda added, update_before_add=False: entities.extend(added),
        )

        quiet_switches = [e for e in entities if isinstance(e, DaikinOneQuietModeSwitch)]
        assert len(quiet_switches) == 0

    def test_switch_state_and_extra_state_attributes(self) -> None:
        entity, _ = _quiet_entity(_quiet_thermostat(enabled=True, active=True))
        assert entity.is_on is True
        assert entity.extra_state_attributes == {"quiet_mode_active": True}

        entity_off, _ = _quiet_entity(_quiet_thermostat(enabled=False, active=False))
        assert entity_off.is_on is False
        assert entity_off.extra_state_attributes == {"quiet_mode_active": False}

        without_active, _ = _quiet_entity(_quiet_thermostat(enabled=True, active=None))
        assert without_active.is_on is True
        assert without_active.extra_state_attributes == {}

    @pytest.mark.parametrize("schema", [0, 1])
    def test_unique_id_stability(self, schema: int) -> None:
        entity, _ = _quiet_entity(_quiet_thermostat(enabled=True), schema=schema)
        assert entity.unique_id == "device123-quiet_mode"

    @pytest.mark.asyncio
    async def test_turn_on_and_off_uses_optimistic_update(self) -> None:
        entity, data = _quiet_entity(_quiet_thermostat(enabled=False))
        entity.update_state_optimistically = AsyncMock()  # type: ignore[method-assign]

        await entity.async_turn_on()
        kwargs = entity.update_state_optimistically.await_args.kwargs
        await kwargs["operation"]()
        kwargs["optimistic_update"](entity._device)
        data.daikin.set_thermostat_quiet_mode_enabled.assert_awaited_once_with("device123", True)
        assert entity.is_on is True

        data.daikin.set_thermostat_quiet_mode_enabled.reset_mock()
        await entity.async_turn_off()
        kwargs = entity.update_state_optimistically.await_args.kwargs
        await kwargs["operation"]()
        kwargs["optimistic_update"](entity._device)
        data.daikin.set_thermostat_quiet_mode_enabled.assert_awaited_once_with("device123", False)
        assert entity.is_on is False

    async def test_async_get_device(self) -> None:
        entity, _ = _quiet_entity(_quiet_thermostat(enabled=True))
        dev = await entity.async_get_device()
        assert dev.id == "device123"
