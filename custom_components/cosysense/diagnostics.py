"""Diagnostics download, with credentials redacted."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import CosysenseConfigEntry
from .const import CONF_CLIENT_ID, CONF_REFRESH_TOKEN

TO_REDACT = {CONF_CLIENT_ID, CONF_REFRESH_TOKEN, "IdToken", "RefreshToken", "Authorization"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: CosysenseConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data({"data": dict(entry.data), "options": dict(entry.options)}, TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "poll_interval_s": coordinator.update_interval.total_seconds() if coordinator.update_interval else None,
        "push": {
            "enabled": coordinator.push_config is not None,
            "connected": bool(getattr(coordinator.push, "connected", False)),
            "messages": getattr(coordinator.push, "messages", 0),
        },
        "equipment": coordinator.data.equipment,
        "readings": list(coordinator.data.readings.values()),
    }
