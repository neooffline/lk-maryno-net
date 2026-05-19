"""LK Марьино.net integration for Home Assistant."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api import MarynoNetApiClient
from .const import DOMAIN, PLATFORMS, SCAN_INTERVAL
from .coordinator import MarynoNetDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LK Марьино.net from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    api_client = MarynoNetApiClient(
        username=entry.data["username"],
        password=entry.data["password"],
        verify_ssl=entry.data.get("verify_ssl", True),
    )

    try:
        await api_client.authenticate()
    except Exception as ex:
        raise ConfigEntryNotReady(f"Failed to authenticate: {ex}") from ex

    scan_interval = entry.data.get("scan_interval", SCAN_INTERVAL)
    coordinator = MarynoNetDataUpdateCoordinator(hass, api_client, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.api_client.close()

    return unload_ok
