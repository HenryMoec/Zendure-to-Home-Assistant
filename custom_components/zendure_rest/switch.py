"""Schalter: nur für den System Manager (Geräte haben keine Schalter mehr)."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SYSTEM_UNIQUE_ID
from .system import async_setup_system_switches


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.unique_id == SYSTEM_UNIQUE_ID:
        async_setup_system_switches(entry, async_add_entities)
