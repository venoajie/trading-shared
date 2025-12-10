# src/trading_shared/exchanges/public/base.py

from abc import ABC, abstractmethod
from typing import List, Dict, Any

class PublicExchangeClient(ABC):
    """
    An abstract base class defining the contract for all public-facing REST API clients.
    Any concrete implementation of this class must provide methods for fetching
    instruments and OHLC data.
    """

    @abstractmethod
    async def connect(self):
        """
        Handles any necessary setup for the client. For clients using a shared
        HTTP session, this may be a no-op.
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self):
        """
        Handles any necessary cleanup for the client. For clients using a shared
        HTTP session, this may be a no-op.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_instruments(self, currencies: List[str]) -> List[Dict[str, Any]]:
        """
        Fetches all relevant instruments from the exchange.
        Should return the raw instrument data, which will be transformed upstream.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_public_ohlc(
        self,
        instrument_name: str,
        resolution: str,
        start_timestamp_ms: int,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Fetches OHLC (k-line) data for a symbol. This method is expected to handle
        any necessary API pagination to retrieve a complete dataset from the start time.
        The returned data must be in the canonical application format.
        """
        raise NotImplementedError