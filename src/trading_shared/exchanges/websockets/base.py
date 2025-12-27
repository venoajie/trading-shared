# src/trading_shared/exchanges/websockets/base.py

# --- Built Ins ---
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

# --- Local Application Imports ---
from ...clients.redis_client import CustomRedisClient
from ...repositories.instrument_repository import InstrumentRepository
from ...repositories.market_data_repository import MarketDataRepository

# --- Shared Library Imports  ---
from trading_engine_core.models import StreamMessage, MarketDefinition


class AbstractWsClient(ABC):
    """
    Abstract base class for exchange-specific WebSocket clients.
    It defines the core interface for connecting, processing messages, and closing.
    """

    def __init__(
        self,
        market_definition: MarketDefinition,
        market_data_repo: MarketDataRepository,
        instrument_repo: InstrumentRepository,
        redis_client: Optional[CustomRedisClient] = None,
        stream_name: str | None = None,
    ):
        """
        Initializes the base client.

        Args:
            market_definition: The market definition for this client.
            market_data_repo: Repository for persisting market data.
            instrument_repo: Repository for instrument lookups.
            redis_client: An optional Redis client, required for private scopes.
            stream_name: The mandatory Redis stream to publish data to.
        """
        self.market_def = market_definition
        self.exchange_name = self.market_def.exchange
        self.market_data_repo = market_data_repo
        self.instrument_repo = instrument_repo
        self.redis_client = redis_client

        if not stream_name:
            raise ValueError(
                f"[{self.exchange_name}] 'stream_name' must be provided to the WebSocket client constructor."
            )
        self.stream_name = stream_name

    @abstractmethod
    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """Connects to the WebSocket and yields processed messages."""
        yield

    @abstractmethod
    async def process_messages(self):
        """The main run loop for the client to process messages."""
        pass

    @abstractmethod
    async def close(self):
        """Gracefully closes the WebSocket connection."""
        pass
