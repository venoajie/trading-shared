# src/trading_shared/exchanges/public/binance.py

# --- Built Ins  ---
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

# --- Installed  ---
import aiohttp
from loguru import logger as log

# --- Local Application Imports ---
from ...config.models import ExchangeSettings
from .base import PublicExchangeClient


class BinancePublicClient(PublicExchangeClient):
    """A consolidated, reusable client for Binance's public REST APIs,
    conforming to the PublicExchangeClient interface."""

    def __init__(
        self,
        settings: ExchangeSettings,
        http_session: aiohttp.ClientSession,
    ):
        super().__init__(settings, http_session)
        self.spot_url = "https://api.binance.com/api/v3"
        self.linear_futures_url = "https://fapi.binance.com/fapi/v1"
        self.inverse_futures_url = "https://dapi.binance.com/dapi/v1"

    async def connect(self):
        """The shared session is managed externally. This method is a no-op."""
        pass

    async def close(self):
        """The shared session is managed externally. This method is a no-op."""
        pass

    async def _get_raw_exchange_info_for_market(
        self, market_type: str
    ) -> List[Dict[str, Any]]:
        """Fetches the raw, untransformed exchange info for a single given market type."""
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
            async with self.http_session.get(url, timeout=20) as response:
                response.raise_for_status()
                data = await response.json()
                return data.get("symbols", [])
        except Exception as e:
            log.error(f"Failed to fetch raw exchange info from {url}: {e}")
            return []

    async def get_instruments(self, currencies: List[str]) -> List[Dict[str, Any]]:
        """
        Fetches instrument details for all supported market types.
        The 'currencies' argument is ignored as Binance API does not filter by currency.
        """
        log.info("[BinancePublicClient] Fetching instruments for all market types...")
        markets_to_query = ["spot", "linear_futures", "inverse_futures"]

        tasks = [
            self._get_raw_exchange_info_for_market(market)
            for market in markets_to_query
        ]
        results_by_market = await asyncio.gather(*tasks)

        all_instruments = []
        for i, raw_instruments in enumerate(results_by_market):
            market_type = markets_to_query[i]
            if raw_instruments:
                # Inject the market_type_hint required for downstream transformation.
                for inst in raw_instruments:
                    inst["market_type_hint"] = market_type
                all_instruments.extend(raw_instruments)
                log.info(
                    f"[BinancePublicClient] Fetched {len(raw_instruments)} instruments for market '{market_type}'."
                )

        log.success(
            f"[BinancePublicClient] Total raw instruments fetched: {len(all_instruments)}"
        )
        return all_instruments

    async def get_historical_ohlc(
        self,
        instrument: str,
        start_ts: int,
        end_ts: int,
        resolution: str,
        market_type: str,
    ) -> Dict[str, Any]:
        """
        Fetches historical OHLC data from the correct Binance market API based on the
        instrument's known market type.
        """
        market_api_map = {
            "spot": (self.spot_url, "/klines"),
            "linear_futures": (self.linear_futures_url, "/klines"),
            "inverse_futures": (self.inverse_futures_url, "/klines"),
        }
        base_url, endpoint = market_api_map.get(market_type, (None, None))
        if not base_url:
            log.error(
                f"Cannot fetch OHLC for '{instrument}': unsupported market_type '{market_type}'."
            )
            return {}

        resolution_map = {"1": "1m", "5": "5m", "15": "15m", "60": "1h", "1D": "1d"}
        binance_res = resolution_map.get(str(resolution))
        if not binance_res:
            raise ValueError(f"Unsupported resolution for Binance: {resolution}")

        params = {
            "symbol": instrument,
            "interval": binance_res,
            "startTime": start_ts,
            "endTime": end_ts,
            "limit": 1500,
        }

        try:
            url = f"{base_url}{endpoint}"
            log.debug(f"Requesting OHLC from: {url} with params: {params}")
            async with self.http_session.get(
                url, params=params, timeout=30
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return {
                    "ticks": [row[0] for row in data],
                    "open": [float(row[1]) for row in data],
                    "high": [float(row[2]) for row in data],
                    "low": [float(row[3]) for row in data],
                    "close": [float(row[4]) for row in data],
                    "volume": [float(row[5]) for row in data],
                }
        except aiohttp.ClientResponseError as e:
            log.error(
                f'Failed to fetch OHLC from {url} for {instrument}: {e.status}, message="{e.message}"'
            )
            return {}
        except Exception as e:
            log.error(f"Failed to fetch OHLC from {url} for {instrument}: {e}")
            return {}

    async def get_public_trades(
        self,
        instrument: str,
        start_ts: int,
        end_ts: int,
        market_type: str,
    ) -> List[Dict[str, Any]]:
        """
        Fetches historical public trades for a given instrument using the
        aggTrades endpoint. Handles pagination to retrieve all trades in the
        given time window.
        """
        market_api_map = {
            "spot": self.spot_url,
            "linear_futures": self.linear_futures_url,
            "inverse_futures": self.inverse_futures_url,
        }
        base_url = market_api_map.get(market_type)
        if not base_url:
            log.error(
                f"Cannot fetch public trades for '{instrument}': unsupported market_type '{market_type}'."
            )
            return []

        url = f"{base_url}/aggTrades"
        all_trades = []
        current_start_ts = start_ts

        while current_start_ts < end_ts:
            params = {
                "symbol": instrument,
                "startTime": current_start_ts,
                "endTime": end_ts,
                "limit": 1000,
            }
            try:
                async with self.http_session.get(
                    url, params=params, timeout=30
                ) as response:
                    response.raise_for_status()
                    trades = await response.json()
                    if not trades:
                        break
                    for trade in trades:
                        all_trades.append(
                            {
                                "exchange": "binance",
                                "instrument_name": instrument,
                                "market_type": market_type,
                                "trade_id": str(trade["a"]),
                                "price": float(trade["p"]),
                                "quantity": float(trade["q"]),
                                "timestamp": datetime.fromtimestamp(
                                    trade["T"] / 1000, tz=timezone.utc
                                ),
                                "is_buyer_maker": trade["m"],
                            }
                        )
                    last_trade_ts = trades[-1]["T"]
                    current_start_ts = last_trade_ts + 1
                    await asyncio.sleep(0.2)
            except aiohttp.ClientResponseError as e:
                log.error(
                    f'Failed to fetch public trades from {url} for {instrument}: {e.status}, message="{e.message}"'
                )
                break
            except Exception as e:
                log.error(
                    f"Failed to fetch public trades from {url} for {instrument}: {e}"
                )
                break

        log.info(
            f"Fetched {len(all_trades)} public trades for {instrument} from {start_ts} to {end_ts}"
        )
        return all_trades
