"""Polls one site: inventory hourly, readings every scan interval."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import CosysenseApi, CosysenseAuthError, CosysenseError
from .const import (
    CONF_LEVELS,
    CONF_SCAN_INTERVAL,
    CONF_SITE_UUID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    INVENTORY_REFRESH,
)

_LOGGER = logging.getLogger(__name__)


def level_key(equipment: dict[str, Any]) -> str:
    """The building / level label the options flow filters on."""
    return " / ".join(p for p in (equipment.get("building_name"), equipment.get("level_name")) if p) or "Unplaced"


@dataclass
class SiteData:
    """What the entities read."""

    equipment: list[dict[str, Any]] = field(default_factory=list)
    readings: dict[str, dict[str, Any]] = field(default_factory=dict)


class CosysenseCoordinator(DataUpdateCoordinator[SiteData]):
    """One coordinator per config entry, which is one site."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: CosysenseApi) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.api = api
        self.site_uuid: str = entry.data[CONF_SITE_UUID]
        self._inventory: list[dict[str, Any]] | None = None
        self._inventory_at: datetime | None = None
        self.all_levels: list[str] = []

    def _filtered(self, equipment: list[dict[str, Any]]) -> list[dict[str, Any]]:
        wanted = set(self.config_entry.options.get(CONF_LEVELS) or [])
        if not wanted:
            return equipment
        return [e for e in equipment if level_key(e) in wanted]

    async def _async_update_data(self) -> SiteData:
        try:
            # Refresh on every poll: a disabled user or revoked token fails here.
            await self.api.refresh()
            now = dt_util.utcnow()
            if self._inventory is None or now - self._inventory_at >= INVENTORY_REFRESH:
                inventory = await self.api.sensors(self.site_uuid)
                previous = self._point_ids(self._inventory)
                self._inventory = inventory.get("equipment", [])
                self._inventory_at = now
                self.all_levels = sorted({level_key(e) for e in self._inventory})
                if previous is not None and previous != self._point_ids(self._inventory):
                    # New or removed sensors: reload so entities match the model.
                    self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
            readings = await self.api.readings(self.site_uuid)
        except CosysenseAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except CosysenseError as err:
            raise UpdateFailed(str(err)) from err
        return SiteData(
            equipment=self._filtered(self._inventory),
            readings={r["point_uuid"]: r for r in readings.get("readings", [])},
        )

    @staticmethod
    def _point_ids(equipment: list[dict[str, Any]] | None) -> set[str] | None:
        if equipment is None:
            return None
        return {p["point_uuid"] for e in equipment for p in e.get("points", [])}
