"""Stromkostentracker Home Assistant integration."""

from pathlib import Path

from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .websocket import websocket_get_month_data, websocket_get_year_data

LOVELACE_URL_BASE = "/stromkostentracker_static"
PLATFORMS = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration."""
    websocket_api.async_register_command(hass, websocket_get_month_data)
    websocket_api.async_register_command(hass, websocket_get_year_data)
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                f"{LOVELACE_URL_BASE}/stromkostentracker-card.js",
                str(Path(__file__).parent / "lovelace" / "stromkostentracker-card.js"),
                cache_headers=False,
            )
        ]
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the integration platforms."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
