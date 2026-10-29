"""System Manager: virtuelles Gerät mit aggregierten Werten über alle Zendure-Geräte."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import PERCENTAGE, STATE_ON, EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DEFAULT_PACK_KWH,
    DOMAIN,
    SIGNAL_UPDATE,
    SYNC_RETRY_SECONDS,
    SYSTEM_UNIQUE_ID,
)
from .coordinator import ZendureCoordinator

_LOGGER = logging.getLogger(__name__)


def _num(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


class SystemManager:
    """Aggregiert alle geladenen Zendure-Geräte und gleicht SoC-Grenzen ab."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.targets: dict[str, float] = {}  # "min_soc" / "max_soc" in Prozent
        self.auto_sync = False
        self._last_try: dict[tuple[str, str], float] = {}
        entry.async_on_unload(
            async_dispatcher_connect(hass, SIGNAL_UPDATE, self._handle_device_update)
        )

    # ---- Datenzugriff -------------------------------------------------
    def coordinators(self) -> list[ZendureCoordinator]:
        """Alle aktuell erreichbaren Geräte."""
        result: list[ZendureCoordinator] = []
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.unique_id == SYSTEM_UNIQUE_ID or entry.state is not ConfigEntryState.LOADED:
                continue
            coordinator = getattr(entry, "runtime_data", None)
            if coordinator is not None and coordinator.last_update_success and coordinator.data:
                result.append(coordinator)
        return result

    def stats(self) -> dict[str, Any]:
        coordinators = self.coordinators()
        power = capacity = remaining = soc_capacity = 0.0
        for c in coordinators:
            props = c.data["properties"]
            # + Entladen / - Laden
            power += _num(props.get("packInputPower")) - _num(props.get("outputPackPower"))
            for sn, pack in c.data["packs"].items():
                cap = c.pack_capacity.get(sn, DEFAULT_PACK_KWH)
                capacity += cap
                soc = pack.get("socLevel")
                if isinstance(soc, (int, float)) and not isinstance(soc, bool):
                    soc_capacity += cap
                    remaining += cap * soc / 100
        return {
            "devices": len(coordinators),
            "power": round(power),
            "capacity": round(capacity, 2),
            "remaining": round(remaining, 2),
            "soc": round(remaining / soc_capacity * 100, 1) if soc_capacity else None,
        }

    # ---- Schreiben ------------------------------------------------------
    async def async_push(self, prop: str, value: float) -> None:
        """Wert (in %) auf alle erreichbaren Geräte schreiben."""
        raw = round(value * 10)
        coordinators = self.coordinators()
        results = await asyncio.gather(
            *(c.async_set_properties({prop: raw}) for c in coordinators),
            return_exceptions=True,
        )
        failed = [
            c.config_entry.title for c, r in zip(coordinators, results) if isinstance(r, Exception)
        ]
        if failed:
            raise HomeAssistantError(f"Schreiben fehlgeschlagen für: {', '.join(failed)}")

    def trigger_sync(self) -> None:
        self._last_try.clear()
        self._handle_device_update()

    @callback
    def _handle_device_update(self) -> None:
        """Weicht ein Gerät vom Zielwert ab, wird es (gedrosselt) angeglichen."""
        if not self.auto_sync:
            return
        now = time.monotonic()
        for c in self.coordinators():
            props = c.data["properties"]
            wanted: dict[str, int] = {}
            for key, prop in (("min_soc", "minSoc"), ("max_soc", "socSet")):
                target = self.targets.get(key)
                current = props.get(prop)
                if target is None or not isinstance(current, (int, float)):
                    continue
                raw = round(target * 10)
                last = self._last_try.get((c.sn, prop), -SYNC_RETRY_SECONDS)
                if current != raw and now - last >= SYNC_RETRY_SECONDS:
                    wanted[prop] = raw
                    self._last_try[(c.sn, prop)] = now
            if wanted:
                self.hass.async_create_task(self._write(c, wanted))

    async def _write(self, coordinator: ZendureCoordinator, props: dict[str, int]) -> None:
        try:
            await coordinator.async_set_properties(props)
        except HomeAssistantError as err:
            _LOGGER.warning("Automatischer Abgleich fehlgeschlagen: %s", err)


class SystemEntity(Entity):
    """Basis aller System-Manager-Entitäten."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: SystemManager, key: str) -> None:
        self.manager = manager
        self._key = key
        self._attr_unique_id = f"{SYSTEM_UNIQUE_ID}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, SYSTEM_UNIQUE_ID)},
            name="System Manager",
            manufacturer="Zendure to Home Assistant (lokal)",
            model="Aggregation",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._refresh)
        )

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()


# ---------------------------------------------------------------- Sensoren
SYSTEM_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="soc", name="Gesamt-SoC",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="power", name="Gesamtleistung",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="capacity", name="Gesamtkapazität",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="remaining", name="Gesamtrestkapazität",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="devices", name="Geräte online",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


class SystemSensor(SystemEntity, SensorEntity):
    def __init__(self, manager: SystemManager, desc: SensorEntityDescription) -> None:
        super().__init__(manager, desc.key)
        self.entity_description = desc

    @property
    def available(self) -> bool:
        return self.entity_description.key == "devices" or self.manager.stats()["devices"] > 0

    @property
    def native_value(self) -> Any:
        return self.manager.stats()[self.entity_description.key]


# ----------------------------------------------------------------- Zahlen
class SystemSocNumber(SystemEntity, RestoreNumber):
    """Ziel-minSoC / Ziel-maxSoC, wird beim Setzen auf alle Geräte geschrieben."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self, manager: SystemManager, key: str, name: str, prop: str,
        lo: int, hi: int, default: int,
    ) -> None:
        super().__init__(manager, key)
        self._attr_name = name
        self._prop = prop
        self._default = default
        self._attr_native_min_value = lo
        self._attr_native_max_value = hi

    @property
    def native_value(self) -> float | None:
        return self.manager.targets.get(self._key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for c in self.manager.coordinators():
            raw = c.data["properties"].get(self._prop)
            values[c.config_entry.title] = raw / 10 if isinstance(raw, (int, float)) else None
        return {"geraetewerte": values}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        value = None
        last = await self.async_get_last_number_data()
        if last is not None:
            value = last.native_value
        if value is None:
            for c in self.manager.coordinators():
                raw = c.data["properties"].get(self._prop)
                if isinstance(raw, (int, float)):
                    value = raw / 10
                    break
        self.manager.targets[self._key] = value if value is not None else self._default
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        if self._key == "min_soc":
            other = self.manager.targets.get("max_soc")
            if other is not None and value >= other:
                raise ServiceValidationError("minSoC muss kleiner als maxSoC sein")
        else:
            other = self.manager.targets.get("min_soc")
            if other is not None and value <= other:
                raise ServiceValidationError("maxSoC muss größer als minSoC sein")
        self.manager.targets[self._key] = value
        self.async_write_ha_state()
        await self.manager.async_push(self._prop, value)


# ----------------------------------------------------------------- Schalter
class SystemAutoSyncSwitch(SystemEntity, SwitchEntity, RestoreEntity):
    _attr_name = "SoC-Grenzen automatisch angleichen"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, manager: SystemManager) -> None:
        super().__init__(manager, "auto_sync")

    @property
    def is_on(self) -> bool:
        return self.manager.auto_sync

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state == STATE_ON:
            self.manager.auto_sync = True
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.manager.auto_sync = True
        self.async_write_ha_state()
        self.manager.trigger_sync()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.manager.auto_sync = False
        self.async_write_ha_state()


# --------------------------------------------------------- Plattform-Setup
@callback
def async_setup_system_sensors(entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    manager: SystemManager = entry.runtime_data
    add(SystemSensor(manager, d) for d in SYSTEM_SENSORS)


@callback
def async_setup_system_numbers(entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    manager: SystemManager = entry.runtime_data
    add(
        [
            SystemSocNumber(manager, "min_soc", "Gesamt-minSoC", "minSoc", 0, 50, 10),
            SystemSocNumber(manager, "max_soc", "Gesamt-maxSoC", "socSet", 40, 100, 80),
        ]
    )


@callback
def async_setup_system_switches(entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    manager: SystemManager = entry.runtime_data
    add([SystemAutoSyncSwitch(manager)])
