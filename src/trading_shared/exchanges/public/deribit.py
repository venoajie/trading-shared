# src/trading_shared/exchanges/public/deribit.py

# --- Built Ins ---
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# --- Installed ---
import aiohttp
from loguru import logger as log

# --- Local Application Imports ---
from ...config.models import ExchangeSettings
from .base import PublicExchangeClient


class DeribitPublicClient(PublicExchangeClient):
    """
    An API client for public, non-authenticated Deribit endpoints.
    """

    def __init__(
        self,
        settings: ExchangeSettings,
        http_session: aiohttp.ClientSession,
    ):
        super().__init__(settings, http_session)

    async def connect(self):
        """The shared session is managed externally. This method is a no-op."""
        pass

    async def close(self):
        """The shared session is managed externally. This method is a no-op."""
        pass

    async def _public_request(
        self,
        endpoint: str,
        params: Optional[dict] = None,
    ) -> Any:
        """Helper for making a public request to Deribit."""

        url = f"{self.base_url}/api/v2/{endpoint}"
        try:
            # The get() call will raise ClientError if the session is closed.
            async with self.http_session.get(url, params=params, timeout=20) as response:
                response.raise_for_status()
                data = await response.json()
                if isinstance(data, dict):
                    return data.get("result", {})
                return data.get("result", [])
        except aiohttp.ClientError as e:
            # More specific catch for aiohttp-related issues, including a closed session.
            log.error(
                f"Failed to fetch from Deribit public endpoint {endpoint}: {e}"
            )
            return [] if not endpoint.endswith("chart_data") else {}
        except Exception as e:
            log.error(
                f"An unexpected error occurred for Deribit endpoint {endpoint}: {e}"
            )
            return [] if not endpoint.endswith("chart_data") else {}
        
    async def get_instruments(
        self,
        currencies: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Fetches all relevant raw instruments by looping through the provided currencies.
        Returns the data without transformation.
        """
        all_raw_instruments = []
        for currency in currencies:
            for kind in ["future", "option"]:
                params = {"currency": currency, "kind": kind, "expired": "false"}
                raw_instruments = await self._public_request(
                    "public/get_instruments", params
                )
                if raw_instruments and isinstance(raw_instruments, list):
                    all_raw_instruments.extend(raw_instruments)
                    log.info(
                        f"[DeribitPublicClient] Fetched {len(raw_instruments)} raw {kind} instruments for {currency}."
                    )
                # Rate limit requests
                await asyncio.sleep(0.2)
        return all_raw_instruments

    async def get_historical_ohlc(
        self,
        instrument: str,
        start_ts: int,
        end_ts: int,
        resolution: str,
        market_type: str,
    ) -> Dict[str, Any]:
        """Fetches OHLC data from the TradingView-compatible endpoint."""
        params = {
            "instrument_name": instrument,
            "start_timestamp": start_ts,
            "end_timestamp": end_ts,
            "resolution": resolution,
        }

        return await self._public_request("public/get_tradingview_chart_data", params)

    async def get_public_trades(
        self,
        instrument: str,
        start_ts: int,
        end_ts: int,
        market_type: str,
    ) -> List[Dict[str, Any]]:
        """Fetches historical public trades for a given instrument with pagination."""
        log.info(f"Fetching public trades for {instrument} from {start_ts} to {end_ts}")
        all_trades = []
        current_start_ts = start_ts

        while current_start_ts < end_ts:
            params = {
                "instrument_name": instrument,
                "start_timestamp": current_start_ts,
                "end_timestamp": end_ts,
                "count": 1000,
                "sorting": "asc",
            }

            result = await self._public_request(
                "public/get_last_trades_by_instrument", params
            )
            trades = result.get("trades", [])
            if not trades:
                break

            for trade in trades:
                all_trades.append(
                    {
                        "exchange": "deribit",
                        "instrument_name": instrument,
                        "market_type": market_type,
                        "trade_id": trade.get("trade_id", ""),
                        "price": trade.get("price", 0),
                        "quantity": trade.get("amount", 0),
                        "timestamp": datetime.fromtimestamp(
                            trade["timestamp"] / 1000, tz=timezone.utc
                        ),
                        "is_buyer_maker": trade.get("direction", "") == "sell",
                    }
                )

            last_trade_ts = trades[-1]["timestamp"]
            if last_trade_ts >= end_ts:
                break

            current_start_ts = last_trade_ts + 1
            await asyncio.sleep(0.2)

        log.info(f"Fetched {len(all_trades)} public trades for {instrument}")
        return all_trades

    def _transform_instrument(
        self,
        raw_instrument: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Transforms a single raw Deribit instrument into our canonical format."""
        exp_ts_ms = raw_instrument.get("expiration_timestamp")
        expiration_timestamp = (
            datetime.fromtimestamp(exp_ts_ms / 1000, tz=timezone.utc)
            if exp_ts_ms
            else None
        )

        return {
            "exchange": "deribit",
            "instrument_name": raw_instrument.get("instrument_name"),
            "market_type": "OPTION"
            if raw_instrument.get("kind") == "option"
            else "FUTURE",
            "base_asset": raw_instrument.get("base_currency"),
            "quote_asset": raw_instrument.get("quote_currency"),
            "settlement_asset": raw_instrument.get("settlement_currency")
            or raw_instrument.get("base_currency"),
            "tick_size": raw_instrument.get("tick_size"),
            "contract_size": raw_instrument.get("contract_size"),
            "expiration_timestamp": expiration_timestamp.isoformat()
            if expiration_timestamp
            else None,
            "data": raw_instrument,
        }
