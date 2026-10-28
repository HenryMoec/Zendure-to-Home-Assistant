"""Konstanten für Zendure REST."""
DOMAIN = "zendure_rest"
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 10  # Sekunden
MIN_SCAN_INTERVAL = 5

SYSTEM_UNIQUE_ID = "system_manager"
SIGNAL_UPDATE = f"{DOMAIN}_update"
DEFAULT_PACK_KWH = 2.88  # Standard-Kapazität eines Akku-Packs in kWh
SYNC_RETRY_SECONDS = 60  # Mindestabstand zwischen automatischen Korrekturversuchen
