"""API client for Maryno.net."""
import asyncio
import logging
import ssl
import time
import urllib.parse
from typing import Any, Dict, Optional

import aiohttp
from yarl import URL

from .const import ACCOUNT_URL, BASE_URL, AUTH_URL, POSSIBLE_BASE_URLS

_LOGGER = logging.getLogger(__name__)

class MarynoNetApiClient:
    """API client for Maryno.net customer portal."""

    def __init__(self, username: str, password: str, verify_ssl: bool = True) -> None:
        """Initialize the API client."""
        self.username = username
        self.password = password
        self.session: Optional[aiohttp.ClientSession] = None
        self._authenticated = False
        self.verify_ssl = verify_ssl
        self.base_url = BASE_URL
        self._connector = None
        self._session_expiration = None

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
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            self._connector = aiohttp.TCPConnector(ssl=ssl_context)

        self.session = aiohttp.ClientSession(connector=self._connector)

    def _get_browser_headers(self) -> Dict[str, str]:
        """Get browser-like headers with the most recent XSRF token from cookies."""
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru,en-US;q=0.9,en;q=0.8",
            "dnt": "1",
            "origin": self.base_url,
            "referer": f"{self.base_url}/",
            "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }

        # Извлекаем актуальный токен прямо из CookieJar перед запросом
        if self.session:
            for cookie in self.session.cookie_jar:
                if cookie.key == 'XSRF-TOKEN':
                    token = urllib.parse.unquote(cookie.value)
                    headers['x-xsrf-token'] = token
                    break
        
        return headers

    def _update_xsrf_token_from_headers(self, headers) -> None:
        """Manually update XSRF token if sent in Set-Cookie header."""
        set_cookie = headers.get('Set-Cookie', '')
        if 'XSRF-TOKEN=' in set_cookie:
            for part in set_cookie.split(';'):
                if part.strip().startswith('XSRF-TOKEN='):
                    token_value = part.strip().split('=', 1)[1]
                    self.session.cookie_jar.update_cookies(
                        {'XSRF-TOKEN': token_value}, 
                        URL(self.base_url)
                    )
                    _LOGGER.debug("Updated XSRF token from headers")
                    break

    async def authenticate(self) -> None:
        """Authenticate with maryno.net."""
        if not self.session:
            await self._create_session()

        try:
            # 1. Сначала заходим на главную, чтобы получить начальные куки
            async with self.session.get(self.base_url, timeout=10) as resp:
                self._update_xsrf_token_from_headers(resp.headers)

            # 2. Логин
            login_data = {"username": self.username, "password": self.password}
            auth_headers = self._get_browser_headers()
            auth_headers["content-type"] = "application/json"
            auth_headers["referer"] = f"{self.base_url}/auth"

            async with self.session.post(
                AUTH_URL, 
                json=login_data, 
                headers=auth_headers, 
                timeout=30
            ) as response:
                if response.status not in [200, 304]:
                    text = await response.text()
                    raise Exception(f"Auth failed: {response.status} - {text}")

                res_json = await response.json()
                self._session_expiration = res_json.get('expiration') or res_json.get('expires')
                self._authenticated = True
                _LOGGER.info("Successfully authenticated")

        except Exception as ex:
            _LOGGER.error("Authentication error: %s", ex)
            raise

    async def get_account_info(self) -> Dict[str, Any]:
        """Get account information with retry on 401."""
        if not self._authenticated:
            await self.authenticate()

        # Минимальный "прогрев" сессии перед запросом данных
        headers = self._get_browser_headers()
        try:
            # Заходим на dashboard, чтобы подтвердить активность сессии
            async with self.session.get(f"{self.base_url}/dashboard", headers=headers) as resp:
                self._update_xsrf_token_from_headers(resp.headers)
            
            await asyncio.sleep(0.5)

            # Основной запрос данных
            user_url = f"{self.base_url}/api/user/all"
            api_headers = self._get_browser_headers()
            api_headers['referer'] = f"{self.base_url}/dashboard"

            async with self.session.get(user_url, headers=api_headers, timeout=30) as response:
                if response.status == 401:
                    _LOGGER.warning("401 Unauthorized. Session lost, retrying auth...")
                    self._authenticated = False
                    await self.authenticate()
                    return await self.get_account_info()

                if response.status not in [200, 304]:
                    raise Exception(f"API Error: {response.status}")

                user_data = await response.json()
                
                return {
                    "balance": float(user_data.get("balance", 0.0)),
                    "customer_number": str(user_data.get("contract_num", user_data.get("contract", ""))),
                    "ip_addresses": [],
                    "bonus_balance": float(user_data.get("bonusBalance", 0.0)),
                }

        except Exception as ex:
            _LOGGER.error("Failed to get account info: %s", ex)
            raise