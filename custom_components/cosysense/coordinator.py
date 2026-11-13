"""One site: inventory hourly, readings every scan interval, live pushes between.

With push on (the inventory carries a push block), changed readings arrive over
MQTT and are applied without touching the poll schedule; the poll then runs
hourly only to reconcile anything a push missed."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
    PUSH_RECONCILE_INTERVAL,
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
        self._poll_interval = timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=self._poll_interval,
        )
        self.api = api
        self.site_uuid: str = entry.data[CONF_SITE_UUID]
        self._inventory: list[dict[str, Any]] | None = None
        self._inventory_at: datetime | None = None
        self.all_levels: list[str] = []
        self.push_config: dict[str, Any] | None = None
        self.push = None  # CosysensePush, set by async_setup_entry when push is on
        # stream_id -> [(point_uuid, scale)]: several points can share one stream.
        self._streams: dict[str, list[tuple[str, float]]] = {}

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
                had_push = self.push_config is not None
                self._inventory = inventory.get("equipment", [])
                self._inventory_at = now
                self.all_levels = sorted({level_key(e) for e in self._inventory})
                self.push_config = inventory.get("push") or None
                self._streams = self._stream_map(self._inventory)
                if previous is not None and (
                    previous != self._point_ids(self._inventory) or had_push != (self.push_config is not None)
                ):
                    # New or removed sensors, or push switched: reload so entities match the model.
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
    def _stream_map(equipment: list[dict[str, Any]]) -> dict[str, list[tuple[str, float]]]:
        streams: dict[str, list[tuple[str, float]]] = {}
        for e in equipment:
            for p in e.get("points", []):
                if p.get("stream_id") and p.get("scale") is not None:
                    streams.setdefault(p["stream_id"], []).append((p["point_uuid"], float(p["scale"])))
        return streams

    @callback
    def apply_push(self, readings: list[dict[str, Any]]) -> None:
        """Merge pushed readings and refresh entities. Uses async_update_listeners,
        not async_set_updated_data, which would push the next poll back on every
        message and starve the reconcile poll."""
        if self.data is None:
            return
        changed = False
        for r in readings:
            if not isinstance(r, dict):
                continue
            raw = r.get("value")
            for point_uuid, scale in self._streams.get(str(r.get("stream_id")), ()):
                value = raw * scale if isinstance(raw, (int, float)) and not isinstance(raw, bool) else raw
                self.data.readings[point_uuid] = {
                    "point_uuid": point_uuid, "value": value, "updated_at": r.get("updated_at"),
                }
                changed = True
        if changed:
            self.async_update_listeners()

    @callback
    def set_push_connected(self, connected: bool) -> None:
        """Poll hourly while pushes flow, at the configured interval otherwise."""
        self.update_interval = PUSH_RECONCILE_INTERVAL if connected else self._poll_interval
        if not connected:
            # Catch up on anything missed while the link was down.
            self.hass.async_create_task(self.async_request_refresh())

    @staticmethod
    def _point_ids(equipment: list[dict[str, Any]] | None) -> set[str] | None:
        if equipment is None:
            return None
        return {p["point_uuid"] for e in equipment for p in e.get("points", [])}
