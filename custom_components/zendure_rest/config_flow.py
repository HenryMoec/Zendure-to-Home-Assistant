"""Config- und Options-Flow."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import ZendureApi, ZendureApiError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, MIN_SCAN_INTERVAL


class ZendureConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._title: str | None = None

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Gerät per mDNS gefunden."""
        host = discovery_info.host
        api = ZendureApi(async_get_clientsession(self.hass), host)
        try:
            report = await api.get_report()
        except ZendureApiError:
            return self.async_abort(reason="cannot_connect")
        sn = report.get("sn")
        if not sn:
            return self.async_abort(reason="invalid_response")

        await self.async_set_unique_id(sn)
        # Bereits eingerichtet: nur die (ggf. geänderte) IP nachziehen
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._host = host
        self._title = f"{report.get('product', 'Zendure')} {sn[-4:]}"
        self.context["title_placeholders"] = {"name": self._title}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=self._title, data={CONF_HOST: self._host}
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"name": self._title, "host": self._host},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            api = ZendureApi(async_get_clientsession(self.hass), host)
            try:
                report = await api.get_report()
            except ZendureApiError:
                errors["base"] = "cannot_connect"
            else:
                sn = report.get("sn")
                if not sn:
                    errors["base"] = "invalid_response"
                else:
                    await self.async_set_unique_id(sn)
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                    product = report.get("product", "Zendure")
                    return self.async_create_entry(
                        title=f"{product} {sn[-4:]}", data={CONF_HOST: host}
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return ZendureOptionsFlow()


class ZendureOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        int, vol.Range(min=MIN_SCAN_INTERVAL, max=3600)
                    )
                }
            ),
        )
