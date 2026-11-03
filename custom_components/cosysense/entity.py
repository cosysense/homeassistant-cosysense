"""Shared entity base: one device per equipment, one entity per point."""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_SITE_NAME,
    CONF_STALE_HOURS,
    DEFAULT_STALE_HOURS,
    DOMAIN,
    MANUFACTURER,
    SERVER_KEEPALIVE,
)
from .coordinator import CosysenseCoordinator

_POINT_PREFIX = re.compile(r"^.*\)[-_ ]")


def humanize(text: str) -> str:
    text = text.replace("_", " ").replace("-", " ").strip()
    return text[:1].upper() + text[1:]


def point_suffix(point_name: str) -> str:
    """'elsys-eco (3A36)-co2' -> 'Co2': the part after the device label."""
    return humanize(_POINT_PREFIX.sub("", point_name))


def equipment_device(coordinator: CosysenseCoordinator, equipment: dict[str, Any]) -> DeviceInfo:
    template = equipment.get("template")
    if template and "-" in template:
        manufacturer, model = template.split("-", 1)
    else:
        manufacturer, model = MANUFACTURER, humanize(equipment.get("entity_class") or "Equipment")
    info = DeviceInfo(
        identifiers={(DOMAIN, equipment["equipment_uuid"])},
        name=equipment["name"],
        manufacturer=manufacturer,
        model=model,
        via_device=(DOMAIN, coordinator.site_uuid),
    )
    if equipment.get("space_name"):
        info["suggested_area"] = equipment["space_name"]
    if equipment.get("dev_eui"):
        info["serial_number"] = equipment["dev_eui"]
    return info


def site_device(coordinator: CosysenseCoordinator) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.site_uuid)},
        name=coordinator.config_entry.data.get(CONF_SITE_NAME) or "Cosysense site",
        manufacturer=MANUFACTURER,
        model="Site",
        entry_type=DeviceEntryType.SERVICE,
    )


class CosysensePointEntity(CoordinatorEntity[CosysenseCoordinator]):
    """A Brick point of one equipment."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CosysenseCoordinator, equipment: dict[str, Any],
                 point: dict[str, Any], name: str) -> None:
        super().__init__(coordinator)
        self._point = point
        self._attr_unique_id = point["point_uuid"]
        self._attr_name = name
        self._attr_device_info = equipment_device(coordinator, equipment)

    @property
    def reading(self) -> dict[str, Any] | None:
        return self.coordinator.data.readings.get(self._point["point_uuid"])

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        reading = self.reading
        if not reading or reading.get("value") is None:
            return False
        updated = dt_util.parse_datetime(reading.get("updated_at") or "")
        if updated is None:
            return False
        hours = self.coordinator.config_entry.options.get(CONF_STALE_HOURS, DEFAULT_STALE_HOURS)
        return dt_util.utcnow() - updated <= timedelta(hours=hours) + SERVER_KEEPALIVE

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        reading = self.reading
        return {"last_seen": reading.get("updated_at")} if reading else None


def entity_names(equipment: dict[str, Any], label_for) -> dict[str, str]:
    """point_uuid -> entity name. A class that appears twice on one device gets
    the point's own suffix so the names stay distinct."""
    labels = {p["point_uuid"]: label_for(p) for p in equipment.get("points", [])}
    counts: dict[str, int] = {}
    for label in labels.values():
        counts[label] = counts.get(label, 0) + 1
    out = {}
    for p in equipment.get("points", []):
        label = labels[p["point_uuid"]]
        out[p["point_uuid"]] = f"{label} {point_suffix(p['name'])}" if counts[label] > 1 else label
    return out
