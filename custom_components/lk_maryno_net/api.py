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

    def _get_headers(self, referer_path: str = "/info") -> Dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru,en-US;q=0.9,en;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": f"{self.base_url}{referer_path}",
            "X-Requested-With": "XMLHttpRequest", # Важно для AngularJS
        }
        if self.session:
            for cookie in self.session.cookie_jar:
                if cookie.key == 'XSRF-TOKEN':
                    headers['x-xsrf-token'] = urllib.parse.unquote(cookie.value)
                    break
        return headers

    async def authenticate(self) -> bool:
        await self._create_session()
        self.session.cookie_jar.clear()
        
        try:
            # 1. Инициализация кук
            async with self.session.get(f"{self.base_url}/auth") as resp:
                await resp.text()

            # 2. Логин
            login_data = {"username": self.username, "password": self.password}
            async with self.session.post(AUTH_URL, json=login_data, headers=self._get_headers("/auth")) as resp:
                if resp.status not in [200, 304]:
                    _LOGGER.error("Login failed with status %s", resp.status)
                    return False
                await resp.text()

            # 3. Имитация инициализации AngularJS (Resolve шаги)
            # Шаг A: Синхронизация сессии на /info
            sync_url = f"{self.base_url}/api/session?path=%2Finfo"
            async with self.session.get(sync_url, headers=self._get_headers("/info")) as resp:
                await resp.text()

            # Шаг B: Запрос контрактов (обязательно для сессии)
            async with self.session.get(f"{self.base_url}/api/user/contract", headers=self._get_headers("/info")) as resp:
                await resp.text()

            # Шаг C: Запрос абонента
            async with self.session.get(f"{self.base_url}/api/user/subscriber", headers=self._get_headers("/info")) as resp:
                await resp.text()

            _LOGGER.info("Full session initialization completed")
            self._authenticated = True
            return True

        except Exception as ex:
            _LOGGER.error("Auth error: %s", ex)
            return False

    async def get_account_info(self) -> Dict[str, Any]:
        max_retries = 2
        for attempt in range(max_retries + 1):
            if not self._authenticated:
                if not await self.authenticate():
                    raise Exception("Auth failed")

            try:
                # Финальный запрос данных
                url = f"{self.base_url}/api/user/all"
                async with self.session.get(url, headers=self._get_headers("/info"), timeout=15) as resp:
                    if resp.status == 401:
                        _LOGGER.warning("401 on attempt %s, re-authenticating...", attempt + 1)
                        self._authenticated = False
                        continue
                    
                    if resp.status != 200:
                        raise Exception(f"API Error {resp.status}")

                    data = await resp.json()
                    user_info = data[0] if isinstance(data, list) else data

                    return {
                        "balance": float(user_info.get("balance", 0.0)),
                        "customer_number": str(user_info.get("contract_num", user_info.get("contract", "N/A"))),
                        "bonus_balance": float(user_info.get("bonusBalance", 0.0)),
                        "ip_addresses": [],
                    }
            except Exception as ex:
                if attempt == max_retries: raise ex
                self._authenticated = False
                await asyncio.sleep(1)

        raise Exception("Failed to fetch data")