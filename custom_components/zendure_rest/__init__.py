"""Zendure REST (lokal) – Home-Assistant-Integration."""
from __future__ import annotations

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import ZendureApi
from .const import DOMAIN, SIGNAL_UPDATE, SYSTEM_UNIQUE_ID
from .coordinator import ZendureConfigEntry, ZendureCoordinator

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT, Platform.SWITCH]
SYSTEM_PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.unique_id == SYSTEM_UNIQUE_ID:
        from .system import SystemManager

        entry.runtime_data = SystemManager(hass, entry)
        await hass.config_entries.async_forward_entry_setups(entry, SYSTEM_PLATFORMS)
        return True

    api = ZendureApi(async_get_clientsession(hass), entry.data[CONF_HOST])
    coordinator = ZendureCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Bei jeder Aktualisierung (und beim Entladen) den System Manager benachrichtigen
    entry.async_on_unload(
        coordinator.async_add_listener(lambda: async_dispatcher_send(hass, SIGNAL_UPDATE))
    )
    entry.async_on_unload(lambda: async_dispatcher_send(hass, SIGNAL_UPDATE))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))

    # System Manager einmalig automatisch anlegen
    if not any(
        e.unique_id == SYSTEM_UNIQUE_ID for e in hass.config_entries.async_entries(DOMAIN)
    ):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data={}
            )
        )
    return True


async def _reload(hass: HomeAssistant, entry: ZendureConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    platforms = SYSTEM_PLATFORMS if entry.unique_id == SYSTEM_UNIQUE_ID else PLATFORMS
    return await hass.config_entries.async_unload_platforms(entry, platforms)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Wird das letzte Gerät entfernt, verschwindet auch der System Manager."""
    if entry.unique_id == SYSTEM_UNIQUE_ID:
        return
    entries = hass.config_entries.async_entries(DOMAIN)
    if any(e.unique_id != SYSTEM_UNIQUE_ID and e.entry_id != entry.entry_id for e in entries):
        return
    for e in entries:
        if e.unique_id == SYSTEM_UNIQUE_ID:
            hass.async_create_task(hass.config_entries.async_remove(e.entry_id))
