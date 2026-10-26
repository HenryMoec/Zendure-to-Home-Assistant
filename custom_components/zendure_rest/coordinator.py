"""DataUpdateCoordinator: ein Coordinator pro Gerät."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ZendureApi, ZendureApiError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type ZendureConfigEntry = ConfigEntry[ZendureCoordinator]


class ZendureCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    config_entry: ZendureConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ZendureConfigEntry, api: ZendureApi
    ) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.unique_id}",
            config_entry=entry,
            update_interval=timedelta(seconds=interval),
        )
        self.api = api
        self.sn: str = entry.unique_id  # type: ignore[assignment]

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
            raise UpdateFailed(str(err)) from err
        data = dict(self.data)
        data["properties"] = {**data["properties"], **properties}
        self.async_set_updated_data(data)
        await self.async_request_refresh()
