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
from .base import PublicExchangeClient # Assumes an Abstract Base Class exists here.

class DeribitPublicClient(PublicExchangeClient):
    """
    An API client for public, non-authenticated Deribit endpoints.
    This is a consolidated client for use by services like Janitor and Backfill.
    """
    def __init__(self, settings: ExchangeSettings):
        self._settings = settings
        self._session: Optional[aiohttp.ClientSession] = None
        self.rest_url = self._settings.rest_url
        if not self.rest_url:
            raise ValueError("Deribit REST API URL ('rest_url') not configured in ExchangeSettings.")

    async def connect(self):
        """Establishes the client session. No login is required."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            log.info("[DeribitPublicClient] Public aiohttp session established.")

    async def close(self):
        """Closes the client session."""
        if self._session and not self._session.closed:
            await self._session.close()
            log.info("[DeribitPublicClient] Public aiohttp session closed.")

    async def _public_request(self, endpoint: str, params: Optional[dict] = None) -> Dict[str, Any]:
        """Helper for making a public request to Deribit."""
        if not self._session or self._session.closed:
            raise ConnectionError("Session not established. Call connect() first.")

        url = f"{self.rest_url}/api/v2/{endpoint}"
        try:
            async with self._session.get(url, params=params, timeout=20) as response:
                response.raise_for_status()
                data = await response.json()
                return data.get("result", {})
        except Exception as e:
            log.error(f"Failed to fetch from Deribit public endpoint {endpoint}: {e}")
            return {}

    async def get_historical_ohlc(
        self,
        instrument: str,
        start_ts: int,
        end_ts: int,
        resolution: str,
        market_type: str,  # Unused for Deribit but required by abstract method
    ) -> Dict[str, Any]:
        """Fetches OHLC data from the TradingView-compatible endpoint."""
        params = {
            "instrument_name": instrument,
            "start_timestamp": start_ts,
            "end_timestamp": end_ts,
            "resolution": resolution,
        }
        return await self._public_request("public/get_tradingview_chart_data", params)

    # Note: The following methods are migrated from the legacy client for use by the Janitor service.
    # The transformation logic is kept local for now but should be centralized in a future refactor.

    async def get_instruments(self, currencies: List[str]) -> List[Dict[str, Any]]:
        """
        Fetches all relevant instruments by looping through the provided currencies.
        """
        all_canonical_instruments = []
        for currency in currencies:
            for kind in ["future", "option"]:
                params = {"currency": currency, "kind": kind, "expired": "false"}
                raw_instruments = await self._public_request("public/get_instruments", params)

                if raw_instruments and isinstance(raw_instruments, list):
                    transformed = [self._transform_instrument(inst) for inst in raw_instruments]
                    all_canonical_instruments.extend(transformed)
                    log.info(f"[DeribitPublicClient] Fetched and transformed {len(transformed)} {kind} instruments for {currency}.")
                await asyncio.sleep(0.2)
        return all_canonical_instruments

    def _transform_instrument(self, raw_instrument: Dict[str, Any]) -> Dict[str, Any]:
        """Transforms a single raw Deribit instrument into our canonical format."""
        exp_ts_ms = raw_instrument.get("expiration_timestamp")
        expiration_timestamp = datetime.fromtimestamp(exp_ts_ms / 1000, tz=timezone.utc) if exp_ts_ms else None

        return {
            "exchange": "deribit",
            "instrument_name": raw_instrument.get("instrument_name"),
            "market_type": "OPTION" if raw_instrument.get("kind") == "option" else "FUTURE",
            "base_asset": raw_instrument.get("base_currency"),
            "quote_asset": raw_instrument.get("quote_currency"),
            "settlement_asset": raw_instrument.get("settlement_currency") or raw_instrument.get("base_currency"),
            "tick_size": raw_instrument.get("tick_size"),
            "contract_size": raw_instrument.get("contract_size"),
            "expiration_timestamp": expiration_timestamp.isoformat() if expiration_timestamp else None,
            "data": raw_instrument,
        }