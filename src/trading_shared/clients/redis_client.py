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
from redis.asyncio.client import PubSub

# --- Local Application Imports ---
from ..config.models import RedisSettings

T = TypeVar("T")


class CustomRedisClient:
    """A resilient client wrapper for the redis-py async client."""

    def __init__(self, settings: RedisSettings):
        self._settings = settings
        self._pool: Optional[aioredis.Redis] = None
        self._circuit_open = False
        self._last_failure = 0
        self._reconnect_attempts = 0
        self._write_sem = asyncio.Semaphore(self._settings.write_concurrency_limit)
        self._lock = asyncio.Lock()
        self._pubsub_max_connections = 30  # Adjust based on needs
        self._pubsub_pool = asyncio.Queue(maxsize=self._pubsub_max_connections)
        self._pubsub_connections = []  # For cleanup on close
        self._pubsub_lock = asyncio.Lock()
        self._pubsub_last_used = {}  # Track last use time for recycling

    async def connect(self):
        """
        Ensures the connection pool is initialized. This is the standard
        public method for explicit connection setup.
        """
        await self._get_pool()

    async def __aenter__(self):
        """Allows the client to be used as an async context manager."""
        await self._get_pool()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensures the connection pool is closed on exit."""
        await self.close()

    async def _safe_close_pool(self):
        """Safely closes the current pool, ignoring errors."""
        pool_to_close = self._pool
        self._pool = None  # Immediately prevent reuse
        if pool_to_close:
            try:
                await pool_to_close.close()
            except Exception as e:
                log.warning(
                    f"A non-critical error occurred while closing stale Redis pool: {e}"
                )

    async def _get_pool(self) -> aioredis.Redis:
        async with self._lock:
            if self._pool:
                return self._pool

            if self._circuit_open:
                cooldown = min(60, 5 * (2**self._reconnect_attempts))
                if time.time() - self._last_failure < cooldown:
                    raise ConnectionError("Redis unavailable - circuit breaker open")
                self._circuit_open = False

            try:
                password_value = (
                    self._settings.password.get_secret_value()
                    if self._settings.password
                    else None
                )

                self._pool = aioredis.from_url(
                    self._settings.url,
                    password=password_value,
                    db=int(self._settings.db or 0),
                    socket_connect_timeout=self._settings.socket_connect_timeout,
                    socket_keepalive=True,
                    socket_keepalive_options={
                        socket.TCP_KEEPIDLE: 60,
                        socket.TCP_KEEPINTVL: 30,
                        socket.TCP_KEEPCNT: 5,
                    },
                    max_connections=self._settings.max_connections,
                    encoding="utf-8",
                    decode_responses=False,
                )
                await asyncio.wait_for(self._pool.ping(), timeout=3)
                self._reconnect_attempts = 0
                log.info("Redis connection established")
                return self._pool
            except (
                redis_exceptions.ConnectionError,
                redis_exceptions.TimeoutError,
                TimeoutError,
                socket.gaierror,
            ) as e:
                log.warning(f"Initial Redis connection failed: {e}")
                await self._safe_close_pool()
                self._circuit_open = True
                self._last_failure = time.time()
                self._reconnect_attempts += 1
                raise ConnectionError(
                    "Redis connection failed on initial attempt."
                ) from e

    async def close(self):
        """Gracefully closes the active Redis connection pool and all pubsub connections."""
        async with self._lock:
            # Close all pubsub connections
            for conn in self._pubsub_connections:
                try:
                    await conn.close()
                except Exception as e:
                    log.warning(f"Error closing pubsub connection: {e}")
            self._pubsub_connections.clear()

            # Recreate empty pool
            self._pubsub_pool = asyncio.Queue(maxsize=self._pubsub_max_connections)

            await self._safe_close_pool()
            log.info("Redis connection pool and pubsub connections closed.")

    async def execute_resiliently(
        self,
        func: Callable[[aioredis.Redis], Awaitable[T]],
        command_name_for_logging: str,
    ) -> T:
        """
        Executes a given Redis command function with a resilient retry mechanism.
        """
        last_exception: Exception | None = None
        max_retries = self._settings.max_retries
        initial_delay = self._settings.initial_retry_delay_s

        for attempt in range(max_retries):
            try:
                pool = await self._get_pool()
                return await func(pool)
            except (
                redis_exceptions.ConnectionError,
                redis_exceptions.TimeoutError,
                TimeoutError,
            ) as e:
                log.warning(
                    f"Redis command '{command_name_for_logging}' failed "
                    f"(attempt {attempt + 1}/{max_retries}): {e}"
                )
                last_exception = e
                await self._safe_close_pool()
                if attempt < max_retries - 1:
                    await asyncio.sleep(initial_delay * (2**attempt))

        log.error(
            f"Redis command '{command_name_for_logging}' failed after {max_retries} attempts."
        )
        raise ConnectionError(
            f"Failed to execute Redis command '{command_name_for_logging}' after retries."
        ) from last_exception

    @asynccontextmanager
    async def pubsub(self) -> PubSub:
        """
        Provides a managed PubSub object that guarantees connection cleanup.
        """
        # Try to get from pool first
        try:
            pubsub_conn = self._pubsub_pool.get_nowait()
            log.debug("Reusing pooled PubSub connection")
        except asyncio.QueueEmpty:
            # Create new connection if pool is empty
            async with self._pubsub_lock:
                # Check if we can recycle old connections first
                current_time = time.time()
                for conn in list(self._pubsub_connections):
                    last_used = self._pubsub_last_used.get(id(conn), 0)
                    if current_time - last_used > 300:  # 5 minutes idle
                        try:
                            await conn.close()
                            self._pubsub_connections.remove(conn)
                            self._pubsub_last_used.pop(id(conn), None)
                            log.debug("Recycled idle PubSub connection")
                        except:
                            pass

                # Double-check after recycling
                try:
                    pubsub_conn = self._pubsub_pool.get_nowait()
                except asyncio.QueueEmpty:
                    if len(self._pubsub_connections) < self._pubsub_max_connections:
                        pool = await self._get_pool()
                        pubsub_conn = pool.pubsub()
                        self._pubsub_connections.append(pubsub_conn)
                        self._pubsub_last_used[id(pubsub_conn)] = current_time
                        log.debug(
                            f"Created new PubSub connection (total: {len(self._pubsub_connections)})"
                        )
                    else:
                        # Wait with timeout to prevent deadlock
                        try:
                            pubsub_conn = await asyncio.wait_for(
                                self._pubsub_pool.get(), timeout=5.0
                            )
                        except asyncio.TimeoutError:
                            raise ConnectionError("No PubSub connections available")

        try:
            yield pubsub_conn
        finally:
            # Update last used time
            self._pubsub_last_used[id(pubsub_conn)] = time.time()

            # Return to pool for reuse
            try:
                self._pubsub_pool.put_nowait(pubsub_conn)
            except asyncio.QueueFull:
                # This shouldn't happen with proper maxsize
                log.warning("PubSub pool full, closing connection")
                await pubsub_conn.close()
                if pubsub_conn in self._pubsub_connections:
                    self._pubsub_connections.remove(pubsub_conn)
                self._pubsub_last_used.pop(id(pubsub_conn), None)

    @staticmethod
    def parse_stream_message(message_data: dict[bytes, bytes]) -> dict:
        result = {}
        for key, value in message_data.items():
            k = key.decode("utf-8")
            if k in ("data", "payload", "order", "trade", "kline"):
                try:
                    result[k] = orjson.loads(value)
                    continue
                except (orjson.JSONDecodeError, TypeError):
                    pass
            try:
                result[k] = orjson.loads(value)
            except (orjson.JSONDecodeError, TypeError):
                try:
                    result[k] = value.decode("utf-8")
                except UnicodeDecodeError:
                    log.warning(f"Could not decode field '{k}'. Storing raw bytes.")
                    result[k] = value
        return result

    async def xadd_bulk(
        self,
        stream_name: str,
        messages: list[dict] | deque,
        maxlen: int = 10000,
    ) -> None:
        if not messages:
            return
        CHUNK_SIZE = 500
        message_list = list(messages)
        for chunk_start in range(0, len(message_list), CHUNK_SIZE):
            chunk = message_list[chunk_start : chunk_start + CHUNK_SIZE]
            try:

                async def command(pool: aioredis.Redis, current_chunk=chunk):
                    async with self._write_sem:
                        pipe = pool.pipeline()
                        for msg in current_chunk:
                            encoded_msg = {
                                k.encode("utf-8"): (
                                    orjson.dumps(v)
                                    if isinstance(v, (dict, list, tuple))
                                    else str(v).encode("utf-8")
                                )
                                for k, v in msg.items()
                            }
                            pipe.xadd(
                                stream_name,
                                encoded_msg,
                                maxlen=maxlen,
                                approximate=True,
                            )
                        await pipe.execute()

                await self.execute_resiliently(command, "pipeline.execute(xadd)")
            # Only catch the final, definitive ConnectionError from the resilient wrapper.
            except ConnectionError as e:
                log.error(
                    f"Final attempt to send chunk failed. Moving to DLQ stream. Error: {e}"
                )
                await self.xadd_to_dlq(stream_name, chunk)
                # Re-raise to signal that the write operation ultimately failed.
                raise

    async def xadd_to_dlq(
        self,
        original_stream_name: str,
        failed_messages: list[dict],
    ):
        if not failed_messages:
            return
        dlq_stream_name = f"dlq:{original_stream_name}"
        try:

            async def command(pool: aioredis.Redis):
                pipe = pool.pipeline()
                for msg in failed_messages:
                    pipe.xadd(
                        dlq_stream_name, {"payload": orjson.dumps(msg)}, maxlen=25000
                    )
                await pipe.execute()

            await self.execute_resiliently(command, "pipeline.execute(xadd_dlq)")
            log.warning(
                f"{len(failed_messages)} message(s) moved to DLQ stream "
                f"'{dlq_stream_name}'"
            )
        except Exception as e:
            log.critical(
                f"CRITICAL: Failed to write to DLQ stream '{dlq_stream_name}': {e}"
            )

    async def ensure_consumer_group(
        self,
        stream_name: str,
        group_name: str,
    ):
        try:
            await self.execute_resiliently(
                lambda pool: pool.xgroup_create(
                    stream_name,
                    group_name,
                    id="0",
                    mkstream=True,
                ),
                "xgroup_create",
            )
            log.info(
                f"Created consumer group '{group_name}' for stream '{stream_name}'."
            )
        except redis_exceptions.ResponseError as e:
            if "BUSYGROUP" in str(e):
                log.debug(f"Consumer group '{group_name}' already exists.")
            else:
                raise

    async def read_stream_messages(
        self,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        count: int = 250,
        block: int = 2000,
    ) -> list:
        try:

            async def command(pool: aioredis.Redis):
                try:
                    response = await pool.xreadgroup(
                        groupname=group_name,
                        consumername=consumer_name,
                        streams={stream_name: ">"},
                        count=count,
                        block=block,
                    )
                    return response[0][1] if response else []
                except redis_exceptions.ResponseError as e:
                    if "NOGROUP" in str(e):
                        log.warning(
                            f"Consumer group '{group_name}' missing for "
                            f"stream '{stream_name}', recreating..."
                        )
                        await self.ensure_consumer_group(stream_name, group_name)
                        return []
                    raise

            return await self.execute_resiliently(command, "xreadgroup")
        except ConnectionError as e:
            raise ConnectionError("Redis connection failed during XREADGROUP") from e

    async def acknowledge_message(
        self,
        stream_name: str,
        group_name: str,
        *message_ids: str,
    ) -> None:
        if not message_ids:
            return
        await self.execute_resiliently(
            lambda pool: pool.xack(stream_name, group_name, *message_ids), "xack"
        )

    async def xautoclaim_stale_messages(
        self,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        min_idle_time_ms: int,
        count: int = 100,
    ) -> tuple[bytes, list]:
        try:
            return await self.execute_resiliently(
                lambda pool: pool.xautoclaim(
                    name=stream_name,
                    groupname=group_name,
                    consumername=consumer_name,
                    min_idle_time=min_idle_time_ms,
                    start_id="0-0",
                    count=count,
                ),
                "xautoclaim",
            )
        except redis_exceptions.ResponseError as e:
            log.warning(f"Could not run XAUTOCLAIM on '{stream_name}': {e}.")
            return b"0-0", []  # Return a valid, non-operational start_id
        except Exception as e:
            log.error(f"An unexpected error occurred during XAUTOCLAIM: {e}")
            raise

    async def get_system_state(self) -> str:
        try:
            state = await self.execute_resiliently(
                lambda pool: pool.get("system:state:simple"), "get"
            )
            if state:
                return state.decode()
            old_state = await self.execute_resiliently(
                lambda pool: pool.get("system:state"), "get"
            )
            return old_state.decode() if old_state else "LOCKED"
        except ConnectionError:
            log.warning(
                "Could not get system state due to Redis connection error. "
                "Defaulting to LOCKED."
            )
            return "LOCKED"

    async def set_system_state(
        self,
        state: str,
        reason: str | None = None,
    ):
        try:

            async def command(pool: aioredis.Redis):
                state_data = {
                    "status": state,
                    "reason": reason or "",
                    "timestamp": time.time(),
                }
                await pool.hset("system:state", mapping=state_data)
                await pool.set("system:state:simple", state)

            await self.execute_resiliently(command, "hset/set")
            log_message = f"System state transitioned to: {state.upper()}"
            if reason:
                log_message += f" (Reason: {reason})"
            log.info(log_message)
        except ConnectionError:
            log.error(
                f"Could not set system state to '{state}' due to Redis connection error."
            )

    async def get(self, key: str) -> bytes | None:
        async def command(conn: aioredis.Redis) -> bytes | None:
            return await conn.get(key)

        return await self.execute_resiliently(command, f"GET {key}")

    async def publish(self, channel: str, message: str | bytes):
        """Publishes a message to a channel."""

        async def command(conn: aioredis.Redis):
            return await conn.publish(channel, message)

        await self.execute_resiliently(command, f"PUBLISH {channel}")

    async def set(self, key: str, value: str, ex: int | None = None):
        async def command(conn: aioredis.Redis):
            await conn.set(key, value, ex=ex)

        await self.execute_resiliently(command, f"SET {key}")

    async def hget(self, name: str, key: str) -> Optional[bytes]:
        async def command(conn: aioredis.Redis):
            return await conn.hget(name, key)

        return await self.execute_resiliently(command, f"HGET {name}")

    async def hset(self, name: str, key: str, value: Any):
        async def command(conn: aioredis.Redis):
            await conn.hset(name, key, value)

        await self.execute_resiliently(command, f"HSET {name}")

    async def xadd(
        self,
        name: str,
        fields: dict,
        maxlen: int | None = None,
        approximate: bool = True,
    ):
        encoded_fields = {
            k.encode("utf-8") if isinstance(k, str) else k: v.encode("utf-8")
            if isinstance(v, str)
            else v
            for k, v in fields.items()
        }

        async def command(conn: aioredis.Redis):
            await conn.xadd(
                name, encoded_fields, maxlen=maxlen, approximate=approximate
            )

        await self.execute_resiliently(command, f"XADD {name}")

    async def lpush(self, key: str, value: str | bytes):
        return await self.execute_resiliently(
            lambda pool: pool.lpush(key, value), f"LPUSH {key}"
        )

    async def brpop(self, key: str, timeout: int) -> tuple[bytes, bytes] | None:
        return await self.execute_resiliently(
            lambda pool: pool.brpop(key, timeout=timeout), f"BRPOP {key}"
        )

    async def delete(self, key: str):
        """Deletes a key from Redis."""
        return await self.execute_resiliently(
            lambda pool: pool.delete(key), f"DELETE {key}"
        )

    async def llen(self, key: str) -> int:
        """Returns the length of a list in Redis."""
        return await self.execute_resiliently(
            lambda pool: pool.llen(key), f"LLEN {key}"
        )
