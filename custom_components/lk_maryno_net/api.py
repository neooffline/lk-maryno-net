"""API client for Maryno.net."""
import asyncio
import logging
import ssl
import urllib.parse
from typing import Any, Dict, Optional

import aiohttp
from yarl import URL

from .const import BASE_URL

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
        # CookieJar будет автоматически хранить XSRF-TOKEN и connect.sid
        self.session = aiohttp.ClientSession(connector=connector)

    def _get_headers(self) -> Dict[str, str]:
        """Формирование заголовков с актуальным XSRF токеном."""
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "origin": self.base_url,
            "referer": f"{self.base_url}/",
        }

        if self.session:
            for cookie in self.session.cookie_jar:
                if cookie.key == 'XSRF-TOKEN':
                    # Важно: декодируем токен (убираем %3D и прочее)
                    headers['x-xsrf-token'] = urllib.parse.unquote(cookie.value)
                    break
        return headers

    async def authenticate(self) -> None:
        """Процесс авторизации с предварительным получением токена."""
        await self._create_session()
        
        try:
            # 1. Заходим на страницу логина для получения начальных кук
            async with self.session.get(f"{self.base_url}/login/", timeout=10) as resp:
                await resp.text()

            # 2. Отправляем учетные данные
            login_data = {"username": self.username, "password": self.password}
            headers = self._get_headers()
            
            _LOGGER.info("Authenticating user %s...", self.username)
            async with self.session.post(
                f"{self.base_url}/auth", 
                json=login_data, 
                headers=headers, 
                timeout=20
            ) as resp:
                if resp.status not in [200, 201, 204, 304]:
                    text = await resp.text()
                    raise Exception(f"Login failed ({resp.status}): {text}")
                
                # Даем сессии время обновить куки (токен меняется после логина)
                await asyncio.sleep(0.5)
                
                self._authenticated = True
                self._auth_attempts = 0
                _LOGGER.info("Successfully authenticated")

        except Exception as ex:
            _LOGGER.error("Authentication error: %s", ex)
            self._authenticated = False
            raise

    async def get_account_info(self) -> Dict[str, Any]:
        """Получение данных по цепочке: Contract -> Subscriber -> Product."""
        if not self._authenticated:
            await self.authenticate()

        try:
            # ШАГ 1: Получаем Contract ID
            async with self.session.get(
                f"{self.base_url}/api/user/contract", 
                headers=self._get_headers(),
                timeout=20
            ) as resp:
                # Если получили HTML вместо JSON - сессия слетела
                if "text/html" in resp.headers.get("Content-Type", ""):
                    _LOGGER.warning("Session lost (HTML received). Retrying...")
                    self._authenticated = False
                    return await self.get_account_info()

                contracts = await resp.json()
                if not contracts:
                    raise Exception("No contracts found")
                
                contract = contracts[0] if isinstance(contracts, list) else contracts
                c_id = contract.get("contract_id")
                c_num = contract.get("contract_num", "N/A")

            # ШАГ 2: Получаем Subscriber ID (используя contract_id)
            async with self.session.get(
                f"{self.base_url}/api/user/subscriber/{c_id}", 
                headers=self._get_headers(),
                timeout=20
            ) as resp:
                subs = await resp.json()
                sub = subs[0] if isinstance(subs, list) else subs
                s_id = sub.get("subscriber_id")

            # ШАГ 3: Получаем баланс из Product (используя subscriber_id)
            async with self.session.get(
                f"{self.base_url}/api/user/product/{s_id}", 
                headers=self._get_headers(),
                timeout=20
            ) as resp:
                products = await resp.json()
                _LOGGER.debug("Financial data: %s", products)
                
                # Баланс обычно в первом объекте списка
                prod = products[0] if isinstance(products, list) else products
                
                # Пытаемся достать баланс из разных возможных полей
                balance = prod.get("balance", 0.0)
                bonus = prod.get("bonus_balance", prod.get("bonusBalance", 0.0))

                return {
                    "balance": float(balance),
                    "customer_number": str(c_num),
                    "bonus_balance": float(bonus),
                    "ip_addresses": [],
                }

        except Exception as ex:
            _LOGGER.error("Failed to fetch account info: %s", ex)
            # Если это первая ошибка, пробуем переавторизоваться один раз
            if self._auth_attempts == 0:
                self._auth_attempts += 1
                self._authenticated = False
                return await self.get_account_info()
            raise

    async def close(self) -> None:
        """Закрытие сессии."""
        if self.session:
            await self.session.close()