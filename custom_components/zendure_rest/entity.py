"""Basis-Entitäten."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZendureCoordinator


class ZendureEntity(CoordinatorEntity[ZendureCoordinator]):
    """Entität, die am Hauptgerät hängt und ein Property aus 'properties' liest."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZendureCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.sn}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.sn)},
            manufacturer="Zendure",
            model=coordinator.data.get("product"),
            name=coordinator.config_entry.title,
            serial_number=coordinator.sn,
        )

    @property
    def raw(self) -> Any:
        return self.coordinator.data["properties"].get(self._key)

    @property
    def available(self) -> bool:
        return super().available and self._key in self.coordinator.data["properties"]


class ZendurePackEntity(CoordinatorEntity[ZendureCoordinator]):
    """Entität eines Akku-Packs (eigenes Gerät, via Hauptgerät verbunden)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZendureCoordinator, pack_sn: str, key: str) -> None:
        super().__init__(coordinator)
        self._pack_sn = pack_sn
        self._key = key
        self._attr_unique_id = f"{pack_sn}_{key}"
        pack = coordinator.data["packs"].get(pack_sn, {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pack_sn)},
            manufacturer="Zendure",
            model=str(pack.get("packType", "Batteriepack")),
            name=f"Pack {pack_sn[-4:]}",
            serial_number=pack_sn,
            via_device=(DOMAIN, coordinator.sn),
        )

    @property
    def raw(self) -> Any:
        return self.coordinator.data["packs"].get(self._pack_sn, {}).get(self._key)

    @property
    def available(self) -> bool:
        return super().available and self.raw is not None
