# src\trading_shared\repositories\hybrid_market_data_repository.py

import json

from trading_engine_core.models import StorageMode

from trading_shared.cache.universe_cache import UniverseCache
from trading_shared.clients.postgres_client import PostgresClient
from trading_shared.clients.redis_client import CustomRedisClient


class HybridMarketDataRepository:
    """
    A unified facade for fetching market data.
    Routes queries to PostgreSQL or Redis based on the asset's storage tier.
    """

    def __init__(
        self,
        postgres_client: PostgresClient,
        redis_client: CustomRedisClient,
        universe_cache: UniverseCache,
    ):
        self._db = postgres_client
        self._redis = redis_client
        self._cache = universe_cache

    async def get_history(self, exchange: str, symbol: str, lookback_minutes: int) -> list[dict]:
        """
        Fetches historical OHLC data.
        Returns a list of dictionaries (compatible with OHLCModel).
        """
        storage_mode = await self._cache.get_storage_mode(symbol)

        if storage_mode == StorageMode.PERSISTENT:
            return await self._fetch_from_postgres(exchange, symbol, lookback_minutes)
        else:
            return await self._fetch_from_redis(exchange, symbol, lookback_minutes)

    async def _fetch_from_postgres(self, exchange: str, symbol: str, limit: int) -> list[dict]:
        query = """
        SELECT
            exchange, instrument_name, resolution,
            extract(epoch from tick) * 1000 as tick,
            "open", high, low, "close", volume,
            taker_buy_volume, taker_sell_volume
        FROM ohlc
        WHERE exchange = $1 AND instrument_name = $2 AND resolution = '1'
        ORDER BY tick DESC LIMIT $3
        """
        records = await self._db.fetch(query, exchange, symbol, limit)
        # Sort ASC for calculation (oldest first)
        return [dict(r) for r in reversed(records)]

    async def _fetch_from_redis(self, exchange: str, symbol: str, limit: int) -> list[dict]:
        key = f"market:buffer:ohlc:{exchange.lower()}:{symbol.upper()}"
        # LTRIM/LRANGE: 0 is oldest, -1 is newest.
        # We want the last N items.
        raw_candles = await self._redis.lrange(key, -limit, -1)
        if not raw_candles:
            return []

        parsed = []
        for c in raw_candles:
            try:
                parsed.append(json.loads(c))
            except json.JSONDecodeError:
                continue
        return parsed
