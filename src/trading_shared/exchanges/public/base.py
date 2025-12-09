# src/trading_shared/exchanges/public/base.py

# --- Built Ins  ---
from abc import ABC, abstractmethod
from typing import List, Dict, Any

# --- Installed ---
import aiohttp 

# --- Shared Library Imports ---
from ...config.models import ExchangeSettings


class PublicExchangeClient(ABC):
    """
    Defines the standard interface for a public REST API client.
    This contract is used by services like Janitor and Backfill.
    """

    def __init__(self, settings: ExchangeSettings, http_session: aiohttp.ClientSession):
        self.settings = settings
        self.http_session = http_session
        self.base_url = settings.rest_url
        if not self.base_url:
            raise ValueError(f"REST URL for {type(self).__name__} is not configured.")

    @abstractmethod
    async def connect(self):
        """
        A placeholder for any initial connection or setup logic.
        This method SHOULD NOT create a new session.
        """
        pass

    @abstractmethod
    async def close(self):
        """
        A placeholder for any cleanup logic.
        This method MUST NOT close the shared http_session, as its lifecycle
        is managed by the service that created it.
        """
        pass

    @abstractmethod
    async def get_instruments(self, currencies: List[str]) -> List[Dict[str, Any]]:
        """Fetches all relevant instruments for the exchange for a list of currencies."""
        pass

    @abstractmethod
    async def get_historical_ohlc(
        self,
        instrument: str,
        start_ts: int,
        end_ts: int,
        resolution: str,
        market_type: str,
    ) -> Dict[str, Any]:
        """Fetches historical OHLC data for an instrument."""
        pass

    @abstractmethod
    async def get_public_trades(
        self,
        instrument: str,
        start_ts: int,
        end_ts: int,
        market_type: str,
    ) -> List[Dict[str, Any]]:
        """Fetches historical public trades for a given instrument."""
        pass