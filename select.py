"""Auswahlfelder (acMode)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureEntity

AC_MODES = {1: "input", 2: "output"}  # Rohwert -> Option
AC_MODES_REV = {v: k for k, v in AC_MODES.items()}


class ZendureAcModeSelect(ZendureEntity, SelectEntity):
    _attr_name = "AC-Modus"
    _attr_options = list(AC_MODES_REV)

    def __init__(self, coordinator: ZendureCoordinator) -> None:
        super().__init__(coordinator, "acMode")

    @property
    def current_option(self) -> str | None:
        return AC_MODES.get(self.raw)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_properties({"acMode": AC_MODES_REV[option]})


async def async_setup_entry(
    hass: HomeAssistant, entry: ZendureConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    c = entry.runtime_data
    if "acMode" in c.data["properties"]:
        async_add_entities([ZendureAcModeSelect(c)])
