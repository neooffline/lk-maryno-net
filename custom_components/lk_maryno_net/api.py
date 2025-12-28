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
        """Полноценная процедура авторизации с 'прогревом' сессии."""
        await self._create_session()
        
        try:
            # 1. ШАГ: 'Прогрев'. Заходим на login, чтобы получить ПЕРВЫЙ XSRF-TOKEN
            _LOGGER.debug("Pre-warming session...")
            async with self.session.get(f"{self.base_url}/login/", timeout=10) as resp:
                await resp.text() # Ждем загрузки

            # 2. ШАГ: Логин. 
            # Теперь у нас в self.session.cookie_jar точно есть XSRF-TOKEN
            headers = self._get_headers()
            login_data = {"username": self.username, "password": self.password}
            
            _LOGGER.info("Sending auth request for user: %s", self.username)
            async with self.session.post(
                f"{self.base_url}/auth", 
                json=login_data, 
                headers=headers, 
                timeout=20
            ) as resp:
                if resp.status not in [200, 201, 204, 304]:
                    text = await resp.text()
                    raise Exception(f"Login failed ({resp.status}): {text}")
                
                # После логина сервер может обновить XSRF-TOKEN, это нормально
                _LOGGER.info("Successfully authenticated, with headers: %s", resp.headers)
                self._authenticated = True
                self._auth_attempts = 0

        except Exception as ex:
            _LOGGER.error("Authentication error: %s", ex)
            self._authenticated = False
            raise

    def _get_headers(self) -> Dict[str, str]:
        """Формирование заголовков. Важно: X-Xsrf-Token должен быть в каждом запросе."""
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "origin": self.base_url,
            "referer": f"{self.base_url}/login/",
        }

        # Ищем токен в куках
        token = None
        for cookie in self.session.cookie_jar:
            if cookie.key == 'XSRF-TOKEN':
                token = urllib.parse.unquote(cookie.value)
                break
        
        if token:
            headers['X-XSRF-TOKEN'] = token
            # В последних версиях Maryno может требоваться и заглавный вариант
            # headers['X-XSRF-TOKEN'] = token 
        _LOGGER.info("Using headers: %s", headers)
        return headers

    async def get_account_info(self) -> Dict[str, Any]:
        """Последовательное получение данных с проверкой редиректа."""
        if not self._authenticated:
            await self.authenticate()

        try:
            # ШАГ 1: Контракт (contract_id)
            # Мы вызываем _get_headers() заново для каждого запроса, чтобы токен был свежим
            async with self.session.get(f"{self.base_url}/api/user/contract", headers=self._get_headers()) as resp:
                # Если сервер ответил HTML-страницей, значит нас выкинуло на логин
                if "text/html" in resp.headers.get("Content-Type", ""):
                    _LOGGER.warning("Session dropped (HTML received). Attempting re-auth...")
                    self._authenticated = False
                    await self.authenticate()
                    return await self.get_account_info()

                contracts = await resp.json()
                contract = contracts[0] if isinstance(contracts, list) and contracts else contracts
                c_id = contract.get("contract_id")
                c_num = contract.get("contract_num")

            # ШАГ 2: Абонент (subscriber_id)
            # На скриншоте 00.21.29.jpg видно, что subscriber возвращает массив объектов
            async with self.session.get(f"{self.base_url}/api/user/subscriber/{c_id}", headers=self._get_headers()) as resp:
                subs = await resp.json()
                sub = subs[0] if isinstance(subs, list) and subs else subs
                s_id = sub.get("subscriber_id")

            # ШАГ 3: Баланс (product)
            # Скриншоты 23.30.42.jpg и 23.30.44.jpg подтверждают, что баланс здесь
            async with self.session.get(f"{self.base_url}/api/user/product/{s_id}", headers=self._get_headers()) as resp:
                products = await resp.json()
                _LOGGER.info("Final product data: %s", products)
                
                prod = products[0] if isinstance(products, list) and products else products
                
                return {
                    "balance": float(prod.get("balance", 0.0)),
                    "customer_number": str(c_num),
                    "bonus_balance": float(prod.get("bonus_balance", 0.0)),
                }

        except Exception as ex:
            _LOGGER.error("Data sequence failed: %s", ex)
            raise