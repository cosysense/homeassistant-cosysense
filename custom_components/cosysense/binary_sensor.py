"""Boolean points (occupancy, leak, on/off) as binary sensors."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CosysenseConfigEntry
from .const import BINARY_KINDS
from .coordinator import CosysenseCoordinator
from .entity import CosysensePointEntity, entity_names, humanize

_TRUE = {"1", "true", "on", "open", "occupied", "yes", "leak"}


def binary_label(point: dict[str, Any]) -> str:
    kind = BINARY_KINDS.get(point["entity_class"])
    return kind[0] if kind else humanize(point["entity_class"].removesuffix("_Sensor"))


async def async_setup_entry(hass: HomeAssistant, entry: CosysenseConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities = []
    for equipment in coordinator.data.equipment:
        points = [p for p in equipment.get("points", []) if p.get("value_type") == "boolean"]
        names = entity_names({"points": points}, binary_label)
        entities += [CosysenseBinarySensor(coordinator, equipment, p, names[p["point_uuid"]]) for p in points]
    async_add_entities(entities)


class CosysenseBinarySensor(CosysensePointEntity, BinarySensorEntity):
    """One on/off point."""

    def __init__(self, coordinator: CosysenseCoordinator, equipment: dict[str, Any],
                 point: dict[str, Any], name: str) -> None:
        super().__init__(coordinator, equipment, point, name)
        kind = BINARY_KINDS.get(point["entity_class"])
        self._attr_device_class = kind[1] if kind else None

    @property
    def is_on(self) -> bool | None:
        reading = self.reading
        value = reading.get("value") if reading else None
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return value != 0
        return str(value).strip().lower() in _TRUE
