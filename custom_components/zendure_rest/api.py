"""Minimaler async REST-Client für die lokale Zendure-API (zenSDK)."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


class ZendureApiError(Exception):
    """Fehler bei der Kommunikation mit dem Gerät."""


class ZendureApi:
    def __init__(self, session: aiohttp.ClientSession, host: str) -> None:
        self._session = session
        self._base = f"http://{host}"
        # Die Geräte sind schwach: Anfragen strikt nacheinander
        self._lock = asyncio.Lock()

    async def get_report(self) -> dict[str, Any]:
        url = f"{self._base}/properties/report"
        async with self._lock:
            try:
                async with asyncio.timeout(10):
                    resp = await self._session.get(url)
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)
            except (TimeoutError, aiohttp.ClientError, ValueError) as err:
                raise ZendureApiError(f"GET {url} fehlgeschlagen: {err}") from err
        if not isinstance(data, dict):
            raise ZendureApiError("Unerwartete Antwort vom Gerät")
        return data

    async def write_properties(self, sn: str, properties: dict[str, Any]) -> None:
        url = f"{self._base}/properties/write"
        async with self._lock:
            try:
                async with asyncio.timeout(10):
                    resp = await self._session.post(
                        url, json={"sn": sn, "properties": properties}
                    )
                    resp.raise_for_status()
            except (TimeoutError, aiohttp.ClientError) as err:
                raise ZendureApiError(f"POST {url} fehlgeschlagen: {err}") from err
