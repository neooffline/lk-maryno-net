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
        self._auth_attempts = 0

    async def _create_session(self) -> None:
        """Create aiohttp session with persistent cookie jar."""
        if self.session and not self.session.closed:
            return
            
        conn_kwargs = {}
        if not self.verify_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            conn_kwargs["ssl"] = ssl_context

        connector = aiohttp.TCPConnector(**conn_kwargs)
        self.session = aiohttp.ClientSession(
            connector=connector,
            cookie_jar=aiohttp.CookieJar(unsafe=True)
        )

    def _get_headers(self, referer: str = None) -> Dict[str, str]:
        """Build headers with XSRF token from session cookies."""
        headers = {
            "accept": "application/json, text/plain, */*",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "origin": self.base_url,
            "referer": referer or f"{self.base_url}/",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
        }

        if self.session:
            for cookie in self.session.cookie_jar:
                if cookie.key == 'XSRF-TOKEN':
                    headers['x-xsrf-token'] = urllib.parse.unquote(cookie.value)
                    break
        return headers

    async def _sync_session(self, path: str = "/info") -> None:
        """Crucial step: Sync session with the server for the specific path."""
        if not self.session:
            return
        
        encoded_path = urllib.parse.quote(path, safe='')
        sync_url = f"{self.base_url}/api/session?path={encoded_path}"
        
        _LOGGER.debug("Syncing session for path: %s", path)
        async with self.session.get(sync_url, headers=self._get_headers(), timeout=10) as resp:
            # Даже если 304 или 200, куки обновятся автоматически в jar
            await resp.text()

    async def authenticate(self) -> None:
        """Authentication sequence with session synchronization."""
        await self._create_session()
        
        try:
            # 1. Получаем токены с главной
            async with self.session.get(self.base_url, timeout=10) as resp:
                await resp.text()

            # 2. Логин
            login_data = {"username": self.username, "password": self.password}
            headers = self._get_headers(referer=f"{self.base_url}/auth")
            headers["content-type"] = "application/json"

            async with self.session.post(AUTH_URL, json=login_data, headers=headers, timeout=20) as resp:
                if resp.status not in [200, 304]:
                    text = await resp.text()
                    raise Exception(f"Login failed ({resp.status}): {text}")
                await resp.text()

            # 3. Синхронизируем сессию для путей личного кабинета
            await self._sync_session("/dashboard")
            await self._sync_session("/info")
            
            _LOGGER.info("Authentication and session sync completed")
            self._authenticated = True
            self._auth_attempts = 0 

        except Exception as ex:
            _LOGGER.error("Auth process error: %s", ex)
            self._authenticated = False
            raise

    async def get_account_info(self) -> Dict[str, Any]:
        """Fetch data using the synchronized session."""
        if not self._authenticated:
            await self.authenticate()

        # Перед каждым запросом данных подтверждаем путь в сессии
        await self._sync_session("/info")
        
        user_url = f"{self.base_url}/api/user/all"
        headers = self._get_headers(referer=f"{self.base_url}/info")
        
        try:
            async with self.session.get(user_url, headers=headers, timeout=20) as resp:
                if resp.status == 401:
                    _LOGGER.warning("401 Unauthorized. Retrying auth sequence...")
                    if self._auth_attempts < 2:
                        self._auth_attempts += 1
                        self._authenticated = False
                        self.session.cookie_jar.clear()
                        await self.authenticate()
                        return await self.get_account_info()
                    else:
                        raise Exception("Persistent 401: Auth loop blocked.")

                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"API Error ({resp.status}): {text}")

                data = await resp.json()
                user_info = data[0] if isinstance(data, list) else data

                return {
                    "balance": float(user_info.get("balance", 0.0)),
                    "customer_number": str(user_info.get("contract_num", user_info.get("contract", "N/A"))),
                    "bonus_balance": float(user_info.get("bonusBalance", 0.0)),
                    "ip_addresses": [],
                }

        except Exception as ex:
            _LOGGER.error("Data fetch error: %s", ex)
            self._authenticated = False
            raise