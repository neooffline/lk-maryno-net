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
        self._auth_attempts = 0

    async def _create_session(self) -> None:
        """Создание сессии aiohttp."""
        if self.session:
            return
            
        conn_kwargs = {}
        if not self.verify_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            conn_kwargs["ssl"] = ssl_context

        connector = aiohttp.TCPConnector(**conn_kwargs)
        # CookieJar автоматически сохраняет XSRF-TOKEN и connect.sid
        self.session = aiohttp.ClientSession(connector=connector)

    def _get_headers(self) -> Dict[str, str]:
        """Формирование заголовков с актуальным XSRF токеном."""
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/login/",
        }

        if self.session:
            for cookie in self.session.cookie_jar:
                if cookie.key == 'XSRF-TOKEN':
                    # Важно: токен из куки нужно декодировать перед отправкой в заголовке
                    headers['X-Xsrf-Token'] = urllib.parse.unquote(cookie.value)
                    break
        return headers

    async def authenticate(self) -> None:
        """Процесс авторизации."""
        await self._create_session()
        
        try:
            # 1. Заходим на страницу логина, чтобы получить начальные куки (XSRF)
            async with self.session.get(f"{self.base_url}/login/", timeout=10) as resp:
                await resp.text()

            # 2. POST запрос на авторизацию
            auth_url = f"{self.base_url}/auth"
            login_data = {"username": self.username, "password": self.password}
            
            # Обновляем заголовки (теперь там должен быть XSRF из шага 1)
            headers = self._get_headers()
            
            async with self.session.post(auth_url, json=login_data, headers=headers, timeout=20) as resp:
                if resp.status not in [200, 304]:
                    text = await resp.text()
                    raise Exception(f"Login failed ({resp.status}): {text}")
                
                _LOGGER.info("Successfully authenticated")
                self._authenticated = True
                self._auth_attempts = 0

        except Exception as ex:
            _LOGGER.error("Authentication error: %s", ex)
            self._authenticated = False
            raise

    async def get_account_info(self) -> Dict[str, Any]:
        """Получение данных аккаунта через API."""
        if not self._authenticated:
            await self.authenticate()

        # Судя по скриншоту 'contract', именно этот эндпоинт дает баланс
        url = f"{self.base_url}/api/user/contract"
        headers = self._get_headers()
        
        try:
            async with self.session.get(url, headers=headers, timeout=20) as resp:
                if resp.status == 401:
                    _LOGGER.warning("Session expired, re-authenticating...")
                    self._authenticated = False
                    return await self.get_account_info()

                if resp.status != 200:
                    raise Exception(f"API error: {resp.status}")

                data = await resp.json()
                
                # Обычно API возвращает список контрактов
                contract = data[0] if isinstance(data, list) and len(data) > 0 else data

                # Сопоставляем поля из ответа API (уточнены по скриншотам)
                return {
                    "balance": float(contract.get("balance", 0.0)),
                    "customer_number": str(contract.get("contract_num", "Н/Д")),
                    "bonus_balance": float(contract.get("bonus_balance", 0.0)),
                    "status": contract.get("status", "Unknown")
                }

        except Exception as ex:
            _LOGGER.error("Failed to fetch account info: %s", ex)
            raise