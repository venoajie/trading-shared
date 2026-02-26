
# src/trading_shared/repositories/hybrid_market_data_repository.py

import orjson
from loguru import logger as log

from trading_shared.cache.universe_cache import UniverseCache
from trading_shared.clients.postgres_client import PostgresClient
from trading_shared.clients.redis_client import CustomRedisClient
from trading_shared.core.models import StorageMode


class HybridMarketDataRepository:
    def __init__(
        self,
        postgres_client: PostgresClient,
        redis_client: CustomRedisClient,
        universe_cache: UniverseCache,
    ):
        self._db = postgres_client
        self._redis = redis_client
        self._cache = universe_cache
        self.BASE_RESOLUTION = "1m"  # Enforce standardized resolution

    async def get_history(self, exchange: str, symbol: str, lookback_minutes: int) -> list[dict]:
        storage_mode = await self._cache.get_storage_mode(symbol)

        if storage_mode == StorageMode.PERSISTENT:
            history = await self._fetch_from_postgres(exchange, symbol, lookback_minutes)
            if history:
                return history
            log.debug(f"DB empty for {symbol}. Falling back to Redis buffer.")

        return await self._fetch_from_redis(exchange, symbol, lookback_minutes)

    async def _fetch_from_postgres(self, exchange: str, symbol: str, limit: int) -> list[dict]:
        """Fetches from PostgreSQL for assets with persistent storage."""
        # FIX: Change resolution = '1' to resolution = '1m' to match the Distributor's write format
        query = """
        SELECT
            exchange, instrument_name, resolution,
            extract(epoch from tick) * 1000 as tick,
            "open", high, low, "close", volume,
            taker_buy_volume, taker_sell_volume
        FROM ohlc
        WHERE exchange = $1 AND instrument_name = $2 AND resolution = '1m'
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
        # FIXED: Match Distributor's LPUSH List architecture
        key = f"market:buffer:ohlc:{exchange.lower()}:{symbol.upper()}"

        try:
            # Use LRANGE for Lists, not ZREVRANGE
            raw_candles = await self._redis.lrange(key, 0, limit - 1)
            if not raw_candles:
                return []

            parsed = []
            for c in raw_candles:
                try:
                    parsed.append(orjson.loads(c))
                except orjson.JSONDecodeError:
                    continue

            # LPUSH puts newest items at index 0. Reverse to get chronological order.
            return list(reversed(parsed))
        except Exception as e:
            log.error(f"Redis List fetch failed for {symbol} (Key: {key}): {e}")
            return []