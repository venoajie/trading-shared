
# src/trading_shared/clients/redis_client.py

# --- Built Ins  ---
import asyncio
import socket
import time
from collections.abc import Awaitable, Callable
from collections import deque
from contextlib import asynccontextmanager
from typing import Any, Optional, TypeVar

# --- Installed  ---
import orjson
import redis.asyncio as aioredis
from loguru import logger as log
from redis import exceptions as redis_exceptions
from redis.asyncio.client import PubSub, Pipeline

# --- Local Application Imports ---
from ..config.models import RedisSettings

T = TypeVar("T")

class CustomRedisClient:
    """
    A resilient, production-grade client wrapper for the redis-py async client.
    This version fixes the instantiation bug while preserving all legacy resilience features.
    """

    def __init__(self, settings: RedisSettings):
        self._settings = settings
        # FIX: This attribute holds the single, managed client instance, not a pool object.
        self._client: Optional[aioredis.Redis] = None
        self._circuit_open = False
        self._last_failure = 0
        self._reconnect_attempts = 0
        self._write_sem = asyncio.Semaphore(self._settings.write_concurrency_limit)
        self._lock = asyncio.Lock()

    # --- Connection and Lifecycle Management ---

    async def connect(self):
        """Public method to ensure the client is connected."""
        await self._get_client()

    async def __aenter__(self):
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _safe_close_client(self):
        """Safely closes the current client instance."""
        client_to_close = self._client
        self._client = None  # Immediately prevent reuse
        if client_to_close:
            try:
                await client_to_close.close()
            except Exception as e:
                log.warning(f"Non-critical error while closing stale Redis client: {e}")

    async def _get_client(self) -> aioredis.Redis:
        """
        [CORRECTED] Returns a single, managed Redis client instance, implementing a circuit breaker.
        """
        async with self._lock:
            if self._client:
                return self._client

            if self._circuit_open:
                cooldown = min(60, 5 * (2**self._reconnect_attempts))
                if time.time() - self._last_failure < cooldown:
                    raise ConnectionError("Redis unavailable - circuit breaker is open.")
                self._circuit_open = False

            try:
                password = self._settings.password.get_secret_value() if self._settings.password else None
                self._client = aioredis.from_url(
                    str(self._settings.url),
                    password=password,
                    db=int(self._settings.db or 0),
                    socket_connect_timeout=self._settings.socket_connect_timeout,
                    decode_responses=False, # Essential for binary-safe operations
                )
                await asyncio.wait_for(self._client.ping(), timeout=10)
                self._reconnect_attempts = 0
                log.info("Redis connection established.")
                return self._client
            except Exception as e:
                log.warning(f"Initial Redis connection failed: {e}")
                await self._safe_close_client()
                self._circuit_open = True
                self._last_failure = time.time()
                self._reconnect_attempts += 1
                raise ConnectionError("Redis connection failed on initial attempt.") from e

    async def close(self):
        """Gracefully closes the active Redis connection."""
        async with self._lock:
            await self._safe_close_client()
            log.info("Redis client connection closed.")

    async def execute_resiliently(
        self,
        func: Callable[[aioredis.Redis], Awaitable[T]],
        command_name_for_logging: str,
    ) -> T:
        """
        [RETAINED] Executes a Redis command with a robust retry and circuit-breaking mechanism.
        """
        last_exception: Optional[Exception] = None
        for attempt in range(self._settings.max_retries):
            try:
                client = await self._get_client()
                return await func(client)
            except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError, ConnectionError) as e:
                log.warning(
                    f"Redis command '{command_name_for_logging}' failed (attempt {attempt + 1}/{self._settings.max_retries}): {e}"
                )
                last_exception = e
                await self._safe_close_client()  # Force reconnect on next attempt
                if attempt < self._settings.max_retries - 1:
                    await asyncio.sleep(self._settings.initial_retry_delay_s * (2**attempt))

        raise ConnectionError(f"Failed to execute Redis command '{command_name_for_logging}' after all retries.") from last_exception

    # --- Standardized Public Command Methods ---

    async def pipeline(self, transaction: bool = True) -> Pipeline:
        """
        Returns a pipeline object. Resilience is applied at pipe.execute(), not here.
        """
        client = await self._get_client()
        return client.pipeline(transaction=transaction)

    async def get(self, key: str) -> bytes | None:
        return await self.execute_resiliently(
            lambda client: client.get(key), f"GET {key}"
        )

    async def hgetall(self, name: str) -> dict[bytes, bytes]:
        return await self.execute_resiliently(
            lambda client: client.hgetall(name), f"HGETALL {name}"
        )

    async def hset(self, name: str, mapping: dict):
        return await self.execute_resiliently(
            lambda client: client.hset(name, mapping=mapping), f"HSET {name}"
        )

    async def delete(self, *names: str):
        if not names: return
        return await self.execute_resiliently(
            lambda client: client.delete(*names), f"DELETE {names}"
        )
    
    async def sadd(self, key: str, *values):
        if not values: return
        return await self.execute_resiliently(
            lambda client: client.sadd(key, *values), f"SADD {key}"
        )
        
    async def smembers(self, key: str) -> set:
        return await self.execute_resiliently(
            lambda client: client.smembers(key), f"SMEMBERS {key}"
        )

    async def exists(self, key: str) -> bool:
         return await self.execute_resiliently(
            lambda client: client.exists(key), f"EXISTS {key}"
        )

    async def xadd(self, name: str, fields: dict, maxlen: int, approximate: bool = True):
        return await self.execute_resiliently(
            lambda client: client.xadd(name, fields, maxlen=maxlen, approximate=approximate),
            f"XADD {name}"
        )

    async def ensure_consumer_group(self, stream_name: str, group_name: str):
        try:
            await self.execute_resiliently(
                lambda client: client.xgroup_create(stream_name, group_name, id="0", mkstream=True),
                "XGROUP CREATE",
            )
            log.info(f"Ensured consumer group '{group_name}' exists for stream '{stream_name}'.")
        except redis_exceptions.ResponseError as e:
            if "BUSYGROUP" in str(e):
                log.debug(f"Consumer group '{group_name}' already exists.")
            else:
                raise

    async def read_stream_messages(self, stream_name: str, group_name: str, consumer_name: str, count: int, block: int) -> list:
        async def command(client: aioredis.Redis):
            # NOGROUP error must be handled within the command passed to the resilient executor
            try:
                response = await client.xreadgroup(
                    groupname=group_name,
                    consumername=consumer_name,
                    streams={stream_name: ">"},
                    count=count,
                    block=block,
                )
                return response[0][1] if response else []
            except redis_exceptions.ResponseError as e:
                if "NOGROUP" in str(e):
                    log.warning(f"Consumer group '{group_name}' not found for stream '{stream_name}'. Recreating...")
                    await self.ensure_consumer_group(stream_name, group_name)
                    return [] # Return empty list to allow immediate retry of the read
                raise
        return await self.execute_resiliently(command, "XREADGROUP")

    async def acknowledge_message(self, stream_name: str, group_name: str, *message_ids: str):
        if not message_ids: return
        await self.execute_resiliently(
            lambda client: client.xack(stream_name, group_name, *message_ids), "XACK"
        )
    
    async def xadd_bulk(self, stream_name: str, messages: list[dict], maxlen: int):
        """[RETAINED] Adds messages in chunks using a pipeline and write semaphore."""
        if not messages: return
        
        async def command(client: aioredis.Redis):
            async with self._write_sem:
                pipe = client.pipeline()
                for msg in messages:
                    encoded_msg = {k: orjson.dumps(v) if not isinstance(v, (bytes, str, int, float)) else v for k, v in msg.items()}
                    pipe.xadd(stream_name, encoded_msg, maxlen=maxlen, approximate=True)
                await pipe.execute()

        try:
            await self.execute_resiliently(command, "XADD BULK")
        except ConnectionError as e:
            log.error(f"Final attempt for XADD BULK failed. Moving {len(messages)} messages to DLQ. Error: {e}")
            await self.xadd_to_dlq(stream_name, messages)
            raise

    async def xadd_to_dlq(self, original_stream_name: str, failed_messages: list[dict]):
        """[RETAINED] Moves failed messages to a Dead-Letter Queue."""
        dlq_stream_name = f"dlq:{original_stream_name}"
        log.warning(f"Moving {len(failed_messages)} message(s) to DLQ: {dlq_stream_name}")
        try:
            # Use a simpler, non-bulk add for DLQ to maximize chances of success
            for msg in failed_messages:
                await self.xadd(dlq_stream_name, {"payload": orjson.dumps(msg)}, maxlen=25000)
        except Exception as e:
            log.critical(f"!!! CRITICAL: FAILED TO WRITE TO DLQ '{dlq_stream_name}': {e} !!! DATA LOSS IMMINENT !!!")
