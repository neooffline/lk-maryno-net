"""API client for Maryno.net."""
import asyncio
import logging
import ssl
from typing import Any, Dict, Optional

import aiohttp

from .const import ACCOUNT_URL, BASE_URL, AUTH_URL, POSSIBLE_BASE_URLS

_LOGGER = logging.getLogger(__name__)


class MarynoNetApiClient:
    """API client for Maryno.net customer portal.

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
        """Authenticate with Maryno.net."""
        if not self.session:
            await self._create_session()

        try:
            # First, try to find a working base URL
            working_url = await self._find_working_base_url()
            if working_url:
                self.base_url = working_url
            else:
                _LOGGER.warning("No working base URL found, using default: %s", self.base_url)

            # Try to access user data directly (may not require authentication)
            test_url = f"{self.base_url}/api/user/all"
            async with self.session.get(test_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    _LOGGER.info("Successfully authenticated with Maryno.net at %s", self.base_url)
                    self._authenticated = True
                    return

            # If direct access fails, try login
            await self._perform_login()

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

                await self.authenticate()
            else:
                raise

    async def _perform_login(self) -> None:
        """Perform login to obtain session cookies."""
        _LOGGER.debug("Attempting authentication with URL: %s", AUTH_URL)

        # Send login data as JSON
        login_data = {
            "username": self.username,
            "password": self.password,
        }

        try:
            async with self.session.post(
                AUTH_URL,
                json=login_data,
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=True
            ) as response:
                _LOGGER.debug("Auth response status: %s", response.status)

                if response.status not in [200, 302]:
                    response_text = await response.text()
                    _LOGGER.debug("Auth response: %s", response_text)
                    raise Exception(f"Authentication failed: {response.status} - {response_text}")

                # Check if we got session cookies
                cookies = list(self.session.cookie_jar)
                if cookies:
                    _LOGGER.debug("Session cookies obtained: %s", [f"{cookie.key}={cookie.value[:20]}..." for cookie in cookies])

                    # Look for expected cookies like connect.sid, XSRF-TOKEN
                    has_session = any(cookie.key in ['connect.sid', 'session', 'sessionid'] for cookie in cookies)
                    has_xsrf = any(cookie.key == 'XSRF-TOKEN' for cookie in cookies)

                    if has_session:
                        _LOGGER.debug("Session cookie found, authentication likely successful")
                    if has_xsrf:
                        _LOGGER.debug("XSRF token found")

                # Verify authentication by trying to access user data
                test_url = f"{self.base_url}/api/user/all"
                async with self.session.get(test_url, timeout=aiohttp.ClientTimeout(total=10)) as test_response:
                    if test_response.status == 200:
                        self._authenticated = True
                        _LOGGER.info("Successfully authenticated with Maryno.net at %s", self.base_url)
                        return
                    else:
                        test_text = await test_response.text()
                        _LOGGER.debug("Authentication test failed: %s - %s", test_response.status, test_text[:200])
                        raise Exception("Authentication succeeded but API access failed")

        except Exception as ex:
            _LOGGER.error("Authentication failed: %s", ex)
            raise

    async def get_account_info(self) -> Dict[str, Any]:
        """Get account information."""
        if not self._authenticated:
            await self.authenticate()

        if not self.session:
            raise Exception("Session not initialized")

        # Prepare headers with CSRF token if available
        headers = {}
        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token
            _LOGGER.debug("Using XSRF token for API requests")

        try:
            # Get user info (balance, customer number, etc.)
            user_url = f"{self.base_url}/api/user/all"
            _LOGGER.debug("Fetching user info from: %s", user_url)

            async with self.session.get(user_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                _LOGGER.debug("User info response status: %s", response.status)

                if response.status != 200:
                    response_text = await response.text()
                    _LOGGER.debug("User info response: %s", response_text)
                    raise Exception(f"Failed to get user info: {response.status} - {response_text}")

                user_data = await response.json()
                _LOGGER.debug("User data received: %s", user_data)

            # Get IP addresses
            accounts_url = f"{self.base_url}/api/accounts"
            _LOGGER.debug("Fetching accounts info from: %s", accounts_url)

            async with self.session.get(accounts_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as accounts_response:
                _LOGGER.debug("Accounts response status: %s", accounts_response.status)

                ip_addresses = []
                if accounts_response.status == 200:
                    accounts_data = await accounts_response.json()
                    _LOGGER.debug("Accounts data received: %s", accounts_data)

                    # Extract IP addresses from accounts data
                    if isinstance(accounts_data, list):
                        ip_addresses = [account.get("ip_address") for account in accounts_data if account.get("ip_address")]
                else:
                    _LOGGER.warning("Failed to get IP addresses: %s", accounts_response.status)

            # Get bonus info
            bonus_url = f"{self.base_url}/api/gbonus/info"
            _LOGGER.debug("Fetching bonus info from: %s", bonus_url)

            bonus_balance = 0
            try:
                async with self.session.get(bonus_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as bonus_response:
                    _LOGGER.debug("Bonus response status: %s", bonus_response.status)

                    if bonus_response.status == 200:
                        bonus_data = await bonus_response.json()
                        _LOGGER.debug("Bonus data received: %s", bonus_data)
                        bonus_balance = bonus_data.get("n_bonus", 0)
            except Exception as ex:
                _LOGGER.debug("Failed to get bonus info: %s", ex)

            # Extract the required information from user_data
            return {
                "balance": float(user_data.get("balance", 0)),
                "customer_number": str(user_data.get("number", "")),
                "ip_addresses": ip_addresses,
                "bonus_balance": float(bonus_balance),
            }

        except Exception as ex:
            _LOGGER.error("Failed to get account info: %s", ex)
            raise

    def _get_xsrf_token(self) -> Optional[str]:
        """Extract XSRF token from cookies."""
        for cookie in self.session.cookie_jar:
            if cookie.key == 'XSRF-TOKEN':
                return cookie.value
        return None