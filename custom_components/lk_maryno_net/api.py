"""API client for Maryno.net."""
import asyncio
import logging
import ssl
import urllib.parse
from typing import Any, Dict, Optional

import aiohttp

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
        """Build headers mimicking a real browser."""
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru,en-US;q=0.9,en;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Origin": self.base_url,
            "Referer": referer or f"{self.base_url}/",
            "DNT": "1",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }

        if self.session:
            for cookie in self.session.cookie_jar:
                if cookie.key == 'XSRF-TOKEN':
                    headers['x-xsrf-token'] = urllib.parse.unquote(cookie.value)
                    break
        return headers

    async def authenticate(self) -> bool:
        """Authentication sequence."""
        await self._create_session()
        self.session.cookie_jar.clear()
        
        try:
            # 1. Загрузка страницы входа
            async with self.session.get(f"{self.base_url}/auth", timeout=10) as resp:
                await resp.text()

            # 2. Логин
            login_data = {"username": self.username, "password": self.password}
            headers = self._get_headers(referer=f"{self.base_url}/auth")
            headers["Content-Type"] = "application/json"

            async with self.session.post(AUTH_URL, json=login_data, headers=headers, timeout=20) as resp:
                if resp.status not in [200, 304]:
                    return False
                await resp.text()

            _LOGGER.info("Authentication basic success")
            self._authenticated = True
            return True

        except Exception as ex:
            _LOGGER.error("Auth process error: %s", ex)
            return False

    async def get_account_info(self) -> Dict[str, Any]:
        """Fetch data using a loop to avoid recursion and sync session."""
        max_retries = 2
        for attempt in range(max_retries + 1):
            if not self._authenticated:
                if not await self.authenticate():
                    raise Exception("Authentication failed")

            try:
                # ШАГ 1: Синхронизация сессии именно для /info
                sync_url = f"{self.base_url}/api/session?path=%2Finfo"
                async with self.session.get(sync_url, headers=self._get_headers(referer=f"{self.base_url}/info"), timeout=10) as s_resp:
                    await s_resp.text()

                # ШАГ 2: СРАЗУ запрос данных с тем же Referer
                user_url = f"{self.base_url}/api/user/all"
                headers = self._get_headers(referer=f"{self.base_url}/info")
                
                async with self.session.get(user_url, headers=headers, timeout=20) as resp:
                    if resp.status == 401:
                        _LOGGER.warning("401 Unauthorized on attempt %s", attempt + 1)
                        self._authenticated = False
                        if attempt < max_retries:
                            await asyncio.sleep(1)
                            continue
                        raise Exception("Persistent 401 Unauthorized")

                    if resp.status != 200:
                        raise Exception(f"API Error: {resp.status}")

                    data = await resp.json()
                    user_info = data[0] if isinstance(data, list) else data

                    return {
                        "balance": float(user_info.get("balance", 0.0)),
                        "customer_number": str(user_info.get("contract_num", user_info.get("contract", "N/A"))),
                        "bonus_balance": float(user_info.get("bonusBalance", 0.0)),
                        "ip_addresses": [],
                    }

            except Exception as ex:
                if attempt < max_retries:
                    _LOGGER.debug("Retrying due to error: %s", ex)
                    self._authenticated = False
                    continue
                raise ex

        raise Exception("Failed to get account info after retries")