# src/trading_shared/exchanges/public/deribit.py

# --- Built Ins ---
from typing import List, Dict, Any
from datetime import datetime, timezone

# --- Installed ---
import aiohttp
from loguru import logger as log

# --- Shared Library Imports ---
from .base import PublicClient
from ..trading.deribit_constants import ApiMethods
from ...config.models import ExchangeSettings


class DeribitPublicClient(PublicClient):
    """
    Client for Deribit's public REST API endpoints.
    """

    _request_id = 0

    def __init__(self, settings: ExchangeSettings, http_session: aiohttp.ClientSession):
        super().__init__()
        if not settings.rest_url:
            raise ValueError("Deribit rest_url not configured.")
        self.base_url = settings.rest_url
        self.http_session = http_session

    async def _make_request(self, method: str, params: Dict[str, Any]) -> Dict:
        """Helper to make a JSON-RPC request to the Deribit API."""
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        try:
            async with self.http_session.post(
                f"{self.base_url}/api/v2/{method}", json=payload
            ) as response:
                response.raise_for_status()
                data = await response.json()
                if "error" in data:
                    log.error(f"Deribit API error for method {method}: {data['error']}")
                    return {}
                return data.get("result", {})
        except aiohttp.ClientError as e:
            log.error(f"Failed to call Deribit API method {method}: {e}")
            return {}
        except Exception:
            log.exception(
                f"An unexpected error occurred during Deribit API call for {method}"
            )
            return {}

    def _transform_candle_data_to_canonical(
        self,
        raw_candles: Dict[str, List],
        exchange: str,
        instrument_name: str,
        resolution: str,
    ) -> List[Dict[str, Any]]:
        """Transforms the Deribit chart data response into our standard list of dicts."""
        canonical_candles = []
        ticks = raw_candles.get("ticks", [])
        opens = raw_candles.get("open", [])
        highs = raw_candles.get("high", [])
        lows = raw_candles.get("low", [])
        closes = raw_candles.get("close", [])
        volumes = raw_candles.get("volume", [])

        for i, tick in enumerate(ticks):
            canonical_candles.append(
                {
                    "exchange": exchange,
                    "instrument_name": instrument_name,
                    "resolution": resolution,
                    "tick": tick,
                    "open": opens[i],
                    "high": highs[i],
                    "low": lows[i],
                    "close": closes[i],
                    "volume": volumes[i],
                }
            )
        return canonical_candles

    async def connect(self):
        """The shared session is managed externally. This method is a no-op."""
        pass

    async def close(self):
        """The shared session is managed externally. This method is a no-op."""
        pass

    async def get_instruments(self, currencies: List[str]) -> List[Dict[str, Any]]:
        """Fetches all instruments for the given currencies from Deribit."""
        all_instruments = []
        for currency in currencies:
            params = {"currency": currency, "expired": False}
            instruments = await self._make_request(ApiMethods.GET_INSTRUMENTS, params)
            if instruments:
                all_instruments.extend(instruments)
        log.success(
            f"[DeribitPublicClient] Total raw instruments fetched: {len(all_instruments)}"
        )
        return all_instruments

    async def get_public_ohlc(
        self,
        instrument_name: str,
        resolution: str,
        start_timestamp_ms: int,
        limit: int = 1000,  # Note: Deribit doesn't use a 'limit' param for this endpoint
    ) -> List[Dict[str, Any]]:
        """
        Fetches OHLC data from Deribit's public/get_tradingview_chart_data endpoint.
        Deribit's API takes a time range, so it is not paginated like Binance's.
        """
        # Deribit's resolution format is minutes as a string, e.g., '1', '15', '60', or '1D'
        resolution_map = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "1d": "1D"}
        deribit_resolution = resolution_map.get(resolution)
        if not deribit_resolution:
            log.error(
                f"Unsupported resolution for Deribit: {resolution}. Must be one of {list(resolution_map.keys())}"
            )
            return []

        # We fetch up to the current time.
        end_timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        params = {
            "instrument_name": instrument_name,
            "start_timestamp": start_timestamp_ms,
            "end_timestamp": end_timestamp_ms,
            "resolution": deribit_resolution,
        }

        log.info(f"Fetching OHLC for {instrument_name} from Deribit...")
        raw_data = await self._make_request(
            ApiMethods.GET_TRADINGVIEW_CHART_DATA, params
        )

        if not raw_data or raw_data.get("status") != "ok":
            log.warning(f"No OHLC data returned from Deribit for {instrument_name}.")
            return []

        return self._transform_candle_data_to_canonical(
            raw_candles=raw_data,
            exchange="deribit",
            instrument_name=instrument_name,
            resolution=resolution,
        )
