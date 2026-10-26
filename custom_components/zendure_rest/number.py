"""Regelbare Zahlenwerte."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureEntity


@dataclass(frozen=True, kw_only=True)
class ZendureNumberDescription(NumberEntityDescription):
    factor: int = 1  # Rohwert = Anzeigewert * factor


NUMBERS: tuple[ZendureNumberDescription, ...] = (
    ZendureNumberDescription(
        key="outputLimit", name="Ausgangslimit",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=0, native_max_value=2400, native_step=1,
        mode=NumberMode.BOX,
    ),
    ZendureNumberDescription(
        key="inputLimit", name="Eingangslimit",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=0, native_max_value=2400, native_step=1,
        mode=NumberMode.BOX,
    ),
    ZendureNumberDescription(
        key="socSet", name="Max. Ladestand",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=40, native_max_value=100, native_step=1,
        mode=NumberMode.SLIDER, factor=10, entity_category=EntityCategory.CONFIG,
    ),
    ZendureNumberDescription(
        key="minSoc", name="Min. Ladestand",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0, native_max_value=50, native_step=1,
        mode=NumberMode.SLIDER, factor=10, entity_category=EntityCategory.CONFIG,
    ),
)


class ZendureNumber(ZendureEntity, NumberEntity):
    entity_description: ZendureNumberDescription

    def __init__(self, coordinator: ZendureCoordinator, desc: ZendureNumberDescription) -> None:
        super().__init__(coordinator, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> float | None:
        v = self.raw
        return None if v is None else v / self.entity_description.factor

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_properties(
            {self._key: round(value * self.entity_description.factor)}
        )


async def async_setup_entry(
    hass: HomeAssistant, entry: ZendureConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    c = entry.runtime_data
    async_add_entities(
        ZendureNumber(c, d) for d in NUMBERS if d.key in c.data["properties"]
    )
