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
        """Последовательное получение данных: contract -> subscriber -> product."""
        if not self._authenticated:
            await self.authenticate()

        headers = self._get_headers()
        # Важно для API
        headers["accept"] = "application/json, text/plain, */*"
        headers["referer"] = f"{self.base_url}/"

        try:
            # ШАГ 1: Получаем ID контракта
            async with self.session.get(f"{self.base_url}/api/user/contract", headers=headers) as resp:
                if "text/html" in resp.headers.get("Content-Type", ""):
                    _LOGGER.warning("Redirected to login. Re-authenticating...")
                    self._authenticated = False
                    return await self.get_account_info()
                
                contracts = await resp.json()
                contract = contracts[0] if contracts else {}
                c_id = contract.get("contract_id")
                c_num = contract.get("contract_num", "N/A")

            # ШАГ 2: Получаем ID абонента (subscriber_id)
            # Видим на скриншоте 00.21.29.jpg, что это возвращает список объектов
            async with self.session.get(f"{self.base_url}/api/user/subscriber/{c_id}", headers=headers) as resp:
                subscribers = await resp.json()
                # Берем subscriber_id из первого элемента
                s_id = subscribers[0].get("subscriber_id") if subscribers else None

            if not s_id:
                _LOGGER.error("Could not find subscriber_id")
                return {"balance": 0.0, "customer_number": c_num}

            # ШАГ 3: Получаем финансовые данные из product
            # На скриншотах 23.30.42.jpg и 23.30.44.jpg видно, что баланс ищется здесь
            product_url = f"{self.base_url}/api/user/product/{s_id}"
            async with self.session.get(product_url, headers=headers) as resp:
                products = await resp.json()
                _LOGGER.info("Product data (financials): %s", products)
                
                # Ищем баланс. В разных API он может быть в корне или в первом продукте
                main_product = products[0] if isinstance(products, list) and products else products
                
                # Проверяем разные варианты именования полей
                balance = main_product.get("balance") or main_product.get("account_balance", 0.0)
                bonus = main_product.get("bonus_balance") or main_product.get("bonusBalance", 0.0)

                return {
                    "balance": float(balance),
                    "customer_number": str(c_num),
                    "bonus_balance": float(bonus),
                    "subscriber_id": s_id
                }

        except Exception as ex:
            _LOGGER.error("Error during data sequence: %s", ex)
            raise