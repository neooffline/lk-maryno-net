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
    
    def _get_headers(self) -> Dict[str, str]:
        """Формирование заголовков с актуальным XSRF-токеном из кук."""
        headers = {
            "accept": "application/json, text/plain, */*",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "origin": self.base_url,
            "referer": f"{self.base_url}/", # Попробуйте также f"{self.base_url}/login/" если не сработает
        }

        if self.session:
            for cookie in self.session.cookie_jar:
                if cookie.key == 'XSRF-TOKEN':
                    # Токен в заголовке должен быть декодирован (без %3D и т.д.)
                    headers['x-xsrf-token'] = urllib.parse.unquote(cookie.value)
                    break
        return headers

    async def get_account_info(self) -> Dict[str, Any]:
        """Цепочка запросов: Contract -> Subscriber -> Product."""
        if not self._authenticated:
            await self.authenticate()

        try:
            # 1. Получаем ID контракта
            # На скриншоте 00.19.24.jpg видно, что этот запрос возвращает массив с contract_id
            async with self.session.get(
                f"{self.base_url}/api/user/contract", 
                headers=self._get_headers()
            ) as resp:
                if "text/html" in resp.headers.get("Content-Type", ""):
                    _LOGGER.warning("Session lost, re-authenticating...")
                    self._authenticated = False
                    await self.authenticate()
                    return await self.get_account_info()

                contracts = await resp.json()
                _LOGGER.debug("Contracts: %s", contracts)
                contract = contracts[0] if isinstance(contracts, list) else contracts
                c_id = contract.get("contract_id")
                c_num = contract.get("contract_num")

            # 2. Получаем ID абонента (subscriber_id)
            # На скриншоте 00.21.29.jpg видно, что запрос к /subscriber/{c_id} возвращает subscriber_id
            async with self.session.get(
                f"{self.base_url}/api/user/subscriber/{c_id}", 
                headers=self._get_headers()
            ) as resp:
                subs = await resp.json()
                sub = subs[0] if isinstance(subs, list) else subs
                s_id = sub.get("subscriber_id")

            # 3. Получаем баланс из product
            # На скриншотах 23.30.42.jpg и 23.30.44.jpg видно, что финансовые данные здесь
            async with self.session.get(
                f"{self.base_url}/api/user/product/{s_id}", 
                headers=self._get_headers()
            ) as resp:
                products = await resp.json()
                _LOGGER.info("Product data received: %s", products)
                
                product = products[0] if isinstance(products, list) else products
                
                # Извлекаем баланс (названия полей сверены со скриншотами)
                return {
                    "balance": float(product.get("balance", 0.0)),
                    "customer_number": str(c_num),
                    "bonus_balance": float(product.get("bonus_balance", 0.0)),
                }

        except Exception as ex:
            _LOGGER.error("Data sequence failed: %s", ex)
            raise