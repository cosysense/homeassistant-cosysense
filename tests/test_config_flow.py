"""Config, reauth and options flows."""
from __future__ import annotations

from unittest.mock import patch

from custom_components.cosysense.const import (
    CONF_CLIENT_ID,
    CONF_LEVELS,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_SITE_UUID,
    CONF_SITES,
    CONF_STALE_HOURS,
    DOMAIN,
)
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import CLIENT_ID, COGNITO, OTHER_SITE, REFRESH, SITE

CREDS = {CONF_CLIENT_ID: CLIENT_ID, CONF_REFRESH_TOKEN: REFRESH}


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_happy_path_one_site(hass: HomeAssistant, mock_api) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    assert result["step_id"] == "site"
    with patch("custom_components.cosysense.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_SITES: [SITE]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Demo Office"
    assert result["data"][CONF_SITE_UUID] == SITE
    assert result["result"].unique_id == SITE


async def test_two_sites_make_two_entries(hass: HomeAssistant, mock_api) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    with patch("custom_components.cosysense.async_setup_entry", return_value=True):
        await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_SITES: [SITE, OTHER_SITE]})
        await hass.async_block_till_done()
    assert sorted(e.unique_id for e in hass.config_entries.async_entries(DOMAIN)) == [SITE, OTHER_SITE]


async def test_no_site_selected_shows_an_error(hass: HomeAssistant, mock_api) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_SITES: []})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_site_selected"}


async def test_rejected_token(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.post(COGNITO, status=400, json={"__type": "NotAuthorizedException", "message": "x"})
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    assert result["errors"] == {"base": "invalid_auth"}


async def test_unreachable(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.post(COGNITO, status=503)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_configured_sites_are_not_offered_again(hass: HomeAssistant, mock_api, entry) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    assert result["step_id"] == "site"
    offered = [o["value"] for o in result["data_schema"].schema[CONF_SITES].config["options"]]
    assert offered == [OTHER_SITE]


async def test_reauth_replaces_the_token(hass: HomeAssistant, mock_api, entry) -> None:
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with patch("custom_components.cosysense.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CLIENT_ID: CLIENT_ID, CONF_REFRESH_TOKEN: "new-token"},
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_REFRESH_TOKEN] == "new-token"


async def test_options_flow(hass: HomeAssistant, mock_api, entry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    levels = result["data_schema"].schema[CONF_LEVELS].config["options"]
    assert levels == ["Main Building / Basement", "Main Building / Ground"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 300, CONF_STALE_HOURS: 6, CONF_LEVELS: ["Main Building / Ground"]},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 300
