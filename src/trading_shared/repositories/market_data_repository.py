
# src/trading_shared/repositories/market_data_repository.py

from collections import deque
from typing import Any, Dict

import orjson
from loguru import logger as log
from trading_engine_core.models import StreamMessage, TakerMetrics, OHLCModel

from trading_shared.clients.redis_client import CustomRedisClient


class MarketDataRepository:
    """
    Manages interaction with Redis for market data.
    Enforces strict TTLs to prevent data stagnation (Zombie Data).
    """

    def __init__(self, redis_client: CustomRedisClient):
        self._redis = redis_client

    async def add_messages_to_stream(
        self,
        stream_name: str,
        messages: list[StreamMessage] | deque[StreamMessage],
        maxlen: int = 10000,
    ):
        if not messages:
            return

        # Optimize: Batch dump
        message_dicts = [msg.model_dump(exclude_none=True) for msg in messages]
        await self._redis.xadd_bulk(stream_name, message_dicts, maxlen=maxlen)
        log.debug(f"Flushed batch of {len(messages)} messages to Redis stream '{stream_name}'.")

    # MODIFIED: Corrected type hint and added TTL parameter
    async def cache_ticker(self, symbol: str, data: Dict[str, Any], ttl_seconds: int = 5400):
        """Caches ticker data with a 90-minute TTL."""
        redis_key = f"ticker:{symbol.upper()}"
        try:
            pipe = await self._redis.pipeline()
            # Storing as a JSON string in a single field is efficient for full object retrieval
            await pipe.hset(redis_key, "payload", orjson.dumps(data))
            await pipe.expire(redis_key, ttl_seconds)
            await pipe.execute()
        except Exception:
            log.exception(f"Failed to cache ticker for {symbol}")


    async def get_ticker_data(self, instrument_name: str) -> dict[str, Any] | None:
        key = f"ticker:{instrument_name.upper()}"
        try:
            payload = await self._redis.hget(key, "payload")
            if not payload:
                return None
            return orjson.loads(payload)
        except orjson.JSONDecodeError as e:
            log.error(f"Failed to decode ticker data for '{instrument_name}': {e}")
            return None

    async def update_realtime_candle(self, exchange: str, instrument_name: str, candle_data: dict):
        """
        Updates the 'Live' in-flight candle.
        CRITICAL: TTL is set to 5 seconds. If ingestion stops, this key MUST vanish
        so downstream services (Analyzer) stop producing signals on stale data.
        """
        key = f"market:cache:{exchange.lower()}:ohlc:live:{instrument_name.upper()}"

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
            await pipe.hset(name=key, mapping=mapping)
            await pipe.expire(key, 5)  # <--- ZOMBIE DATA KILL SWITCH
            await pipe.execute()
        except Exception:
            log.exception(f"Failed to update live candle for key '{key}'")
    
    async def persist_ephemeral_candles(self, candles: list[OHLCModel]):
        """Persists a batch of completed candles designated as EPHEMERAL."""
        # This functionality might be better named or placed, but for now, it handles
        # writing completed candles to a final resting place in Redis if needed.
        # For this system, we only care about the live candle, so this might be a no-op
        # or could be used to store a short history.
        pass


    async def get_realtime_candle(self, exchange: str, instrument_name: str) -> dict[str, Any] | None:
        key = f"market:cache:{exchange.lower()}:ohlc:live:{instrument_name.upper()}"
        data = await self._redis.hgetall(key)

        if not data:
            return None

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

    async def set_market_metrics(self, exchange: str, instrument_name: str, metrics: dict[str, Any], ttl: int = 60):
        key = f"market:metrics:{exchange.lower()}:rvol:{instrument_name.upper()}"
        mapping = {k: str(v) for k, v in metrics.items()}
        try:
            pipe = await self._redis.pipeline()
            await pipe.hset(name=key, mapping=mapping)
            await pipe.expire(key, ttl)
            await pipe.execute()
        except Exception:
            log.exception(f"Failed to publish metrics for {instrument_name}")

    async def get_market_metrics(self, exchange: str, instrument_name: str) -> dict[str, Any] | None:
        key = f"market:metrics:{exchange.lower()}:rvol:{instrument_name.upper()}"
        data = await self._redis.hgetall(key)
        if not data:
            return None

        decoded = {}
        for k, v in data.items():
            key_str = k.decode("utf-8")
            val_str = v.decode("utf-8")
            try:
                decoded[key_str] = float(val_str)
            except ValueError:
                decoded[key_str] = val_str
        return decoded

    async def set_taker_metrics(self, exchange: str, metrics: TakerMetrics):
        key = f"market:metrics:taker:{exchange.lower()}:{metrics.symbol.upper()}"
        mapping = {k: str(v) for k, v in metrics.model_dump().items()}
        try:
            pipe = await self._redis.pipeline()
            await pipe.hset(name=key, mapping=mapping)
            await pipe.expire(key, 120)
            await pipe.execute()
        except Exception:
            log.exception(f"Failed to publish taker metrics for {metrics.symbol}")

    async def get_taker_metrics(self, exchange: str, symbol: str) -> TakerMetrics | None:
        key = f"market:metrics:taker:{exchange.lower()}:{symbol.upper()}"
        data = await self._redis.hgetall(key)
        if not data:
            return None
        try:
            decoded = {k.decode("utf-8"): v.decode("utf-8") for k, v in data.items()}
            return TakerMetrics.model_validate(decoded)
        except Exception:
            return None