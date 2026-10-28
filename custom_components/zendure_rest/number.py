"""Regelbare Zahlenwerte."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_PACK_KWH, SIGNAL_UPDATE, SYSTEM_UNIQUE_ID
from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureEntity, ZendurePackEntity
from .system import async_setup_system_numbers


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


class ZendurePackCapacity(ZendurePackEntity, RestoreNumber):
    """Nutzbare Kapazität eines Packs in kWh (für den System Manager)."""

    _attr_name = "Kapazität"
    _attr_device_class = NumberDeviceClass.ENERGY_STORAGE
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_native_min_value = 0.1
    _attr_native_max_value = 10
    _attr_native_step = 0.01
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZendureCoordinator, pack_sn: str) -> None:
        super().__init__(coordinator, pack_sn, "capacity")
        self._value: float = DEFAULT_PACK_KWH
        coordinator.pack_capacity.setdefault(pack_sn, self._value)

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and self._pack_sn in self.coordinator.data["packs"]
        )

    @property
    def native_value(self) -> float:
        return self._value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._value = last.native_value
        self.coordinator.pack_capacity[self._pack_sn] = self._value
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    async def async_set_native_value(self, value: float) -> None:
        self._value = value
        self.coordinator.pack_capacity[self._pack_sn] = value
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)


async def async_setup_entry(
    hass: HomeAssistant, entry: ZendureConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.unique_id == SYSTEM_UNIQUE_ID:
        async_setup_system_numbers(entry, async_add_entities)
        return

    c = entry.runtime_data
    async_add_entities(
        ZendureNumber(c, d) for d in NUMBERS if d.key in c.data["properties"]
    )

    known_packs: set[str] = set()

    def _add_new_packs() -> None:
        new = [sn for sn in c.data["packs"] if sn not in known_packs]
        if not new:
            return
        known_packs.update(new)
        async_add_entities(ZendurePackCapacity(c, sn) for sn in new)

    _add_new_packs()
    entry.async_on_unload(c.async_add_listener(_add_new_packs))
