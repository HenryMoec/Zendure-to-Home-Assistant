"""Sensoren: Gerät + dynamisch pro Akku-Pack."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_PACK_KWH, SIGNAL_UPDATE, SYSTEM_UNIQUE_ID
from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureEntity, ZendurePackEntity
from .system import async_setup_system_sensors


@dataclass(frozen=True, kw_only=True)
class ZendureSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Any], Any] | None = None


def _deci_kelvin(v: Any) -> float:
    return round((v - 2731) / 10, 1)


def _centi(v: Any) -> float:
    return round(v / 100, 2)


_POWER = dict(
    device_class=SensorDeviceClass.POWER,
    native_unit_of_measurement=UnitOfPower.WATT,
    state_class=SensorStateClass.MEASUREMENT,
)
_DIAG = dict(entity_category=EntityCategory.DIAGNOSTIC)

DEVICE_SENSORS: tuple[ZendureSensorDescription, ...] = (
    ZendureSensorDescription(
        key="electricLevel", name="Ladestand",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZendureSensorDescription(key="outputHomePower", name="Ausgangsleistung Haus", **_POWER),
    ZendureSensorDescription(key="gridInputPower", name="Netzeingangsleistung", **_POWER),
    ZendureSensorDescription(key="outputPackPower", name="Ladeleistung Pack", **_POWER),
    ZendureSensorDescription(key="packInputPower", name="Entladeleistung Pack", **_POWER),
    ZendureSensorDescription(key="solarInputPower", name="Solarleistung gesamt", **_POWER),
    ZendureSensorDescription(key="solarPower1", name="Solarleistung 1", **_POWER),
    ZendureSensorDescription(key="solarPower2", name="Solarleistung 2", **_POWER),
    ZendureSensorDescription(key="solarPower3", name="Solarleistung 3", **_POWER),
    ZendureSensorDescription(key="solarPower4", name="Solarleistung 4", **_POWER),
    ZendureSensorDescription(
        key="remainOutTime", name="Restlaufzeit",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZendureSensorDescription(
        key="hyperTmp", name="Temperatur",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_deci_kelvin,
    ),
    ZendureSensorDescription(key="packNum", name="Anzahl Packs", **_DIAG),
    ZendureSensorDescription(key="packState", name="Packstatus", **_DIAG),
    ZendureSensorDescription(key="acStatus", name="AC-Status", **_DIAG),
    ZendureSensorDescription(key="dcStatus", name="DC-Status", **_DIAG),
    ZendureSensorDescription(key="pvStatus", name="PV-Status", **_DIAG),
    ZendureSensorDescription(key="gridState", name="Netzstatus", **_DIAG),
    ZendureSensorDescription(key="faultLevel", name="Fehlerlevel", **_DIAG),
    ZendureSensorDescription(
        key="smartMode", name="Smart Mode",
        value_fn=lambda v: "An" if v else "Aus", **_DIAG,
    ),
)

PACK_SENSORS: tuple[ZendureSensorDescription, ...] = (
    ZendureSensorDescription(
        key="socLevel", name="Ladestand",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZendureSensorDescription(key="power", name="Leistung", **_POWER),
    ZendureSensorDescription(
        key="maxTemp", name="Temperatur",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_deci_kelvin,
    ),
    ZendureSensorDescription(
        key="totalVol", name="Gesamtspannung",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_centi,
    ),
    ZendureSensorDescription(
        key="maxVol", name="Max. Zellspannung",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_centi,
    ),
    ZendureSensorDescription(
        key="minVol", name="Min. Zellspannung",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_centi,
    ),
    ZendureSensorDescription(key="state", name="Status", **_DIAG),
)


class ZendureSensor(ZendureEntity, SensorEntity):
    entity_description: ZendureSensorDescription

    def __init__(self, coordinator: ZendureCoordinator, desc: ZendureSensorDescription) -> None:
        super().__init__(coordinator, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> Any:
        v = self.raw
        if v is None:
            return None
        fn = self.entity_description.value_fn
        return fn(v) if fn else v


def _as_float(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


class ZendureBatteryPowerSensor(ZendureEntity, SensorEntity):
    """Akkuleistung des Geräts: - Laden / + Entladen."""

    _attr_name = "Gesamtleistung"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ZendureCoordinator) -> None:
        super().__init__(coordinator, "batteryPower")

    @property
    def available(self) -> bool:
        props = self.coordinator.data["properties"]
        return self.coordinator.last_update_success and (
            "packInputPower" in props or "outputPackPower" in props
        )

    @property
    def native_value(self) -> float:
        props = self.coordinator.data["properties"]
        return round(
            _as_float(props.get("packInputPower")) - _as_float(props.get("outputPackPower"))
        )


class ZendurePackPowerSensor(ZendureEntity, SensorEntity):
    """Summe der Leistungen aller Akku-Packs eines Geräts (Rohwerte der Packs)."""

    _attr_name = "Packleistung gesamt"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ZendureCoordinator) -> None:
        super().__init__(coordinator, "packPowerTotal")

    def _values(self) -> list[float]:
        return [
            float(p["power"])
            for p in self.coordinator.data["packs"].values()
            if isinstance(p.get("power"), (int, float)) and not isinstance(p.get("power"), bool)
        ]

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and bool(self._values())

    @property
    def native_value(self) -> float | None:
        values = self._values()
        return round(sum(values)) if values else None


class ZendureRemainingCapacitySensor(ZendureEntity, SensorEntity):
    """Restkapazität des Geräts in kWh (Summe Kapazität x SoC je Pack)."""

    _attr_name = "Restkapazität"
    _attr_device_class = SensorDeviceClass.ENERGY_STORAGE
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: ZendureCoordinator) -> None:
        super().__init__(coordinator, "remainingCapacity")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Ändert sich eine Pack-Kapazität, sofort neu berechnen
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._refresh))

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()

    def _remaining(self) -> float | None:
        total = None
        for sn, pack in self.coordinator.data["packs"].items():
            soc = pack.get("socLevel")
            if isinstance(soc, bool) or not isinstance(soc, (int, float)):
                continue
            cap = self.coordinator.pack_capacity.get(sn, DEFAULT_PACK_KWH)
            total = (total or 0.0) + cap * soc / 100
        return total

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._remaining() is not None

    @property
    def native_value(self) -> float | None:
        value = self._remaining()
        return None if value is None else round(value, 2)


class ZendurePackSensor(ZendurePackEntity, SensorEntity):
    entity_description: ZendureSensorDescription

    def __init__(
        self, coordinator: ZendureCoordinator, pack_sn: str, desc: ZendureSensorDescription
    ) -> None:
        super().__init__(coordinator, pack_sn, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> Any:
        v = self.raw
        if v is None:
            return None
        fn = self.entity_description.value_fn
        return fn(v) if fn else v


async def async_setup_entry(
    hass: HomeAssistant, entry: ZendureConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.unique_id == SYSTEM_UNIQUE_ID:
        async_setup_system_sensors(entry, async_add_entities)
        return

    coordinator = entry.runtime_data

    # Nur Sensoren anlegen, deren Property das Gerät tatsächlich meldet
    props = coordinator.data["properties"]
    async_add_entities(
        ZendureSensor(coordinator, d) for d in DEVICE_SENSORS if d.key in props
    )
    if "packInputPower" in props or "outputPackPower" in props:
        async_add_entities([ZendureBatteryPowerSensor(coordinator)])

    known_packs: set[str] = set()
    summary_added: list[bool] = []

    def _add_new_packs() -> None:
        new = [sn for sn in coordinator.data["packs"] if sn not in known_packs]
        if not new:
            return
        known_packs.update(new)
        if not summary_added:
            summary_added.append(True)
            async_add_entities(
                [ZendurePackPowerSensor(coordinator), ZendureRemainingCapacitySensor(coordinator)]
            )
        async_add_entities(
            ZendurePackSensor(coordinator, sn, d)
            for sn in new
            for d in PACK_SENSORS
            if d.key in coordinator.data["packs"][sn]
        )

    _add_new_packs()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_packs))
