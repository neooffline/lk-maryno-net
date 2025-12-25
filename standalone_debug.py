#!/usr/bin/env python3
"""Standalone debug test script for maryno.net API client."""

import asyncio
import logging
import sys
import os
import aiohttp
import urllib.parse
import ssl

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

_LOGGER = logging.getLogger(__name__)

# Constants
POSSIBLE_BASE_URLS = [
    "https://lk.maryno.net",
    "https://www.maryno.net",
    "https://maryno.net",
    "https://lk.marynunet.ru",
    "https://marynunet.ru",
    "https://my.maryno.net",
]
BASE_URL = "https://lk.maryno.net"
AUTH_URL = f"{BASE_URL}/auth"

class StandaloneMarynoNetApiClient:
    """Standalone API client for maryno.net customer portal."""

    def __init__(self, username: str, password: str, verify_ssl: bool = True):
        """Initialize the API client."""
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.base_url = BASE_URL
        self.session: aiohttp.ClientSession = None
        self._authenticated = False
        self._connector = None

    async def _create_session(self) -> None:
        """Create aiohttp session with proper SSL settings."""
        if self.verify_ssl:
            ssl_context = ssl.create_default_context()
        else:
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

    async def _find_working_base_url(self) -> str:
        """Find a working base URL from the list of possible URLs."""
        if not self.session:
            await self._create_session()

        for base_url in POSSIBLE_BASE_URLS:
            if await self._try_base_url(base_url):
                _LOGGER.info("Found working base URL: %s", base_url)
                return base_url

        return None

    def _get_browser_headers(self) -> dict:
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
            # URL encode the XSRF token for the header
            encoded_xsrf = urllib.parse.quote(xsrf_token)
            headers['x-xsrf-token'] = encoded_xsrf
            _LOGGER.debug("Using XSRF token: %s (encoded: %s)", xsrf_token, encoded_xsrf)

        # Try adding session cookie to Authorization header
        # session_cookie = self._get_session_cookie()
        # if session_cookie:
        #     headers['Authorization'] = f"Bearer {session_cookie}"
        #     _LOGGER.debug("Using session cookie in Authorization header")

        return headers

    def _get_xsrf_token(self):
        """Extract XSRF token from cookies."""
        if not self.session:
            return None

        for cookie in self.session.cookie_jar:
            if cookie.key == 'XSRF-TOKEN':
                # URL decode the token as it might be encoded in the cookie
                decoded_token = urllib.parse.unquote(cookie.value)
                _LOGGER.debug("Found XSRF token (raw): %s, decoded: %s", cookie.value, decoded_token)
                return decoded_token
        return None

    def _get_session_cookie(self):
        """Extract session cookie from cookies."""
        if not self.session:
            return None

        for cookie in self.session.cookie_jar:
            if cookie.key == 'connect.sid':
                _LOGGER.debug("Found session cookie: %s", cookie.value[:30] + "..." if len(cookie.value) > 30 else cookie.value)
                return cookie.value
        return None

    async def authenticate(self):
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

    async def _perform_login(self):
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

                # Try to parse the response as JSON to check for success indicators
                try:
                    import json
                    auth_data = json.loads(response_text)
                    _LOGGER.debug("Auth response JSON: %s", auth_data)
                    # Check if the response indicates success
                    # The user mentioned getting {"type_jur": 0} which might be success
                    if isinstance(auth_data, dict) and 'type_jur' in auth_data:
                        if auth_data.get('type_jur') == 0:
                            _LOGGER.debug("Auth response indicates success (type_jur: 0)")
                        else:
                            _LOGGER.warning("Auth response type_jur: %s", auth_data.get('type_jur'))
                except Exception as json_ex:
                    _LOGGER.debug("Could not parse auth response as JSON: %s", json_ex)

                # Check if we got session cookies
                cookies = list(self.session.cookie_jar)
                if cookies:
                    _LOGGER.debug("All session cookies after auth: %s", [(cookie.key, urllib.parse.unquote(cookie.value)[:50] + "..." if len(cookie.value) > 50 else urllib.parse.unquote(cookie.value)) for cookie in cookies])

                # Small delay to ensure session is fully established
                await asyncio.sleep(0.5)

                # Try to access the main page first to establish session
                _LOGGER.debug("Accessing main page to establish session...")
                main_url = f"{self.base_url}/"
                async with self.session.get(main_url, headers=self._get_browser_headers(), timeout=aiohttp.ClientTimeout(total=10)) as main_response:
                    _LOGGER.debug("Main page response status: %s", main_response.status)
                    if main_response.status == 200:
                        _LOGGER.debug("Main page access successful")
                    else:
                        _LOGGER.debug("Main page access failed: %s", main_response.status)

                # Small additional delay
                await asyncio.sleep(0.5)

                # Access main page to get the full dashboard HTML
                main_page_url = f"{self.base_url}/"
                main_headers = self._get_browser_headers()
                _LOGGER.debug("Accessing main page for HTML analysis: %s", main_page_url)
                
                async with self.session.get(main_page_url, headers=main_headers, timeout=aiohttp.ClientTimeout(total=10)) as main_response:
                    _LOGGER.debug("Main page response status: %s", main_response.status)
                    if main_response.status == 200:
                        main_response_text = await main_response.text()
                        # Save the main page HTML for analysis
                        with open('main_page.html', 'w', encoding='utf-8') as f:
                            f.write(main_response_text)
                        _LOGGER.info("Saved main page HTML to main_page.html for analysis")
                    else:
                        _LOGGER.warning("Failed to access main page: %s", main_response.status)

                # Verify authentication by trying to access user data with proper headers
                test_url = f"{self.base_url}/api/user/contract"
                test_headers = self._get_browser_headers()
                test_headers['content-type'] = 'application/json'
                _LOGGER.debug("Testing API access with URL: %s", test_url)
                _LOGGER.debug("Testing API access with headers: %s", test_headers)
                
                # Debug: check what cookies will be sent
                from yarl import URL
                cookie_header = self.session.cookie_jar.filter_cookies(URL(test_url))
                _LOGGER.debug("Cookies that will be sent: %s", list(cookie_header.items()))
                
                async with self.session.get(test_url, headers=test_headers, timeout=aiohttp.ClientTimeout(total=10)) as test_response:
                    _LOGGER.debug("API test response status: %s", test_response.status)
                    _LOGGER.debug("API test response headers: %s", dict(test_response.headers))
                    test_response_text = await test_response.text()
                    _LOGGER.debug("API test response body: %s", test_response_text[:500])
                    
                    # Save the full HTML response to examine for API endpoints
                    with open('response.html', 'w', encoding='utf-8') as f:
                        f.write(test_response_text)
                    _LOGGER.info("Saved full HTML response to response.html for analysis")

                    if test_response.status == 200:
                        self._authenticated = True
                        _LOGGER.info("Successfully authenticated with maryno.net at %s", self.base_url)
                        return
                    else:
                        raise Exception(f"Authentication succeeded but API access failed (status: {test_response.status})")

        except Exception as ex:
            _LOGGER.error("Authentication failed: %s", ex)
            raise

    async def close(self):
        """Close the session."""
        if self.session:
            await self.session.close()


async def debug_auth():
    """Debug the authentication process."""
    # Replace with your actual credentials for testing
    username = "92"
    password = "77126"

    print(f"Debugging maryno.net API with username: {username}")

    client = StandaloneMarynoNetApiClient(username, password)

    try:
        print("Starting authentication...")
        await client.authenticate()
        print("✓ Authentication successful")

    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await client.close()

    return True


if __name__ == "__main__":
    print("This is a debug script. Please edit the username and password variables with your actual credentials.")
    print("The script will show detailed debug information about the authentication process.")
    print()

    # Uncomment the next line to run the test (after setting credentials)
    success = asyncio.run(debug_auth())