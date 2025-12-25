"""Data update coordinator for LK Марьино.net."""
from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MarinoNetApiClient
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class MarinoNetDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from Marino.net."""

    def __init__(self, hass: HomeAssistant, api_client: MarinoNetApiClient) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api_client = api_client

    async def _async_update_data(self):
        """Update data via library."""
        try:
            return await self.api_client.get_account_info()
        except Exception as ex:
            raise UpdateFailed(f"Error communicating with API: {ex}") from ex