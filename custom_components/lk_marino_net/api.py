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
        """Authenticate with maryno.net."""
        if not self.session:
            await self._create_session()

        try:
            # First, try to find a working base URL
            working_url = await self._find_working_base_url()
            if working_url:
                self.base_url = working_url
            else:
                # If no working URL found, try the auth URL domain as fallback
                from urllib.parse import urlparse
                auth_domain = urlparse(AUTH_URL).scheme + "://" + urlparse(AUTH_URL).netloc
                self.base_url = auth_domain
                _LOGGER.warning("No working base URL found, using auth domain: %s", self.base_url)

            # Try to access user data directly (may not require authentication)
            test_url = f"{self.base_url}/api/user/all"
            test_headers = self._get_browser_headers()
            async with self.session.get(test_url, headers=test_headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    _LOGGER.info("Successfully authenticated with maryno.net at %s", self.base_url)
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
                else:
                    # Use auth domain as fallback
                    from urllib.parse import urlparse
                    auth_domain = urlparse(AUTH_URL).scheme + "://" + urlparse(AUTH_URL).netloc
                    self.base_url = auth_domain

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

        # Use browser-like headers for authentication
        auth_headers = {
            "accept": "application/json, text/plain, */*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ru,en-US;q=0.9,en;q=0.8,bg;q=0.7",
            "content-type": "application/json",
            "dnt": "1",
            "origin": "https://lk.maryno.net",
            "priority": "u=1, i",
            "referer": "https://lk.maryno.net/login",
            "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        }

        try:
            async with self.session.post(
                AUTH_URL,
                json=login_data,
                headers=auth_headers,
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=True
            ) as response:
                _LOGGER.debug("Auth response status: %s", response.status)
                response_text = await response.text()
                _LOGGER.debug("Auth response body: %s", response_text)

                if response.status not in [200, 302]:
                    raise Exception(f"Authentication failed: {response.status} - {response_text}")

                # Check if we got session cookies
                cookies = list(self.session.cookie_jar)
                if cookies:
                    _LOGGER.debug("All session cookies after auth: %s", [(cookie.key, cookie.value[:30] + "..." if len(cookie.value) > 30 else cookie.value) for cookie in cookies])

                    # Look for expected cookies like connect.sid, XSRF-TOKEN
                    has_session = any(cookie.key in ['connect.sid', 'session', 'sessionid'] for cookie in cookies)
                    has_xsrf = any(cookie.key == 'XSRF-TOKEN' for cookie in cookies)

                    if has_session:
                        _LOGGER.debug("Session cookie found, authentication likely successful")
                    if has_xsrf:
                        _LOGGER.debug("XSRF token found")

                # Small delay to ensure session is fully established
                await asyncio.sleep(0.5)

                # Verify authentication by trying to access user data with proper headers
                test_url = f"{self.base_url}/api/user/all"
                test_headers = self._get_browser_headers()
                _LOGGER.debug("Testing API access with URL: %s", test_url)
                _LOGGER.debug("Testing API access with headers: %s", test_headers)
                async with self.session.get(test_url, headers=test_headers, timeout=aiohttp.ClientTimeout(total=10)) as test_response:
                    _LOGGER.debug("API test response status: %s", test_response.status)
                    _LOGGER.debug("API test response headers: %s", dict(test_response.headers))
                    test_response_text = await test_response.text()
                    _LOGGER.debug("API test response body: %s", test_response_text[:500])

                    if test_response.status == 200:
                        self._authenticated = True
                        _LOGGER.info("Successfully authenticated with maryno.net at %s", self.base_url)
                        return
                    else:
                        raise Exception(f"Authentication succeeded but API access failed (status: {test_response.status})")

        except Exception as ex:
            _LOGGER.error("Authentication failed: %s", ex)
            raise

    async def get_account_info(self) -> Dict[str, Any]:
        """Get account information."""
        if not self._authenticated:
            await self.authenticate()

        if not self.session:
            raise Exception("Session not initialized")

        # Prepare headers to match browser requests
        headers = self._get_browser_headers()

        try:
            # Get contract info (contains customer number and other details)
            contract_url = f"{self.base_url}/api/user/contract"
            _LOGGER.debug("Fetching contract info from: %s", contract_url)
            _LOGGER.debug("Using headers: %s", headers)

            async with self.session.get(contract_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                _LOGGER.debug("Contract response status: %s", response.status)
                _LOGGER.debug("Response headers: %s", dict(response.headers))

                if response.status != 200:
                    response_text = await response.text()
                    _LOGGER.debug("Contract response: %s", response_text)
                    raise Exception(f"Failed to get contract info: {response.status} - {response_text}")

                contract_data = await response.json()
                _LOGGER.debug("Contract data received: %s", contract_data)

                # Contract data is an array, get the first contract
                if isinstance(contract_data, list) and len(contract_data) > 0:
                    contract = contract_data[0]
                else:
                    contract = contract_data if isinstance(contract_data, dict) else {}

            # Get IP addresses (try subscriber endpoint)
            ip_addresses = []
            try:
                subscriber_url = f"{self.base_url}/api/user/subscriber"
                _LOGGER.debug("Fetching subscriber info from: %s", subscriber_url)

                async with self.session.get(subscriber_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as subscriber_response:
                    _LOGGER.debug("Subscriber response status: %s", subscriber_response.status)

                    if subscriber_response.status == 200:
                        subscriber_data = await subscriber_response.json()
                        _LOGGER.debug("Subscriber data received: %s", subscriber_data)
                        # TODO: Extract IP addresses from subscriber data
            except Exception as ex:
                _LOGGER.debug("Failed to get subscriber info: %s", ex)

            # Get bonus info (keep existing logic)
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

            # Extract the required information from contract_data
            return {
                "balance": 0.0,  # TODO: Find balance in contract/subscriber/product data
                "customer_number": str(contract.get("contract_num", contract.get("contract", ""))),
                "ip_addresses": ip_addresses,
                "bonus_balance": float(bonus_balance),
            }

        except Exception as ex:
            _LOGGER.error("Failed to get account info: %s", ex)
            raise

    def _get_browser_headers(self) -> Dict[str, str]:
        """Get browser-like headers to match web requests."""
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ru,en-US;q=0.9,en;q=0.8,bg;q=0.7",
            "dnt": "1",
            "origin": "https://lk.maryno.net",
            "priority": "u=1, i",
            "referer": f"{self.base_url}/",
            "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        }

        # Add XSRF token if available
        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['x-xsrf-token'] = xsrf_token
            _LOGGER.debug("Using XSRF token: %s", xsrf_token)

        return headers

    def _get_xsrf_token(self) -> Optional[str]:
        """Extract XSRF token from cookies."""
        import urllib.parse

        for cookie in self.session.cookie_jar:
            if cookie.key == 'XSRF-TOKEN':
                # URL decode the token as it might be encoded in the cookie
                decoded_token = urllib.parse.unquote(cookie.value)
                _LOGGER.debug("Found XSRF token (raw): %s, decoded: %s", cookie.value, decoded_token)
                return decoded_token
        return None