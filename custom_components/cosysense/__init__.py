"""Cosysense: bring a building's sensors and meters into Home Assistant."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration

from .api import CosysenseApi
from .const import (
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    DEFAULT_REGION,
    DOMAIN,
)
from .coordinator import CosysenseCoordinator
from .entity import site_device
from .push import CosysensePush

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

type CosysenseConfigEntry = ConfigEntry[CosysenseCoordinator]


def build_api(hass: HomeAssistant, data: dict, version: str = "0") -> CosysenseApi:
    return CosysenseApi(
        async_get_clientsession(hass),
        client_id=data[CONF_CLIENT_ID],
        refresh_token=data[CONF_REFRESH_TOKEN],
        base_url=data[CONF_BASE_URL],
        region=data.get(CONF_REGION, DEFAULT_REGION),
        user_agent=f"HomeAssistant-Cosysense/{version}",
    )


async def async_setup_entry(hass: HomeAssistant, entry: CosysenseConfigEntry) -> bool:
    integration = await async_get_integration(hass, DOMAIN)
    coordinator = CosysenseCoordinator(hass, entry, build_api(hass, dict(entry.data), str(integration.version)))
    # Raises ConfigEntryNotReady or ConfigEntryAuthFailed on a failed first poll.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, **site_device(coordinator))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    if coordinator.push_config:
        push = CosysensePush(
            hass, coordinator.api, coordinator.push_config, entry.entry_id,
            coordinator.apply_push, coordinator.set_push_connected,
        )
        coordinator.push = push
        push.start()
        entry.async_on_unload(push.stop)
    return True


async def _options_updated(hass: HomeAssistant, entry: CosysenseConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CosysenseConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
