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
        """Получение детальных данных аккаунта."""
        if not self._authenticated:
            await self.authenticate()

        headers = self._get_headers()
        
        try:
            # Шаг 1: Получаем ID контракта
            contract_url = f"{self.base_url}/api/user/contract"
            async with self.session.get(contract_url, headers=headers, timeout=20) as resp:
                if resp.status == 401:
                    self._authenticated = False
                    return await self.get_account_info()
                
                contract_data = await resp.json()
                # Берем первый контракт из списка
                contract = contract_data[0] if isinstance(contract_data, list) else contract_data
                contract_id = contract.get("contract_id")
                contract_num = contract.get("contract_num", "N/A")

            # Шаг 2: Запрашиваем данные абонента (где обычно лежит баланс)
            # Судя по скриншоту, путь выглядит как /api/user/subscriber/ID
            sub_url = f"{self.base_url}/api/user/subscriber/{contract_id}"
            _LOGGER.debug("Fetching subscriber info from: %s", sub_url)
            
            async with self.session.get(sub_url, headers=headers, timeout=20) as resp:
                if resp.status != 200:
                    _LOGGER.error("Failed to fetch subscriber data: %s", resp.status)
                    return {
                        "balance": 0.0,
                        "customer_number": contract_num,
                        "bonus_balance": 0.0,
                    }
                
                sub_data = await resp.json()
                _LOGGER.info("Subscriber data received: %s", sub_data)
                
                # Если приходит список, берем первый элемент
                info = sub_data[0] if isinstance(sub_data, list) else sub_data

                return {
                    "balance": float(info.get("balance", 0.0)),
                    "customer_number": str(contract_num),
                    "bonus_balance": float(info.get("bonus_balance", info.get("bonusBalance", 0.0))),
                    "ip_addresses": [],
                }

        except Exception as ex:
            _LOGGER.error("Data fetch error: %s", ex)
            raise