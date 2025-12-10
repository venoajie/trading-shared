# src/trading_shared/exchanges/public/binance.py

# --- Built Ins ---
import asyncio
from typing import List, Dict, Any
from datetime import datetime, timezone

# --- Installed ---
import aiohttp
from loguru import logger as log

# --- Shared Library Imports ---
from .base import PublicExchangeClient
from ..trading.binance_constants import BinanceMarketType
from ...config.models import ExchangeSettings


class BinancePublicClient(PublicExchangeClient):
    """
    Client for Binance's public REST API endpoints.
    """
    _SAFETY_FETCH_LIMIT = 50  # Max number of paginated calls for a single request

    def __init__(self, settings: ExchangeSettings, http_session: aiohttp.ClientSession):
        super().__init__()
        self.http_session = http_session
        self.spot_url = "https://api.binance.com/api/v3"
        self.linear_futures_url = "https://fapi.binance.com/fapi/v1"
        self.inverse_futures_url = "https://dapi.binance.com/dapi/v1"

    def _get_api_url_for_instrument(self, instrument_name: str) -> str:
        """Determines the correct API base URL (spot or futures) for a given instrument."""
        market_type = self.get_market_type_from_instrument_name(instrument_name)
        if market_type == BinanceMarketType.FUTURES_USD_M:
            return self.linear_futures_url
        return self.spot_url

    # A placeholder for the detection logic mentioned above
    def get_market_type_from_instrument_name(self, instrument_name: str) -> BinanceMarketType:
        if "PERP" in instrument_name:
            return BinanceMarketType.FUTURES_USD_M
        return BinanceMarketType.SPOT
        
    def _transform_candle_data_to_canonical(
        self,
        raw_candle: list,
        exchange: str,
        instrument_name: str,
        resolution: str,
    ) -> Dict[str, Any]:
        """Transforms a single raw candle from Binance API into our standard dict format."""
        return {
            "exchange": exchange,
            "instrument_name": instrument_name,
            "resolution": resolution,
            "tick": int(raw_candle[0]),
            "open": float(raw_candle[1]),
            "high": float(raw_candle[2]),
            "low": float(raw_candle[3]),
            "close": float(raw_candle[4]),
            "volume": float(raw_candle[5]),
        }

    async def _perform_paginated_ohlc_fetch(
        self,
        api_url: str,
        instrument_name: str,
        resolution: str,
        start_timestamp_ms: int,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """
        Private method to repeatedly call the klines endpoint to fetch all candles
        from a start time until the present.
        """
        all_candles = []
        next_start_time_ms = start_timestamp_ms
        
        for i in range(self._SAFETY_FETCH_LIMIT):
            params = {
                "symbol": instrument_name.replace("/", ""), 
                "interval": resolution,
                "startTime": next_start_time_ms,
                "limit": limit,
            }
            
            try:
                async with self.http_session.get(f"{api_url}/klines", params=params) as response:
                    response.raise_for_status()
                    raw_candles = await response.json()

                    if not raw_candles:
                        log.info(f"[{instrument_name}] No more candles returned. Pagination complete.")
                        break

                    candles = [
                        self._transform_candle_data_to_canonical(
                            c, "binance", instrument_name, resolution
                        )
                        for c in raw_candles
                    ]
                    all_candles.extend(candles)

                    last_candle_timestamp = candles[-1]["tick"]
                    next_start_time_ms = last_candle_timestamp + 1

                    log.debug(f"Fetched {len(candles)} candles for {instrument_name}. Next fetch starts at {next_start_time_ms}.")

                    if len(raw_candles) < limit:
                        log.info(f"[{instrument_name}] Reached end of available data. Pagination complete.")
                        break

                    await asyncio.sleep(0.2) 

            except aiohttp.ClientError as e:
                log.error(f"API call failed for {instrument_name}: {e}")
                break
            except Exception:
                log.exception(f"An unexpected error occurred during OHLC fetch for {instrument_name}")
                break
        
        if i == self._SAFETY_FETCH_LIMIT - 1:
            log.warning(f"Hit safety fetch limit for {instrument_name}. More data may be available.")

        return all_candles

    async def get_public_ohlc(
        self,
        instrument_name: str,
        resolution: str,
        start_timestamp_ms: int,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Public method to fetch OHLC (k-line) data for a symbol.
        It automatically handles pagination to retrieve all available data from the
        start time until the present.
        """
        api_url = self._get_api_url_for_instrument(instrument_name)
        log.info(f"Starting paginated OHLC fetch for {instrument_name} on {api_url}...")
        
        return await self._perform_paginated_ohlc_fetch(
            api_url=api_url,
            instrument_name=instrument_name,
            resolution=resolution,
            start_timestamp_ms=start_timestamp_ms,
            limit=limit
        )

    async def connect(self):
        """The shared session is managed externally. This method is a no-op."""
        pass

    async def close(self):
            """The shared session is managed externally. This method is a no-op."""
            pass

    async def _get_raw_exchange_info_for_market(
        self, market_type_url: str, market_type_name: str
    ) -> List[Dict[str, Any]]:
        """Fetches the raw, untransformed exchange info for a single given market type."""
        try:
            url = f"{market_type_url}/exchangeInfo"
            async with self.http_session.get(url, timeout=20) as response:
                response.raise_for_status()
                data = await response.json()
                raw_instruments = data.get("symbols", [])
                for inst in raw_instruments:
                    inst["market_type_hint"] = market_type_name
                return raw_instruments
        except Exception as e:
            log.error(f"Failed to fetch raw exchange info from {url}: {e}")
            return []

    async def get_instruments(self, currencies: List[str]) -> List[Dict[str, Any]]:
        """
        Fetches instrument details for all supported market types.
        The 'currencies' argument is ignored as Binance API does not filter by currency.
        """
        log.info("[BinancePublicClient] Fetching instruments for all market types...")
        markets_to_query = {
            "spot": self.spot_url,
            "linear_futures": self.linear_futures_url,
            "inverse_futures": self.inverse_futures_url,
        }

        tasks = [
            self._get_raw_exchange_info_for_market(url, name)
            for name, url in markets_to_query.items()
        ]
        results_by_market = await asyncio.gather(*tasks)

        all_instruments = [inst for market_list in results_by_market for inst in market_list]

        log.success(f"[BinancePublicClient] Total raw instruments fetched: {len(all_instruments)}")
        return all_instruments