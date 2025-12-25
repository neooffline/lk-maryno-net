"""API client for Maryno.net."""
import asyncio
import logging
import ssl
import urllib.parse
from typing import Any, Dict, Optional

import aiohttp
from yarl import URL

from .const import BASE_URL, AUTH_URL

_LOGGER = logging.getLogger(__name__)

class MarynoNetApiClient:
    def __init__(self, username: str, password: str, verify_ssl: bool = True) -> None:
        self.username = username
        self.password = password
        self.session: Optional[aiohttp.ClientSession] = None
        self._authenticated = False
        self.verify_ssl = verify_ssl
        self.base_url = BASE_URL
        self._auth_attempts = 0 # Счетчик для предотвращения цикла

    async def _create_session(self) -> None:
        """Create aiohttp session."""
        if self.session:
            return
            
        conn_kwargs = {}
        if not self.verify_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            conn_kwargs["ssl"] = ssl_context

        connector = aiohttp.TCPConnector(**conn_kwargs)
        # cookie_jar сам управляет куками, включая XSRF-TOKEN
        self.session = aiohttp.ClientSession(connector=connector)

    def _get_headers(self) -> Dict[str, str]:
        """Build headers fetching fresh XSRF token from session cookies."""
        headers = {
            "accept": "application/json, text/plain, */*",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "origin": self.base_url,
            "referer": f"{self.base_url}/",
        }

        # Ищем XSRF-TOKEN в куках сессии
        if self.session:
            for cookie in self.session.cookie_jar:
                if cookie.key == 'XSRF-TOKEN':
                    headers['x-xsrf-token'] = urllib.parse.unquote(cookie.value)
                    break
        return headers

    async def authenticate(self) -> None:
        """Authenticate with minimal steps."""
        await self._create_session()
        
        try:
            # 1. Получаем начальный XSRF токен с главной страницы
            async with self.session.get(self.base_url, timeout=10) as resp:
                _LOGGER.debug("Initial page status: %s", resp.status)

            # 2. Выполняем POST логин
            login_data = {"username": self.username, "password": self.password}
            headers = self._get_headers()
            headers["content-type"] = "application/json"

            async with self.session.post(AUTH_URL, json=login_data, headers=headers, timeout=20) as resp:
                if resp.status not in [200, 304]:
                    text = await resp.text()
                    raise Exception(f"Login failed ({resp.status}): {text}")
                
                _LOGGER.info("Authentication successful")
                self._authenticated = True
                self._auth_attempts = 0 # Сброс счетчика при успехе

        except Exception as ex:
            _LOGGER.error("Auth error: %s", ex)
            self._authenticated = False
            raise

    async def get_account_info(self) -> Dict[str, Any]:
        """Fetch data with a simple structure."""
        if not self._authenticated:
            await self.authenticate()

        # Идем СРАЗУ к API, минуя dashboard, чтобы не провоцировать сброс токена
        user_url = f"{self.base_url}/api/user/all"
        headers = self._get_headers()
        
        try:
            async with self.session.get(user_url, headers=headers, timeout=20) as resp:
                if resp.status == 401:
                    if self._auth_attempts < 2:
                        _LOGGER.warning("401 during data fetch. Retrying auth...")
                        self._auth_attempts += 1
                        self._authenticated = False
                        await self.authenticate()
                        return await self.get_account_info()
                    else:
                        raise Exception("Auth loop detected. Stopping.")

                if resp.status != 200:
                    raise Exception(f"API returned {resp.status}")

                data = await resp.json()
                
                # Возвращаем данные. 
                # Важно: если структура в логах была [ {...} ], берем data[0]
                user_info = data[0] if isinstance(data, list) else data

                return {
                    "balance": float(user_info.get("balance", 0.0)),
                    "customer_number": str(user_info.get("contract_num", user_info.get("contract", "N/A"))),
                    "bonus_balance": float(user_info.get("bonusBalance", 0.0)),
                    "ip_addresses": [],
                }

        except Exception as ex:
            _LOGGER.error("Data fetch error: %s", ex)
            raise