# src\trading_shared\repositories\hybrid_market_data_repository.py


from trading_engine_core.models import OHLC

from trading_shared.cache import InstrumentCache
from trading_shared.clients import PostgresClient, RedisClient


class HybridMarketDataRepository:
    def __init__(self, redis: RedisClient, postgres: PostgresClient, cache: InstrumentCache):
        self._redis = redis
        self._db = postgres
        self._cache = cache

    async def get_history(self, exchange: str, symbol: str, lookback: str) -> list[OHLC]:
        """
        The Service calls this SINGLE method.
        It does not care if the data comes from RAM or Disk.
        """

        # 1. Determine the Storage Mode (The Routing Logic)
        # The cache is updated via Redis Pub/Sub from the Janitor's ledger
        storage_mode = self._cache.get_storage_mode(exchange, symbol)

        if storage_mode == "PERSISTENT":
            return await self._fetch_from_postgres(exchange, symbol, lookback)

        elif storage_mode == "EPHEMERAL":
            return await self._fetch_from_redis(exchange, symbol, lookback)

        else:
            # Fallback/Error handling
            return []

    async def _fetch_from_postgres(self, exchange, symbol, lookback) -> list[OHLC]:
        # SQL Query logic
        # Returns List[OHLC] Pydantic models
        pass

    async def _fetch_from_redis(self, exchange, symbol, lookback) -> list[OHLC]:
        # Redis Lrange logic
        # Deserializes JSON -> Returns List[OHLC] Pydantic models
        pass
