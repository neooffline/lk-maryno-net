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
        """Формирование заголовков."""
        headers = {
            "accept": "application/json, text/plain, */*",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "origin": self.base_url,
            "referer": f"{self.base_url}/",
        }

        # Вытаскиваем токен максимально аккуратно
        token = None
        for cookie in self.session.cookie_jar:
            if cookie.key.upper() == 'XSRF-TOKEN':
                token = urllib.parse.unquote(cookie.value)
                break
        
        if token:
            headers['x-xsrf-token'] = token
        return headers

    async def authenticate(self) -> None:
        """Авторизация с принудительной очисткой старых сессий."""
        await self._create_session()
        self.session.cookie_jar.clear() # Начинаем с чистого листа
        
        try:
            # 1. Сначала просто получаем базовые куки
            async with self.session.get(f"{self.base_url}/login/") as resp:
                await resp.text()

            # 2. Логин
            login_data = {"username": self.username, "password": self.password}
            # ВАЖНО: при логине отправляем токен, который получили на шаге 1
            async with self.session.post(
                f"{self.base_url}/auth", 
                json=login_data, 
                headers=self._get_headers()
            ) as resp:
                if resp.status not in [200, 304]:
                    raise Exception(f"Auth failed: {resp.status}")
                
                # ЧИТ: Извлекаем новый токен напрямую из заголовков ответа, 
                # не дожидаясь, пока aiohttp его переварит
                set_cookie = resp.headers.getall('Set-Cookie', [])
                for cookie_str in set_cookie:
                    if 'XSRF-TOKEN=' in cookie_str:
                        new_token = cookie_str.split('XSRF-TOKEN=')[1].split(';')[0]
                        # Принудительно обновляем в jar
                        self.session.cookie_jar.update_cookies(
                            {'XSRF-TOKEN': new_token}, 
                            URL(self.base_url)
                        )
                
                await asyncio.sleep(1) # Ждем секунду для надежности
                self._authenticated = True
                _LOGGER.info("Successfully authenticated. Token updated manually.")

        except Exception as ex:
            _LOGGER.error("Authentication error: %s", ex)
            raise

    async def get_account_info(self) -> Dict[str, Any]:
        if not self._authenticated:
            await self.authenticate()

        try:
            async with self.session.get(
                f"{self.base_url}/api/user/contract", 
                headers=self._get_headers(),
                allow_redirects=False # ЗАПРЕЩАЕМ редирект на /login/
            ) as resp:
                # Если вместо 200 получили 302 (редирект), значит сессия не сработала
                if resp.status in [301, 302]:
                    _LOGGER.error("Server tried to redirect to login. Session invalid.")
                    self._authenticated = False
                    raise Exception("Session failed right after auth")

                if "text/html" in resp.headers.get("Content-Type", ""):
                    # Это то самое место, где мы падали
                    raise Exception("Received HTML instead of JSON. Auth sequence is broken.")

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