"""Config flow: credentials, then the site(s) to add. One entry per site."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_IMPORT,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import build_api
from .api import CosysenseAuthError, CosysenseError
from .const import (
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_LEVELS,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_SITE_NAME,
    CONF_SITE_UUID,
    CONF_SITES,
    CONF_STALE_HOURS,
    DEFAULT_BASE_URL,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STALE_HOURS,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_SECRET = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _credentials_schema(advanced: bool, defaults: Mapping[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    fields: dict[Any, Any] = {
        vol.Required(CONF_CLIENT_ID, default=defaults.get(CONF_CLIENT_ID, vol.UNDEFINED)): str,
        vol.Required(CONF_REFRESH_TOKEN): _SECRET,
    }
    if advanced:
        fields[vol.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL)] = str
        fields[vol.Optional(CONF_REGION, default=DEFAULT_REGION)] = str
    return vol.Schema(fields)


class CosysenseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one or more Cosysense sites."""

    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, Any] = {}
        self._sites: list[dict[str, str]] = []

    async def _validate(self, data: dict[str, Any]) -> tuple[list[dict[str, str]], str | None]:
        """Sites the credentials reach, and an error key when they fail."""
        if not str(data.get(CONF_BASE_URL, "")).startswith("https://"):
            return [], "https_required"
        api = build_api(self.hass, data)
        try:
            await api.refresh()
            return await api.sites(), None
        except CosysenseAuthError:
            return [], "invalid_auth"
        except CosysenseError:
            return [], "cannot_connect"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        advanced = bool(self.show_advanced_options)
        if user_input is not None:
            data = {CONF_BASE_URL: DEFAULT_BASE_URL, CONF_REGION: DEFAULT_REGION, **user_input}
            sites, error = await self._validate(data)
            if error:
                errors["base"] = error
            else:
                configured = {e.unique_id for e in self._async_current_entries()}
                self._sites = [s for s in sites if s["site_uuid"] not in configured]
                if not self._sites:
                    return self.async_abort(reason="no_sites" if not sites else "already_configured")
                self._credentials = data
                return await self.async_step_site()
        return self.async_show_form(
            step_id="user", data_schema=_credentials_schema(advanced), errors=errors,
        )

    async def async_step_site(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        chosen = [s for s in self._sites if s["site_uuid"] in (user_input or {}).get(CONF_SITES, [])]
        if user_input is not None and not chosen:
            errors["base"] = "no_site_selected"
        elif user_input is not None:
            first, rest = chosen[0], chosen[1:]
            for site in rest:
                self.hass.async_create_task(self.hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": SOURCE_IMPORT}, data=self._entry_data(site),
                ))
            await self.async_set_unique_id(first["site_uuid"])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=first["name"], data=self._entry_data(first))
        options = [SelectOptionDict(value=s["site_uuid"], label=s["name"]) for s in self._sites]
        return self.async_show_form(
            step_id="site",
            data_schema=vol.Schema({
                vol.Required(CONF_SITES, default=[self._sites[0]["site_uuid"]]): SelectSelector(
                    SelectSelectorConfig(options=options, multiple=True)
                ),
            }),
            errors=errors,
        )

    def _entry_data(self, site: dict[str, str]) -> dict[str, Any]:
        return {**self._credentials, CONF_SITE_UUID: site["site_uuid"], CONF_SITE_NAME: site["name"]}

    async def async_step_import(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Further sites picked in the same user flow."""
        await self.async_set_unique_id(data[CONF_SITE_UUID])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=data[CONF_SITE_NAME], data=data)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            sites, error = await self._validate(data)
            if error:
                errors["base"] = error
            elif entry.data[CONF_SITE_UUID] not in {s["site_uuid"] for s in sites}:
                errors["base"] = "site_not_granted"
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_credentials_schema(False, entry.data),
            description_placeholders={"site": entry.data.get(CONF_SITE_NAME, "")},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CosysenseOptionsFlow()


class CosysenseOptionsFlow(OptionsFlow):
    """Poll interval, staleness and which buildings and levels to show."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            user_input[CONF_STALE_HOURS] = int(user_input[CONF_STALE_HOURS])
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        coordinator = getattr(self.config_entry, "runtime_data", None)
        levels = list(getattr(coordinator, "all_levels", []) or [])
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): NumberSelector(NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, step=10,
                    unit_of_measurement="s", mode=NumberSelectorMode.BOX,
                )),
                vol.Required(
                    CONF_STALE_HOURS, default=options.get(CONF_STALE_HOURS, DEFAULT_STALE_HOURS),
                ): NumberSelector(NumberSelectorConfig(
                    min=1, max=48, step=1, unit_of_measurement="h", mode=NumberSelectorMode.BOX,
                )),
                vol.Optional(CONF_LEVELS, default=options.get(CONF_LEVELS, [])): SelectSelector(
                    SelectSelectorConfig(options=levels, multiple=True)
                ),
            }),
        )
