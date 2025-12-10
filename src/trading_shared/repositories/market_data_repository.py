# src/trading_shared/repositories/market_data_repository.py

# --- Built Ins ---
from typing import List, Dict, Deque, Any
from collections import deque

# --- Installed ---
import orjson
from loguru import logger as log

# --- Shared Library Imports ---
from trading_engine_core.models import StreamMessage
from trading_shared.clients.redis_client import CustomRedisClient


class MarketDataRepository:
    """
    Manages interaction with Redis for market data, including streams and caches.
    """

    def __init__(self, redis_client: CustomRedisClient):
        self._redis = redis_client

    async def add_messages_to_stream(
        self,
        stream_name: str,
        messages: List[StreamMessage] | Deque[StreamMessage],
        maxlen: int = 10000,
    ):
        """Adds a batch of messages to a Redis stream."""
        if not messages:
            return

        # Convert Pydantic models to dicts for xadd_bulk
        message_dicts = [msg.model_dump(exclude_none=True) for msg in messages]

        await self._redis.xadd_bulk(stream_name, message_dicts, maxlen=maxlen)
        log.debug(
            f"Flushed batch of {len(messages)} messages to Redis stream '{stream_name}'."
        )

    async def cache_ticker(self, symbol: str, data: Dict):
        """Caches the latest ticker data in a Redis hash."""
        redis_key = f"ticker:{symbol}"
        await self._redis.hset(redis_key, "payload", orjson.dumps(data))

    async def get_ticker_data(
        self,
        instrument_name: str,
    ) -> dict[str, Any] | None:
        """Retrieves and decodes ticker data from a Redis hash."""
        key = f"ticker:{instrument_name}"
        try:
            payload = await self._redis.hget(key, "payload")
            if not payload:
                return None
            return orjson.loads(payload)
        except orjson.JSONDecodeError as e:
            log.error(
                f"Failed to decode ticker data for '{instrument_name}'. "
                f"Possible data corruption in Redis key '{key}'. Error: {e}"
            )
            return None
