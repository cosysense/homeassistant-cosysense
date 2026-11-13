"""Entities: devices, areas, units, Energy dashboard fields, staleness, revocation."""
from __future__ import annotations

from datetime import timedelta

from custom_components.cosysense.const import DOMAIN
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import COGNITO, SITE, load

NOW = "2026-11-03T08:12:00+00:00"


def _entity(hass: HomeAssistant, point_n: int):
    unique_id = f"00000000-0000-4000-8000-{point_n:012d}"
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id) or registry.async_get_entity_id(
        "binary_sensor", DOMAIN, unique_id)
    return hass.states.get(entity_id) if entity_id else None


async def _setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_one_entity_per_point(hass: HomeAssistant, mock_api, entry, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)
    await _setup(hass, entry)
    points = sum(len(e["points"]) for e in load("sensors")["equipment"])
    assert len(er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)) == points


async def test_devices_and_area(hass: HomeAssistant, mock_api, entry, freezer) -> None:
    freezer.move_to(NOW)
    await _setup(hass, entry)
    devices = dr.async_get(hass)
    room = devices.async_get_device(identifiers={(DOMAIN, "00000000-0000-4000-8000-000000000100")})
    assert room.manufacturer == "Elsys" and room.model == "ERS2-CO2"
    assert room.serial_number == "0000000000000a01"
    assert ar.async_get(hass).async_get_area(room.area_id).name == "Meeting Room"
    site = devices.async_get_device(identifiers={(DOMAIN, SITE)})
    assert room.via_device_id == site.id
    meter = devices.async_get_device(identifiers={(DOMAIN, "00000000-0000-4000-8000-000000000200")})
    assert meter.area_id is None and meter.manufacturer == "Cosysense"


async def test_room_readings(hass: HomeAssistant, mock_api, entry, freezer) -> None:
    freezer.move_to(NOW)
    await _setup(hass, entry)
    co2 = _entity(hass, 101)
    assert co2.state == "942.0"
    assert co2.attributes["unit_of_measurement"] == "ppm"
    assert co2.attributes["device_class"] == "carbon_dioxide"
    assert co2.attributes["state_class"] == "measurement"
    assert _entity(hass, 102).attributes["unit_of_measurement"] == "°C"
    assert _entity(hass, 105).state == STATE_ON
    assert _entity(hass, 402).state == "blue"
    battery = er.async_get(hass).async_get(_entity(hass, 106).entity_id)
    assert battery.entity_category == "diagnostic"


async def test_energy_dashboard_fields(hass: HomeAssistant, mock_api, entry, freezer) -> None:
    freezer.move_to(NOW)
    await _setup(hass, entry)
    energy = _entity(hass, 201)
    assert (energy.attributes["device_class"], energy.attributes["state_class"],
            energy.attributes["unit_of_measurement"]) == ("energy", "total_increasing", "kWh")
    gas = _entity(hass, 301)
    assert gas.attributes["device_class"] == "gas"
    assert gas.attributes["unit_of_measurement"] == "m³"
    assert float(gas.state) == 749.02  # litres served, m3 shown
    water = _entity(hass, 401)
    assert (water.attributes["device_class"], water.attributes["state_class"]) == ("water", "total_increasing")


async def test_meter_register_device_class_follows_the_meter(hass: HomeAssistant, mock_api, entry, freezer) -> None:
    freezer.move_to(NOW)
    await _setup(hass, entry)
    for point_n, device_class, unit in ((205, "energy", "kWh"), (302, "gas", "m³"), (403, "water", "m³")):
        register = _entity(hass, point_n)
        assert (register.attributes["device_class"], register.attributes["state_class"],
                register.attributes["unit_of_measurement"]) == (device_class, "total_increasing", unit)
        assert register.name.endswith("Meter reading")


async def test_duplicate_classes_get_distinct_names(hass: HomeAssistant, mock_api, entry, freezer) -> None:
    freezer.move_to(NOW)
    await _setup(hass, entry)
    assert _entity(hass, 202).name.endswith("Power Active power")
    assert _entity(hass, 203).name.endswith("Power Active power l1")


async def test_stale_reading_is_unavailable(hass: HomeAssistant, mock_api, entry, freezer) -> None:
    freezer.move_to("2026-11-03T11:20:00+00:00")  # 3 h 10 min after updated_at, past 3 h + 300 s
    await _setup(hass, entry)
    assert _entity(hass, 101).state == STATE_UNAVAILABLE


async def test_revoked_token_asks_for_reauth(hass: HomeAssistant, mock_api, entry, freezer) -> None:
    freezer.move_to(NOW)
    await _setup(hass, entry)
    mock_api.clear_requests()
    mock_api.post(COGNITO, status=400, json={"__type": "NotAuthorizedException", "message": "User is disabled."})
    freezer.tick(timedelta(seconds=901))  # one default poll interval
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _entity(hass, 101).state == STATE_UNAVAILABLE
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == SOURCE_REAUTH for f in flows)


async def test_setup_retries_when_unreachable(hass: HomeAssistant, aioclient_mock, entry) -> None:
    aioclient_mock.post(COGNITO, status=503)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_level_filter(hass: HomeAssistant, mock_api, entry, freezer) -> None:
    freezer.move_to(NOW)
    hass.config_entries.async_update_entry(entry, options={"levels": ["Main Building / Basement"]})
    await _setup(hass, entry)
    assert _entity(hass, 101) is None
    assert _entity(hass, 301) is not None
