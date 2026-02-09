# src/trading_shared/repositories/hybrid_market_data_repository.py

import orjson  # Use the faster orjson library for consistency
from loguru import logger as log

from trading_shared.cache.universe_cache import UniverseCache
from trading_shared.clients.postgres_client import PostgresClient
from trading_shared.clients.redis_client import CustomRedisClient
from trading_shared.core.models import StorageMode


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
        """Fetches from PostgreSQL for assets with persistent storage."""
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
        try:
            records = await self._db.fetch(query, exchange, symbol, limit)
            # Sort ASC for calculation (oldest first)
            return [dict(r) for r in reversed(records)]
        except Exception as e:
            log.warning(f"Postgres fetch failed for {symbol}: {e}")
            return []

    async def _fetch_from_redis(self, exchange: str, symbol: str, limit: int) -> list[dict]:
        """
        Fetches from Redis using non-blocking ZSet commands.
        """
        # Data Contract: Points to the canonical 1-minute time-series ZSet.
        key = f"market:series:{exchange.lower()}:{symbol.upper()}:1m"

        try:
            # ZREVRANGE is the correct non-blocking command to get the latest N items.
            # It returns items from highest score (newest) to lowest.
            raw_candles = await self._redis.zrevrange(key, 0, limit - 1)
            if not raw_candles:
                return []

            parsed = []
            for c in raw_candles:
                try:
                    # The members of the ZSet are orjson-encoded strings.
                    parsed.append(orjson.loads(c))
                except orjson.JSONDecodeError:
                    continue

            # The result from zrevrange is newest-to-oldest.
            # Most indicator calculations expect oldest-to-newest.
            return list(reversed(parsed))
        except Exception as e:
            log.warning(f"Redis ZSet fetch failed for {symbol}: {e}")
            return []
