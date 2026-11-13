"""Numeric and enum points as sensors."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CosysenseConfigEntry
from .const import (
    ENERGY_CLASSES,
    GAS_LITRES,
    METER_REGISTER_CLASS,
    METER_REGISTER_DEVICE_CLASSES,
    SENSOR_KINDS,
    UNITS,
    SensorKind,
)
from .coordinator import CosysenseCoordinator
from .entity import CosysensePointEntity, entity_names, humanize


def sensor_kind(point: dict[str, Any]) -> SensorKind:
    return SENSOR_KINDS.get(point["entity_class"]) or SensorKind(humanize(point["entity_class"].removesuffix("_Sensor")))


def register_device_class(equipment: dict[str, Any]) -> SensorDeviceClass | None:
    equipment_class = equipment.get("entity_class") or ""
    return next((dc for key, dc in METER_REGISTER_DEVICE_CLASSES if key in equipment_class), None)


def describe(point: dict[str, Any], equipment: dict[str, Any] | None = None) -> tuple[SensorKind, SensorDeviceClass | None, str | None, float, SensorStateClass | None]:
    """(kind, device class, unit, multiplier, state class) for one point."""
    kind = sensor_kind(point)
    if point.get("value_type") == "enum":
        return kind, None, None, 1.0, None
    unit, scale = UNITS.get(point.get("unit") or "", (None, 1.0))
    device_class = kind.device_class
    if point["entity_class"] == METER_REGISTER_CLASS:
        device_class = register_device_class(equipment or {})
    if device_class == SensorDeviceClass.GAS and point.get("unit") == GAS_LITRES[0]:
        unit, scale = GAS_LITRES[1]
    if device_class is not None and unit is None and device_class not in (
        SensorDeviceClass.POWER_FACTOR, SensorDeviceClass.AQI,
    ):
        device_class = None  # a device class without its unit fails HA's checks
    if point.get("cumulative"):
        state_class = SensorStateClass.TOTAL_INCREASING
    elif device_class in ENERGY_CLASSES:
        state_class = SensorStateClass.TOTAL
    else:
        state_class = SensorStateClass.MEASUREMENT
    return kind, device_class, unit, scale, state_class


async def async_setup_entry(hass: HomeAssistant, entry: CosysenseConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities = []
    for equipment in coordinator.data.equipment:
        points = [p for p in equipment.get("points", []) if p.get("value_type") != "boolean"]
        names = entity_names({"points": points}, lambda p: sensor_kind(p).label)
        entities += [CosysenseSensor(coordinator, equipment, p, names[p["point_uuid"]]) for p in points]
    async_add_entities(entities)


class CosysenseSensor(CosysensePointEntity, SensorEntity):
    """One numeric or enum point."""

    def __init__(self, coordinator: CosysenseCoordinator, equipment: dict[str, Any],
                 point: dict[str, Any], name: str) -> None:
        super().__init__(coordinator, equipment, point, name)
        kind, device_class, unit, scale, state_class = describe(point, equipment)
        self._scale = scale
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        if kind.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> float | str | None:
        reading = self.reading
        value = reading.get("value") if reading else None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return round(value * self._scale, 6)
        return value
