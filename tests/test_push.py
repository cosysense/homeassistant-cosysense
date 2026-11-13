"""Live push: setup wiring, applying pushed readings, poll interval switching."""
from __future__ import annotations

import copy
from datetime import timedelta
from unittest.mock import patch

from custom_components.cosysense.const import (
    DEFAULT_SCAN_INTERVAL,
    PUSH_RECONCILE_INTERVAL,
)
from custom_components.cosysense.push import CosysensePush
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant

from .conftest import SITE, load
from .test_sensor import NOW, _entity, _setup

PUSH = {"host": "broker.example.com", "authorizer": "cosysense-ha-push",
        "topic": f"cosysense/sites/{SITE}/readings"}
P = "00000000-0000-4000-8000-{:012d}"


def _push_inventory() -> dict:
    inv = copy.deepcopy(load("sensors"))
    inv["push"] = PUSH
    for e in inv["equipment"]:
        for p in e["points"]:
            p["stream_id"] = "r-" + p["point_uuid"][-3:]
            p["scale"] = 0.001 if p["point_uuid"] == P.format(201) else 1.0
    return inv


def _with_push(mock_api):
    mock_api.clear_requests()
    from .conftest import COGNITO, DEFAULT_BASE_URL, ID_TOKEN
    mock_api.post(COGNITO, json={"AuthenticationResult": {"IdToken": ID_TOKEN}})
    mock_api.get(f"{DEFAULT_BASE_URL}/api/dashboard/meta", json=load("meta"))
    mock_api.get(f"{DEFAULT_BASE_URL}/api/sites/{SITE}/sensors", json=_push_inventory())
    mock_api.get(f"{DEFAULT_BASE_URL}/api/sites/{SITE}/readings", json=load("readings"))


async def test_default_poll_is_fifteen_minutes(hass: HomeAssistant, mock_api, entry, freezer) -> None:
    freezer.move_to(NOW)
    with patch.object(CosysensePush, "start") as start:
        await _setup(hass, entry)
    assert DEFAULT_SCAN_INTERVAL == 900
    assert entry.runtime_data.update_interval == timedelta(seconds=900)
    start.assert_not_called()  # no push block: poll only


async def test_push_starts_when_the_site_has_it(hass: HomeAssistant, mock_api, entry, freezer) -> None:
    freezer.move_to(NOW)
    _with_push(mock_api)
    with patch.object(CosysensePush, "start") as start:
        await _setup(hass, entry)
    start.assert_called_once()
    assert entry.runtime_data.push_config == PUSH


async def test_pushed_readings_update_entities_with_scale(hass: HomeAssistant, mock_api, entry, freezer) -> None:
    freezer.move_to(NOW)
    _with_push(mock_api)
    with patch.object(CosysensePush, "start"):
        await _setup(hass, entry)
    coordinator = entry.runtime_data
    calls_before = mock_api.call_count
    coordinator.apply_push([
        {"stream_id": "r-101", "value": 1200, "updated_at": "2026-11-03T08:11:30Z"},
        {"stream_id": "r-105", "value": 0, "updated_at": "2026-11-03T08:11:30Z"},
        {"stream_id": "r-201", "value": 931000, "updated_at": "2026-11-03T08:11:30Z"},
        {"stream_id": "unknown", "value": 5},
        "garbage",
    ])
    await hass.async_block_till_done()
    assert float(_entity(hass, 101).state) == 1200
    assert _entity(hass, 105).state == STATE_OFF
    assert float(_entity(hass, 201).state) == 931.0
    assert mock_api.call_count == calls_before  # a push never triggers a poll


async def test_poll_slows_while_push_is_connected(hass: HomeAssistant, mock_api, entry, freezer) -> None:
    freezer.move_to(NOW)
    _with_push(mock_api)
    with patch.object(CosysensePush, "start"):
        await _setup(hass, entry)
    coordinator = entry.runtime_data
    coordinator.set_push_connected(True)
    assert coordinator.update_interval == PUSH_RECONCILE_INTERVAL
    coordinator.set_push_connected(False)
    await hass.async_block_till_done()
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)


async def test_push_message_parsing(hass: HomeAssistant) -> None:
    got: list = []
    push = CosysensePush(hass, None, PUSH, "entry", got.append, lambda c: None)
    push._message(b'{"readings": [{"stream_id": "a", "value": 1}]}')
    push._message(b"not json")
    push._message(b'{"readings": "nope"}')
    assert got == [[{"stream_id": "a", "value": 1}]]
    assert push.messages == 1
