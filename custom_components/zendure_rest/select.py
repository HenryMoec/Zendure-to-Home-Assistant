"""Auswahlfelder: AC-Modus, Energie Export (gridReverse), Off-Grid-Modus (gridOffMode)."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureEntity


@dataclass(frozen=True, kw_only=True)
class ZendureSelectDescription(SelectEntityDescription):
    mapping: dict[int, str]  # Rohwert des Geräts -> Option


SELECTS: tuple[ZendureSelectDescription, ...] = (
    ZendureSelectDescription(
        key="acMode",
        translation_key="ac_mode",
        mapping={1: "input", 2: "output"},
    ),
    ZendureSelectDescription(
        key="gridReverse",
        translation_key="grid_reverse",
        mapping={0: "disabled", 1: "allow", 2: "forbidden"},
    ),
    ZendureSelectDescription(
        key="gridOffMode",
        translation_key="grid_off_mode",
        mapping={0: "normal", 1: "eco", 2: "off"},
    ),
)


class ZendureSelect(ZendureEntity, SelectEntity):
    entity_description: ZendureSelectDescription

    def __init__(
        self, coordinator: ZendureCoordinator, desc: ZendureSelectDescription
    ) -> None:
        super().__init__(coordinator, desc.key)
        self.entity_description = desc
        self._attr_options = list(desc.mapping.values())
        self._reverse = {v: k for k, v in desc.mapping.items()}

    @property
    def current_option(self) -> str | None:
        return self.entity_description.mapping.get(self.raw)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_properties({self._key: self._reverse[option]})


async def async_setup_entry(
    hass: HomeAssistant, entry: ZendureConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    c = entry.runtime_data
    async_add_entities(
        ZendureSelect(c, d) for d in SELECTS if d.key in c.data["properties"]
    )
