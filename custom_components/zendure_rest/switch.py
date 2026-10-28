"""Schalter (smartMode)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SYSTEM_UNIQUE_ID
from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureEntity
from .system import async_setup_system_switches


class ZendureSmartModeSwitch(ZendureEntity, SwitchEntity):
    _attr_name = "Smart Mode"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZendureCoordinator) -> None:
        super().__init__(coordinator, "smartMode")

    @property
    def is_on(self) -> bool | None:
        v = self.raw
        return None if v is None else bool(v)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_properties({"smartMode": 1})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_properties({"smartMode": 0})


async def async_setup_entry(
    hass: HomeAssistant, entry: ZendureConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.unique_id == SYSTEM_UNIQUE_ID:
        async_setup_system_switches(entry, async_add_entities)
        return
    c = entry.runtime_data
    if "smartMode" in c.data["properties"]:
        async_add_entities([ZendureSmartModeSwitch(c)])
