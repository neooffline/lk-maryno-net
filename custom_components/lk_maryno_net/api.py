"""API client for Maryno.net."""
import logging
import ssl
import urllib.parse
from typing import Any, Dict, Optional

import aiohttp

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

    async def _create_session(self) -> None:
        if self.session:
            return

        conn_kwargs = {}
        if not self.verify_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            conn_kwargs["ssl"] = ssl_context

        connector = aiohttp.TCPConnector(**conn_kwargs)
        self.session = aiohttp.ClientSession(connector=connector)

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "accept": "application/json, text/plain, */*",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "origin": self.base_url,
            "referer": f"{self.base_url}/",
        }

        token = None
        for cookie in self.session.cookie_jar:
            if cookie.key.upper() == 'XSRF-TOKEN':
                token = urllib.parse.unquote(cookie.value)
                break

        if token:
            headers['x-xsrf-token'] = token
        return headers

    async def _get_json(self, url: str) -> Any:
        async with self.session.get(
            url,
            headers=self._get_headers(),
            allow_redirects=False,
        ) as resp:
            if resp.status in (301, 302):
                self._authenticated = False
                raise Exception(f"Session expired, redirect to {resp.headers.get('Location')}")
            if "text/html" in resp.headers.get("Content-Type", ""):
                raise Exception(f"Received HTML instead of JSON from {url}")
            return await resp.json()

    async def _post(self, url: str) -> str:
        async with self.session.post(
            url,
            headers=self._get_headers(),
            allow_redirects=False,
        ) as resp:
            if resp.status not in (200, 204):
                raise Exception(f"POST {url} failed: {resp.status}")
            return await resp.text()

    async def authenticate(self) -> None:
        await self._create_session()
        self.session.cookie_jar.clear()

        try:
            async with self.session.get(f"{self.base_url}/login/") as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to get login page: {resp.status}")
                await resp.text()

            login_data = {"username": self.username, "password": self.password}
            async with self.session.post(
                f"{self.base_url}/auth",
                json=login_data,
                headers=self._get_headers(),
            ) as resp:
                if resp.status not in (200, 304):
                    body = await resp.text()
                    raise Exception(f"Auth failed: {resp.status} - {body}")

                auth_response = await resp.json()
                type_jur = auth_response.get("type_jur")
                _LOGGER.debug("Auth response: type_jur=%s", type_jur)

            self._authenticated = True
            _LOGGER.info("Successfully authenticated")

        except Exception as ex:
            _LOGGER.error("Authentication error: %s", ex)
            raise

    async def get_account_info(self) -> Dict[str, Any]:
        if not self._authenticated:
            await self.authenticate()

        try:
            contracts = await self._get_json(f"{self.base_url}/api/user/contract")
            if not contracts:
                raise Exception("No contracts found")
            contract = contracts[0] if isinstance(contracts, list) else contracts
            contract_id = contract["contract_id"]
            contract_num = contract.get("contract_num", "N/A")
            _LOGGER.debug("Contract: id=%s, num=%s", contract_id, contract_num)

            await self._post(f"{self.base_url}/api/user/contract/{contract_id}")

            subscribers = await self._get_json(f"{self.base_url}/api/user/subscriber")
            if not subscribers:
                raise Exception("No subscribers found")
            subscriber = subscribers[0] if isinstance(subscribers, list) else subscribers
            subscriber_id = subscriber["subscriber_id"]
            _LOGGER.debug("Subscriber: id=%s", subscriber_id)

            await self._post(f"{self.base_url}/api/user/subscriber/{subscriber_id}")

            products = await self._get_json(f"{self.base_url}/api/user/product")
            if not products:
                raise Exception("No products found")
            product = products[0] if isinstance(products, list) else products
            product_id = product["product_id"]
            _LOGGER.debug("Product: id=%s", product_id)

            await self._post(f"{self.base_url}/api/user/product/{product_id}")

            user_all = await self._get_json(f"{self.base_url}/api/user/all")
            _LOGGER.debug("User all data: %s", user_all)

            gbonus_info = await self._get_json(f"{self.base_url}/api/gbonus/info")
            _LOGGER.debug("G-Bonus info: %s", gbonus_info)

            return {
                "balance": float(user_all.get("balance", 0.0)),
                "customer_number": str(contract_num),
                "bonus_balance": float(user_all.get("bonusBalance", 0.0)),
                "ip_addresses": [],
                "fio": user_all.get("fio", ""),
                "address": user_all.get("address", ""),
                "plan": user_all.get("plan", ""),
                "plan_cost": user_all.get("plan_cost", 0),
                "plan_speed": user_all.get("plan_speed", ""),
                "status": user_all.get("status", ""),
                "gbonus_count": gbonus_info.get("n_bonus", 0),
                "gbonus_days_left": gbonus_info.get("days_left", 0),
                "gbonus_status": gbonus_info.get("pvt_status_name", ""),
                "gbonus_sum_pays": gbonus_info.get("sum_pays", 0),
            }

        except Exception as ex:
            _LOGGER.error("Failed to fetch account info: %s", ex)
            self._authenticated = False
            raise

    async def close(self) -> None:
        if self.session:
            await self.session.close()
