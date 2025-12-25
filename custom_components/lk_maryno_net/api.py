"""API client for Maryno.net."""
import asyncio
import logging
import ssl
from typing import Any, Dict, Optional

import aiohttp
from yarl import URL

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
            test_url = f"{self.base_url}/api/user/contract"
            test_headers = self._get_browser_headers()
            async with self.session.get(test_url, headers=test_headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status in [200, 304]:
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
            "referer": "https://lk.maryno.net/auth",
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
                _LOGGER.info("Auth response body: %s", response_text)

                if response.status not in [200, 304]:
                    raise Exception(f"Authentication failed: {response.status} - {response_text}")

                # Parse auth response for expiration and session info
                try:
                    import json
                    auth_data = json.loads(response_text)
                    _LOGGER.debug("Auth response JSON: %s", auth_data)
                    
                    # Check for expiration date in auth response
                    if isinstance(auth_data, dict) and 'expiration' in auth_data:
                        self._session_expiration = auth_data['expiration']
                        _LOGGER.info("Session expiration: %s", self._session_expiration)
                    elif isinstance(auth_data, dict) and 'expires' in auth_data:
                        self._session_expiration = auth_data['expires']
                        _LOGGER.info("Session expires: %s", self._session_expiration)
                except Exception as json_ex:
                    _LOGGER.debug("Could not parse auth response as JSON: %s", json_ex)

                # Check if we got session cookies
                cookies = list(self.session.cookie_jar)
                if cookies:
                    _LOGGER.info("All session cookies after auth: %s", [(cookie.key, cookie.value[:30] + "..." if len(cookie.value) > 30 else cookie.value) for cookie in cookies])

                    # Look for expected cookies like connect.sid, XSRF-TOKEN
                    has_session = any(cookie.key in ['connect.sid', 'session', 'sessionid'] for cookie in cookies)
                    has_xsrf = any(cookie.key == 'XSRF-TOKEN' for cookie in cookies)

                    if has_session:
                        _LOGGER.info("Session cookie found, authentication likely successful")
                    if has_xsrf:
                        _LOGGER.info("XSRF token found")

                # Check session expiration before proceeding
                if not self._check_session_expiration():
                    raise Exception("Session has expired, please re-authenticate")

                # Step 1: Access contract page first (as discovered by user)
                _LOGGER.debug("Step 1: Accessing contract page to establish session...")
                contract_page_url = f"{self.base_url}/contract"
                async with self.session.get(contract_page_url, headers=self._get_browser_headers(), timeout=aiohttp.ClientTimeout(total=10)) as contract_response:
                    _LOGGER.debug("Contract page response status: %s", contract_response.status)
                    # Update XSRF token from contract page response
                    self._update_xsrf_token_from_headers(contract_response.headers)
                    
                    if contract_response.status in [200, 304]:
                        _LOGGER.debug("Contract page access successful")
                    else:
                        _LOGGER.warning("Contract page access failed: %s", contract_response.status)

                # Small delay
                await asyncio.sleep(0.5)

                # Step 2: Access main page (as per user discovery)
                _LOGGER.debug("Step 2: Accessing main page...")
                main_url = f"{self.base_url}/"
                async with self.session.get(main_url, headers=self._get_browser_headers(), timeout=aiohttp.ClientTimeout(total=10)) as main_response:
                    _LOGGER.debug("Main page response status: %s", main_response.status)
                    # Update XSRF token from main page response
                    self._update_xsrf_token_from_headers(main_response.headers)
                    
                    if main_response.status in [200, 304]:
                        _LOGGER.debug("Main page access successful")
                    else:
                        _LOGGER.warning("Main page access failed: %s", main_response.status)

                # Small delay
                await asyncio.sleep(0.5)

                # Step 3: Access contract page again before API calls (as per user discovery)
                _LOGGER.debug("Step 3: Accessing contract page again...")
                async with self.session.get(contract_page_url, headers=self._get_browser_headers(), timeout=aiohttp.ClientTimeout(total=10)) as contract_response2:
                    _LOGGER.debug("Contract page (second) response status: %s", contract_response2.status)
                    # Update XSRF token from second contract page response
                    self._update_xsrf_token_from_headers(contract_response2.headers)
                    
                    if contract_response2.status in [200, 304]:
                        _LOGGER.debug("Contract page (second) access successful")
                    else:
                        _LOGGER.warning("Contract page (second) access failed: %s", contract_response2.status)

                # Small delay
                await asyncio.sleep(0.5)

                # Verify authentication by trying to access user data with proper headers
                test_url = f"{self.base_url}/api/user/contract"
                test_headers = self._get_browser_headers()
                _LOGGER.debug("Testing API access with URL: %s", test_url)
                _LOGGER.debug("Testing API access with headers: %s", test_headers)
                async with self.session.get(test_url, headers=test_headers, timeout=aiohttp.ClientTimeout(total=10)) as test_response:
                    _LOGGER.info("API test response status: %s", test_response.status)
                    _LOGGER.info("API test response headers: %s", dict(test_response.headers))                    
                    # Update XSRF token from response headers
                    self._update_xsrf_token_from_headers(test_response.headers)
                    
                    test_response_text = await test_response.text()
                    _LOGGER.info("API test response body: %s", test_response_text[:500])

                    if test_response.status in [200, 304]:
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
            _LOGGER.info("Not authenticated, performing authentication")
            await self.authenticate()

        if not self.session:
            raise Exception("Session not initialized")

        # Check session expiration before proceeding
        if not self._check_session_expiration():
            _LOGGER.info("Session expired, re-authenticating")
            self._authenticated = False
            await self.authenticate()

        # Prepare headers to match browser requests
        headers = self._get_browser_headers()

        try:
            # Step 1: Access contract page first (as per user discovery)
            _LOGGER.debug("Accessing contract page before API call...")
            contract_page_url = f"{self.base_url}/contract"
            async with self.session.get(contract_page_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as contract_response:
                _LOGGER.info("Contract page response status: %s", contract_response.status)
                _LOGGER.debug("Contract page response headers: %s", dict(contract_response.headers))
                # Update XSRF token from contract page response
                self._update_xsrf_token_from_headers(contract_response.headers)
                
                if contract_response.status not in [200, 304]:
                    _LOGGER.warning("Contract page access failed with status: %s", contract_response.status)

            # Small delay
            await asyncio.sleep(0.5)

            # Step 2: Access main page (as per user discovery)
            _LOGGER.debug("Accessing main page before API call...")
            main_url = f"{self.base_url}/"
            async with self.session.get(main_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as main_response:
                _LOGGER.info("Main page response status: %s", main_response.status)
                _LOGGER.debug("Main page response headers: %s", dict(main_response.headers))
                # Update XSRF token from main page response
                self._update_xsrf_token_from_headers(main_response.headers)
                
                if main_response.status not in [200, 304]:
                    _LOGGER.warning("Main page access failed with status: %s", main_response.status)

            # Small delay
            await asyncio.sleep(0.5)

            # Step 3: Access contract page again before API calls (as per user discovery)
            _LOGGER.debug("Accessing contract page again before API call...")
            async with self.session.get(contract_page_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as contract_response2:
                _LOGGER.info("Contract page (second) response status: %s", contract_response2.status)
                _LOGGER.debug("Contract page (second) response headers: %s", dict(contract_response2.headers))
                # Update XSRF token from second contract page response
                self._update_xsrf_token_from_headers(contract_response2.headers)
                
                if contract_response2.status not in [200, 304]:
                    _LOGGER.warning("Contract page (second) access failed with status: %s", contract_response2.status)

            # Step 4: Access dashboard/main page to establish full session
            _LOGGER.debug("Accessing dashboard page before API call...")
            dashboard_url = f"{self.base_url}/dashboard"
            async with self.session.get(dashboard_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as dashboard_response:
                _LOGGER.info("Dashboard page response status: %s", dashboard_response.status)
                _LOGGER.debug("Dashboard page response headers: %s", dict(dashboard_response.headers))
                # Update XSRF token from dashboard page response
                self._update_xsrf_token_from_headers(dashboard_response.headers)
                
                if dashboard_response.status not in [200, 304]:
                    _LOGGER.warning("Dashboard page access failed with status: %s", dashboard_response.status)

            # Small delay
            await asyncio.sleep(0.5)

            # First get contract info to establish session
            contract_api_url = f"{self.base_url}/api/user/contract"
            _LOGGER.debug("Fetching contract info from: %s", contract_api_url)
            async with self.session.get(contract_api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as contract_api_response:
                _LOGGER.debug("Contract API response status: %s", contract_api_response.status)
                _LOGGER.debug("Contract API response headers: %s", dict(contract_api_response.headers))
                
                # Update XSRF token from contract API response
                self._update_xsrf_token_from_headers(contract_api_response.headers)
                
                if contract_api_response.status not in [200, 304]:
                    contract_response_text = await contract_api_response.text()
                    _LOGGER.warning("Contract API response: %s", contract_response_text)
                    # Don't fail here, just log warning - some systems might not require this

            # Small delay
            await asyncio.sleep(0.5)

            # Get user info (contains all account details including balance)
            user_url = f"{self.base_url}/api/user/all"
            _LOGGER.debug("Fetching user info from: %s", user_url)
            _LOGGER.debug("Using headers: %s", headers)

            async with self.session.get(user_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                _LOGGER.debug("User response status: %s", response.status)
                _LOGGER.debug("Response headers: %s", dict(response.headers))

                # Update XSRF token from response headers
                self._update_xsrf_token_from_headers(response.headers)

                if response.status not in [200, 304]:
                    response_text = await response.text()
                    _LOGGER.warning("User response: %s", response_text)
                    raise Exception(f"Failed to get user info: {response.status} - {response_text}")

                user_data = await response.json()
                _LOGGER.info("User data received: %s", user_data)

                # Extract customer number
                customer_number = str(user_data.get("contract_num", user_data.get("contract", "")))
                _LOGGER.debug("Extracted customer number: %s", customer_number)

                # Extract balance
                balance = float(user_data.get("balance", 0.0))
                _LOGGER.debug("Extracted balance: %s", balance)

                # Extract bonus balance
                bonus_balance = float(user_data.get("bonusBalance", 0.0))
                _LOGGER.debug("Extracted bonus balance: %s", bonus_balance)

            # Get IP addresses (try subscriber endpoint) - keeping this separate as it might have different data
            ip_addresses = []
            try:
                subscriber_url = f"{self.base_url}/api/acoount"
                _LOGGER.debug("Fetching subscriber info from: %s", subscriber_url)

                async with self.session.get(subscriber_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as subscriber_response:
                    _LOGGER.info("Subscriber response status: %s", subscriber_response.status)

                    if subscriber_response.status in [200, 304]:
                        subscriber_data = await subscriber_response.json()
                        _LOGGER.info("Subscriber data received: %s", subscriber_data)
                        
                        # Extract IP addresses if available
                        # TODO: Parse IP addresses from subscriber data structure
            except Exception as ex:
                _LOGGER.error("Failed to get subscriber info: %s", ex)

            # Extract the required information from user_data
            return {
                "balance": float(balance),
                "customer_number": customer_number,
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
            _LOGGER.info("Using XSRF token: %s", xsrf_token)

        return headers

    def _get_xsrf_token(self) -> Optional[str]:
        """Extract XSRF token from cookies."""
        import urllib.parse

        for cookie in self.session.cookie_jar:
            if cookie.key == 'XSRF-TOKEN':
                # URL decode the token as it might be encoded in the cookie
                decoded_token = urllib.parse.unquote(cookie.value)
                _LOGGER.info("Found XSRF token (raw): %s, decoded: %s", cookie.value, decoded_token)
                return decoded_token
        return None
    def _check_session_expiration(self) -> bool:
        """Check if the current session is still valid based on expiration."""
        if not hasattr(self, '_session_expiration') or not self._session_expiration:
            return True  # No expiration info, assume valid
        
        try:
            import time
            current_time = int(time.time() * 1000)  # Current time in milliseconds
            
            # If expiration is a string, try to parse it
            if isinstance(self._session_expiration, str):
                # Try different date formats
                try:
                    # ISO format
                    import datetime
                    expiration_dt = datetime.datetime.fromisoformat(self._session_expiration.replace('Z', '+00:00'))
                    expiration_time = int(expiration_dt.timestamp() * 1000)
                except:
                    # Try as timestamp
                    expiration_time = int(self._session_expiration)
            else:
                expiration_time = int(self._session_expiration)
            
            if current_time < expiration_time:
                _LOGGER.debug("Session is still valid until: %s", self._session_expiration)
                return True
            else:
                _LOGGER.warning("Session has expired: %s", self._session_expiration)
                self._authenticated = False
                return False
                
        except Exception as ex:
            _LOGGER.debug("Could not check session expiration: %s", ex)
            return True  # Assume valid if we can't check

    def _update_xsrf_token_from_headers(self, headers) -> None:
        """Update XSRF token from response headers."""
        import urllib.parse
        
        set_cookie = headers.get('Set-Cookie', '')
        if 'XSRF-TOKEN=' in set_cookie:
            # Extract token from Set-Cookie header
            cookie_parts = set_cookie.split(';')
            for part in cookie_parts:
                if part.strip().startswith('XSRF-TOKEN='):
                    token_value = part.strip().split('=', 1)[1]
                    decoded_token = urllib.parse.unquote(token_value)
                    
                    # Update the cookie using update_cookies method
                    base_url = URL(self.base_url)
                    self.session.cookie_jar.update_cookies({'XSRF-TOKEN': token_value}, base_url)
                    _LOGGER.info("Updated XSRF token from headers: %s", decoded_token)
                    return