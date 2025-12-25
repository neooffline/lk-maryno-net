"""API client for Marino.net."""
import asyncio
import logging
import ssl
from typing import Any, Dict, Optional

import aiohttp

from .const import ACCOUNT_URL, BASE_URL, LOGIN_URL, POSSIBLE_BASE_URLS

_LOGGER = logging.getLogger(__name__)


class MarinoNetApiClient:
    """API client for Marino.net customer portal.

    Note: This implementation handles SSL certificate issues that may occur
    with some ISP portals. SSL verification can be disabled if necessary.
    """

    def __init__(self, username: str, password: str, verify_ssl: bool = True) -> None:
        """Initialize the API client."""
        self.username = username
        self.password = password
        self.session = None
        self._authenticated = False
        self.verify_ssl = verify_ssl
        self.base_url = BASE_URL
        self._connector = None

    async def __aenter__(self):
        """Enter async context."""
        await self._create_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        if self.session:
            await self.session.close()

    async def _create_session(self) -> None:
        """Create aiohttp session with appropriate SSL settings."""
        if self.verify_ssl:
            self._connector = aiohttp.TCPConnector()
        else:
            # Create SSL context that doesn't verify certificates
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            self._connector = aiohttp.TCPConnector(ssl=ssl_context)

        self.session = aiohttp.ClientSession(connector=self._connector)

    async def _try_base_url(self, base_url: str) -> bool:
        """Try to connect to a specific base URL."""
        try:
            test_url = f"{base_url}/"
            _LOGGER.debug("Testing URL: %s", test_url)

            async with self.session.get(test_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                _LOGGER.debug("Response status: %s, URL: %s", response.status, response.url)
                return response.status < 400

        except Exception as ex:
            _LOGGER.debug("Failed to connect to %s: %s", base_url, ex)
            return False

    async def _find_working_base_url(self) -> Optional[str]:
        """Find a working base URL from the list of possible URLs."""
        if not self.session:
            await self._create_session()

        for base_url in POSSIBLE_BASE_URLS:
            if await self._try_base_url(base_url):
                _LOGGER.info("Found working base URL: %s", base_url)
                return base_url

        return None

    async def authenticate(self) -> None:
        """Authenticate with Marino.net."""
        if not self.session:
            await self._create_session()

        try:
            # First, try to find a working base URL
            working_url = await self._find_working_base_url()
            if working_url:
                self.base_url = working_url
            else:
                _LOGGER.warning("No working base URL found, using default: %s", self.base_url)

            # Try authentication with current base_url
            await self._perform_authentication()

        except Exception as ex:
            # If SSL verification fails, try with SSL disabled
            if "CERTIFICATE_VERIFY_FAILED" in str(ex) or "SSL" in str(ex):
                _LOGGER.warning("SSL certificate verification failed, trying with SSL verification disabled")
                self.verify_ssl = False
                await self.session.close()
                await self._create_session()

                # Try again with SSL disabled
                working_url = await self._find_working_base_url()
                if working_url:
                    self.base_url = working_url

                await self._perform_authentication()
            else:
                raise

    async def _perform_authentication(self) -> None:
        """Perform the actual authentication."""
        login_url = f"{self.base_url}/login"
        account_url = f"{self.base_url}/api/account"

        _LOGGER.debug("Attempting authentication with base URL: %s", self.base_url)

        try:
            # This is a placeholder implementation
            # Actual implementation will depend on Marino.net's authentication method

            # For REST API approach:
            auth_data = {
                "username": self.username,
                "password": self.password,
            }

            async with self.session.post(login_url, json=auth_data, timeout=aiohttp.ClientTimeout(total=30)) as response:
                _LOGGER.debug("Login response status: %s", response.status)

                if response.status != 200:
                    response_text = await response.text()
                    _LOGGER.debug("Login response: %s", response_text)
                    raise Exception(f"Login failed: {response.status} - {response_text}")

                # Check response for success
                data = await response.json()
                if not data.get("success", False):
                    raise Exception("Invalid credentials")

            self._authenticated = True
            _LOGGER.info("Successfully authenticated with Marino.net at %s", self.base_url)

        except Exception as ex:
            _LOGGER.error("Authentication failed: %s", ex)
            raise

    async def get_account_info(self) -> Dict[str, Any]:
        """Get account information."""
        if not self._authenticated:
            await self.authenticate()

        if not self.session:
            raise Exception("Session not initialized")

        try:
            account_url = f"{self.base_url}/api/account"
            _LOGGER.debug("Fetching account info from: %s", account_url)

            async with self.session.get(account_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                _LOGGER.debug("Account info response status: %s", response.status)

                if response.status != 200:
                    response_text = await response.text()
                    _LOGGER.debug("Account info response: %s", response_text)
                    raise Exception(f"Failed to get account info: {response.status} - {response_text}")

                # Parse the response - adapt based on actual API
                data = await response.json()
                _LOGGER.debug("Account data received: %s", data)

                # Extract the required information - adapt field names as needed
                return {
                    "balance": float(data.get("balance", 0)),
                    "customer_number": str(data.get("customer_number", "")),
                    "ip_addresses": data.get("ip_addresses", []),
                    "bonus_balance": float(data.get("bonus_balance", 0)),
                }

        except Exception as ex:
            _LOGGER.error("Failed to get account info: %s", ex)
            raise