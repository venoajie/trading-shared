# src/trading_shared/exchanges/websockets/base.py

from abc import ABC, abstractmethod
from typing import AsyncGenerator

# --- Shared Library Imports ---
# These imports are now validated against the provided models.py
from trading_engine_core.models import MarketDefinition, StreamMessage
from ...clients.postgres_client import PostgresClient
from ...clients.redis_client import CustomRedisClient

class AbstractWsClient(ABC):
    """An abstract base class for exchange WebSocket clients."""

    def __init__(
        self,
        market_definition: MarketDefinition,
        redis_client: CustomRedisClient,
        postgres_client: PostgresClient,
    ):
        self.market_def = market_definition
        self.exchange_name = market_definition.exchange
        self.redis_client = redis_client
        self.postgres_client = postgres_client
        # Standardize stream name format
        self.stream_name = f"stream:market_data:{self.exchange_name}"

    @abstractmethod
    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """Connects, authenticates, subscribes, and yields canonical StreamMessage objects."""
        yield # This makes the method an async generator

    @abstractmethod
    async def process_messages(self):
        """A generic processor that consumes from connect() and pushes to a data stream."""
        raise NotImplementedError

    @abstractmethod
    async def close(self):
        """Gracefully closes the connection and cleans up resources."""
        raise NotImplementedError