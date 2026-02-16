# src/trading_shared/exchanges/trading/deribit_client.py

# --- Built Ins  ---
import asyncio
import time
from functools import wraps
from typing import Any

# --- Installed  ---
import aiohttp
import orjson
from loguru import logger as log
from pydantic import SecretStr

# --- Local Application Imports ---
from ...config.models import ExchangeSettings
from .deribit_constants_deprecating import ApiMethods


class TokenExpiredError(Exception):
    pass


class DeribitTradingClient:
    """
    An API client for private, authenticated Deribit trading endpoints.
    Handles authentication, token expiry, and basic request signing.
    """

    def __init__(
        self,
        settings: ExchangeSettings,
        client_id: str | SecretStr,
        client_secret: str | SecretStr,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._settings = settings
        self.exchange_name = "deribit"
        self._session: aiohttp.ClientSession | None = None
        self._base_url = self._settings.rest_url + "/api/v2" if self._settings.rest_url else "https://www.deribit.com/api/v2"
        self._access_token: str | None = None
        self._auth_lock = asyncio.Lock()
        log.info("Deribit API client initialized for production use.")

    def _get_secret_value(self, secret: SecretStr | str) -> str:
        """Safely gets the string value from a SecretStr or a plain str."""
        if isinstance(secret, SecretStr):
            return secret.get_secret_value()
        return secret

    def _ensure_authenticated(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                return await func(self, *args, **kwargs)
            except TokenExpiredError:
                async with self._auth_lock:
                    log.warning(f"Access token expired during call to '{func.__name__}'. Re-authenticating.")
                    await self.login()
                    log.info(f"Re-authentication successful. Retrying call to '{func.__name__}'.")
                    return await func(self, *args, **kwargs)

        return wrapper

    # --- Connection and Auth ---
    async def connect(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(json_serialize=lambda data: orjson.dumps(data).decode())
            log.info("Aiohttp session established for Deribit API.")
            await self.login()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            log.info("Aiohttp session for Deribit API closed.")

    async def login(self):
        if not self._session:
            raise ConnectionError("Session not established. Call connect() first.")

        auth_params = {
            "grant_type": "client_credentials",
            "client_id": self._get_secret_value(self._client_id),
            "client_secret": self._get_secret_value(self._client_secret),
        }
        url = f"{self._base_url}/public/auth"
        log.info("Attempting to authenticate with Deribit...")
        try:
            async with self._session.get(url, params=auth_params) as response:
                response.raise_for_status()
                data = await response.json()
                if "result" in data and "access_token" in data["result"]:
                    self._access_token = data["result"]["access_token"]
                    log.success("Successfully authenticated with Deribit.")
                else:
                    log.error(f"Deribit authentication failed: {data.get('error', 'Unknown error')}")
                    self._access_token = None
        except aiohttp.ClientError as e:
            log.critical(f"HTTP error during authentication: {e}")
            self._access_token = None

    async def _perform_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not method.startswith("public/") and not self._access_token:
            raise ConnectionError("Not authenticated for private API call.")
        if not self._session or self._session.closed:
            raise ConnectionError("Session is not active.")

        headers = {"Authorization": f"bearer {self._access_token}"} if self._access_token else {}
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": method,
            "params": params,
        }

        async with self._session.post(self._base_url, json=payload, headers=headers) as response:
            data = await response.json()
            if response.status == 400 and data.get("error", {}).get("code") == 13009:
                raise TokenExpiredError(f"Token expired for method {method}")

            response.raise_for_status()

            if "error" in data:
                log.error(f"Deribit API Error for method {method}: {data['error']}")
                return {"success": False, "error": data["error"]}

            return {"success": True, "data": data.get("result")}

    # --- API Methods ---

    @_ensure_authenticated
    async def get_positions(self, currency: str) -> dict[str, Any]:
        log.info(f"[API CALL] Fetching positions for currency: {currency}")
        return await self._perform_request(ApiMethods.GET_POSITIONS, {"currency": currency})

    @_ensure_authenticated
    async def buy(self, **params) -> dict[str, Any]:
        return await self._perform_request(ApiMethods.BUY, params)

    @_ensure_authenticated
    async def sell(self, **params) -> dict[str, Any]:
        return await self._perform_request(ApiMethods.SELL, params)

    @_ensure_authenticated
    async def edit(self, **params) -> dict[str, Any]:
        return await self._perform_request(ApiMethods.EDIT, params)

    @_ensure_authenticated
    async def cancel(self, order_id: str) -> dict[str, Any]:
        log.info(f"[API CALL] Attempting to cancel order: {order_id}")
        return await self._perform_request(ApiMethods.CANCEL, {"order_id": order_id})

    @_ensure_authenticated
    async def get_open_orders_by_currency(self, currency: str) -> dict[str, Any]:
        log.info(f"[API CALL] Fetching open orders for currency: {currency}")
        return await self._perform_request(ApiMethods.GET_OPEN_ORDERS_BY_CURRENCY, {"currency": currency})

    @_ensure_authenticated
    async def get_account_summary(self, currency: str) -> dict[str, Any] | None:
        log.info(f"[API CALL] Fetching account summary for currency: {currency}")
        response = await self._perform_request(ApiMethods.GET_ACCOUNT_SUMMARY, {"currency": currency})
        return response.get("data") if response.get("success") else None

    @_ensure_authenticated
    async def simulate_pme(self, positions: dict[str, float]) -> dict[str, Any]:
        log.info(f"[API CALL] Simulating PME for portfolio with {len(positions)} positions.")
        params = {
            "currency": "CROSS",
            "add_positions": True,
            "simulated_positions": positions,
        }
        return await self._perform_request(ApiMethods.SIMULATE_PME, params)
