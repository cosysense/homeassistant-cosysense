"""Shared fixtures: synthetic API responses and a mocked Cosysense backend."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from custom_components.cosysense.const import (
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_SITE_NAME,
    CONF_SITE_UUID,
    DEFAULT_BASE_URL,
    DEFAULT_REGION,
    DOMAIN,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

FIXTURES = Path(__file__).parent / "fixtures"
COGNITO = "https://cognito-idp.eu-west-2.amazonaws.com/"
SITE = "00000000-0000-4000-8000-000000000001"
OTHER_SITE = "00000000-0000-4000-8000-000000000002"
CLIENT_ID = "test-client-id"
REFRESH = "test-refresh-token"
ID_TOKEN = "header.payload.signature"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


ENTRY_DATA = {
    CONF_CLIENT_ID: CLIENT_ID,
    CONF_REFRESH_TOKEN: REFRESH,
    CONF_BASE_URL: DEFAULT_BASE_URL,
    CONF_REGION: DEFAULT_REGION,
    CONF_SITE_UUID: SITE,
    CONF_SITE_NAME: "Demo Office",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def mock_api(aioclient_mock):
    """A healthy backend: Cognito refresh plus the three customer routes."""
    aioclient_mock.post(COGNITO, json={"AuthenticationResult": {"IdToken": ID_TOKEN}})
    aioclient_mock.get(f"{DEFAULT_BASE_URL}/api/dashboard/meta", json=load("meta"))
    aioclient_mock.get(f"{DEFAULT_BASE_URL}/api/sites/{SITE}/sensors", json=load("sensors"))
    aioclient_mock.get(f"{DEFAULT_BASE_URL}/api/sites/{SITE}/readings", json=load("readings"))
    return aioclient_mock


@pytest.fixture
def entry(hass):
    e = MockConfigEntry(domain=DOMAIN, unique_id=SITE, title="Demo Office", data=dict(ENTRY_DATA))
    e.add_to_hass(hass)
    return e
