# src/trading_shared/repositories/market_data_repository.py

# --- Built Ins ---
from collections import deque
from typing import Any

# --- Installed ---
import orjson
from loguru import logger as log

# --- Shared Library Imports ---
from trading_engine_core.models import StreamMessage, TakerMetrics

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
        messages: list[StreamMessage] | deque[StreamMessage],
        maxlen: int = 10000,
    ):
        """Adds a batch of messages to a Redis stream."""
        if not messages:
            return

        # Convert Pydantic models to dicts for xadd_bulk
        message_dicts = [msg.model_dump(exclude_none=True) for msg in messages]

        await self._redis.xadd_bulk(stream_name, message_dicts, maxlen=maxlen)
        log.debug(f"Flushed batch of {len(messages)} messages to Redis stream '{stream_name}'.")

    async def cache_ticker(
        self,
        symbol: str,
        data: dict,
    ):
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
            log.error(f"Failed to decode ticker data for '{instrument_name}'. Possible data corruption in Redis key '{key}'. Error: {e}")
            return None

    async def update_realtime_candle(
        self,
        exchange: str,
        instrument_name: str,
        candle_data: dict,
    ):
        """
        Updates the 'Live' in-flight candle in Redis using the v2.0 data contract.
        Used by the Distributor for real-time analytics visibility.
        """

        key = f"market:cache:{exchange.lower()}:ohlc:live:{instrument_name.upper()}"

        # We use HSET with mapping to update fields atomically
        # We convert values to strings to ensure Redis compatibility
        # Updated for Microstructure Alpha: Now includes Taker Buy/Sell Volume
        mapping = {
            "tick": str(candle_data["tick"]),
            "open": str(candle_data["open"]),
            "high": str(candle_data["high"]),
            "low": str(candle_data["low"]),
            "close": str(candle_data["close"]),
            "volume": str(candle_data["volume"]),
            "taker_buy_volume": str(candle_data.get("taker_buy_volume", 0.0)),
            "taker_sell_volume": str(candle_data.get("taker_sell_volume", 0.0)),
            "updated_at": str(candle_data.get("updated_at", "")),
        }

        try:
            pipe = await self._redis.pipeline()
            # Use a pipeline for atomic HSET and EXPIRE operations
            await pipe.hset(name=key, mapping=mapping)
            # TTL updated to 70 seconds as per the spec
            await pipe.expire(key, 70)
            await pipe.execute()
        except Exception:
            log.exception(f"Failed to update live candle for key '{key}'")

    async def get_realtime_candle(
        self,
        exchange: str,
        instrument_name: str,
    ) -> dict[str, Any] | None:
        """
        Retrieves the current in-flight candle from Redis using the v2.0 data contract.
        """
        key = f"market:cache:{exchange.lower()}:ohlc:live:{instrument_name.upper()}"
        data = await self._redis.hgetall(key)

        if not data:
            return None

        # Convert byte strings back to appropriate types
        try:
            return {
                "tick": int(data[b"tick"]),
                "open": float(data[b"open"]),
                "high": float(data[b"high"]),
                "low": float(data[b"low"]),
                "close": float(data[b"close"]),
                "volume": float(data[b"volume"]),
                "taker_buy_volume": float(data.get(b"taker_buy_volume", 0.0)),
                "taker_sell_volume": float(data.get(b"taker_sell_volume", 0.0)),
                "updated_at": data[b"updated_at"].decode("utf-8"),
            }
        except (KeyError, ValueError) as e:
            log.warning(f"Corrupt realtime candle in Redis for {instrument_name}: {e}")
            return None

    async def set_market_regime(
        self,
        instrument_name: str,
        regime: str,
    ):
        """
        Publishes the calculated regime to Redis for the Executor to consume.
        """
        key = f"system:regime:deribit:{instrument_name}"
        await self._redis.set(key, regime)

    async def set_market_metrics(self, exchange: str, instrument_name: str, metrics: dict[str, Any], ttl: int = 60):
        """
        Publishes calculated microstructure metrics to Redis.
        Key: market:metrics:{exchange}:rvol:{instrument}
        Note: 'rvol' is legacy naming in the key pattern, but payload includes full suite (Delta, TBSR).
        """
        # Adhering to Data Contract 5.7.1
        key = f"market:metrics:{exchange.lower()}:rvol:{instrument_name.upper()}"

        # We store as a hash for atomic field access if needed,
        # but flattening to JSON string is often easier for consumers reading the whole object.
        # However, the Data Contract specifies Redis Hash.

        # Convert all values to strings for Redis Hash compatibility
        mapping = {k: str(v) for k, v in metrics.items()}

        try:
            pipe = await self._redis.pipeline()
            await pipe.hset(name=key, mapping=mapping)
            await pipe.expire(key, ttl)
            await pipe.execute()
        except Exception:
            log.exception(f"Failed to publish metrics for {instrument_name}")

    async def get_market_metrics(self, exchange: str, instrument_name: str) -> dict[str, Any] | None:
        """
        Retrieves the latest calculated metrics for a specific instrument.
        Used by Strategist.
        """
        key = f"market:metrics:{exchange.lower()}:rvol:{instrument_name.upper()}"
        data = await self._redis.hgetall(key)

        if not data:
            return None

        # Decode bytes to native types
        decoded = {}
        for k, v in data.items():
            key_str = k.decode("utf-8")
            val_str = v.decode("utf-8")
            try:
                # Attempt float conversion for numerical fields
                decoded[key_str] = float(val_str)
            except ValueError:
                decoded[key_str] = val_str

        return decoded

    async def set_taker_metrics(self, exchange: str, metrics: TakerMetrics):
        """
        Publishes real-time Taker metrics to Redis Hash.
        Key: market:metrics:taker:{exchange}:{symbol}
        """
        key = f"market:metrics:taker:{exchange.lower()}:{metrics.symbol.upper()}"

        # Convert model to dict and values to strings
        mapping = {k: str(v) for k, v in metrics.model_dump().items()}

        try:
            pipe = await self._redis.pipeline()
            await pipe.hset(name=key, mapping=mapping)
            await pipe.expire(key, 120)  # Short TTL, this is hot data
            await pipe.execute()
        except Exception:
            log.exception(f"Failed to publish taker metrics for {metrics.symbol}")

    async def get_taker_metrics(self, exchange: str, symbol: str) -> TakerMetrics | None:
        key = f"market:metrics:taker:{exchange.lower()}:{symbol.upper()}"
        data = await self._redis.hgetall(key)

        if not data:
            return None

        try:
            # Decode Redis bytes
            decoded = {k.decode("utf-8"): v.decode("utf-8") for k, v in data.items()}
            return TakerMetrics.model_validate(decoded)
        except Exception:
            return None
