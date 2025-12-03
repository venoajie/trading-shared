# --- Built Ins  ---
from typing import List, Dict, Any

# --- Installed  ---
import aiohttp
from loguru import logger as log

# --- Local Application Imports ---
from ...config.models import ExchangeSettings


class BinancePublicClient:
    """A generic, reusable client for Binance's public REST APIs."""

    def __init__(self, settings: ExchangeSettings):
        # The base URL can be part of the settings or defaulted
        self.spot_url = "https://api.binance.com/api/v3"
        self.linear_futures_url = "https://fapi.binance.com/fapi/v1"
        self.inverse_futures_url = "https://dapi.binance.com/dapi/v1"
        self._session: aiohttp.ClientSession | None = None

    async def connect(self):
        self._session = aiohttp.ClientSession()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_raw_exchange_info(self, market_type: str) -> List[Dict[str, Any]]:
        """Fetches the raw, untransformed exchange info for a given market type."""
        url_map = {
            "spot": self.spot_url,
            "linear_futures": self.linear_futures_url,
            "inverse_futures": self.inverse_futures_url,
        }
        base_url = url_map.get(market_type)
        if not base_url:
            raise ValueError(f"Unknown market type for Binance: {market_type}")

        try:
            url = f"{base_url}/exchangeInfo"
            async with self._session.get(url, timeout=20) as response:
                response.raise_for_status()
                data = await response.json()
                return data.get("symbols", [])
        except Exception as e:
            log.error(f"Failed to fetch raw exchange info from {url}: {e}")
            return []
