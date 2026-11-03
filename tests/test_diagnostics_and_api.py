"""Diagnostics redact credentials; the client never shows its tokens."""
from __future__ import annotations

import json

from custom_components.cosysense.api import CosysenseApi
from custom_components.cosysense.diagnostics import async_get_config_entry_diagnostics
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import CLIENT_ID, COGNITO, ID_TOKEN, REFRESH


async def test_diagnostics_redact_credentials(hass: HomeAssistant, mock_api, entry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = json.dumps(diag)
    assert REFRESH not in text and CLIENT_ID not in text
    assert diag["entry"]["data"]["refresh_token"] == "**REDACTED**"
    assert diag["equipment"]


async def test_refresh_call_and_bearer(hass: HomeAssistant, mock_api) -> None:
    api = CosysenseApi(async_get_clientsession(hass), client_id=CLIENT_ID, refresh_token=REFRESH,
                       base_url="https://portal.cosysense.space")
    assert REFRESH not in repr(api) and CLIENT_ID not in repr(api)
    await api.sites()
    _method, url, body, _headers = mock_api.mock_calls[0][:4]
    assert str(url) == COGNITO
    sent = json.loads(body)
    assert sent["AuthFlow"] == "REFRESH_TOKEN_AUTH"
    assert sent["AuthParameters"]["REFRESH_TOKEN"] == REFRESH
    _, _, _, get_headers = mock_api.mock_calls[1][:4]
    assert get_headers["Authorization"] == f"Bearer {ID_TOKEN}"
    assert get_headers["User-Agent"].startswith("HomeAssistant-Cosysense")
