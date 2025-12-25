"""LK Марьино.net integration for Home Assistant."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api import MarinoNetApiClient
from .const import DOMAIN, PLATFORMS
from .coordinator import MarinoNetDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LK Марьино.net from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create API client
    api_client = MarinoNetApiClient(
        username=entry.data["username"],
        password=entry.data["password"],
        verify_ssl=entry.data.get("verify_ssl", True),
    )

    # Test the API connection
    try:
        await api_client.authenticate()
    except Exception as ex:
        raise ConfigEntryNotReady(f"Failed to authenticate: {ex}") from ex

    # Create update coordinator
    coordinator = MarinoNetDataUpdateCoordinator(hass, api_client)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
