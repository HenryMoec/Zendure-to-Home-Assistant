"""DataUpdateCoordinator: ein Coordinator pro Gerät."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ZendureApi, ZendureApiError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, SYSTEM_UNIQUE_ID

_LOGGER = logging.getLogger(__name__)

type ZendureConfigEntry = ConfigEntry[ZendureCoordinator]


def _initial_interval(hass: HomeAssistant, entry: ConfigEntry) -> int:
    """Intervall aus dem System Manager; Fallback: früherer Wert am Gerät, dann Standard."""
    for e in hass.config_entries.async_entries(DOMAIN):
        if e.unique_id == SYSTEM_UNIQUE_ID and CONF_SCAN_INTERVAL in e.options:
            return e.options[CONF_SCAN_INTERVAL]
    return entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)


class ZendureCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    config_entry: ZendureConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ZendureConfigEntry, api: ZendureApi
    ) -> None:
        interval = _initial_interval(hass, entry)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.unique_id}",
            config_entry=entry,
            update_interval=timedelta(seconds=interval),
        )
        self.api = api
        self.sn: str = entry.unique_id  # type: ignore[assignment]
        # Kapazität je Pack (kWh), befüllt von den Kapazitäts-Number-Entitäten
        self.pack_capacity: dict[str, float] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            report = await self.api.get_report()
        except ZendureApiError as err:
            raise UpdateFailed(str(err)) from err

        old = self.data or {}
        # Mergen, damit einzelne fehlende Keys Entitäten nicht flackern lassen
        props = {**old.get("properties", {}), **report.get("properties", {})}
        packs = {
            p["sn"]: p for p in report.get("packData", []) if isinstance(p, dict) and "sn" in p
        }
        return {
            "product": report.get("product") or old.get("product"),
            "properties": props,
            "packs": packs,
        }

    async def async_set_properties(self, properties: dict[str, Any]) -> None:
        """Schreibt Properties, übernimmt sie optimistisch und liest danach zurück."""
        try:
            await self.api.write_properties(self.sn, properties)
        except ZendureApiError as err:
            raise HomeAssistantError(
                f"Schreiben auf {self.config_entry.title} fehlgeschlagen: {err}"
            ) from err
        data = dict(self.data)
        data["properties"] = {**data["properties"], **properties}
        self.async_set_updated_data(data)
        await self.async_request_refresh()
