# src/trading_shared/clients/redis_client.py

# --- Built Ins  ---
import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

# --- Installed  ---
import orjson
import redis.asyncio as aioredis
from loguru import logger as log
from redis import exceptions as redis_exceptions
from redis.asyncio.client import Pipeline, PubSub

# --- Local Application Imports ---
from ..config.models import RedisSettings

T = TypeVar("T")


class CustomRedisClient:
    """A resilient client wrapper for the redis-py async client."""

    def __init__(self, settings: RedisSettings):
        self._settings = settings
        self._client: aioredis.Redis | None = None
        self._circuit_open = False
        self._last_failure = 0
        self._reconnect_attempts = 0
        self._write_sem = asyncio.Semaphore(self._settings.write_concurrency_limit)
        self._lock = asyncio.Lock()
        self._pubsub_max_connections = self._settings.pubsub_max_connections
        self._pubsub_pool = asyncio.Queue(maxsize=self._pubsub_max_connections)
        self._pubsub_connections = []  # For cleanup on close
        self._pubsub_lock = asyncio.Lock()
        self._pubsub_last_used = {}  # Track last use time for recycling

    async def connect(self):
        await self._get_client()

    async def __aenter__(self):
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensures the connection pool is closed on exit."""
        await self.close()

    async def _get_client(self) -> aioredis.Redis:
        """
        Returns a single, managed Redis client instance.
        Implements a circuit breaker to prevent hammering a down server.
        """
        async with self._lock:
            if self._client:
                return self._client

            if self._circuit_open:
                cooldown = min(60, 5 * (2**self._reconnect_attempts))
                if time.time() - self._last_failure < cooldown:
                    raise ConnectionError("Redis unavailable - circuit breaker open")
                self._circuit_open = False

            try:
                password_value = self._settings.password.get_secret_value() if self._settings.password else None
                redis_url_as_string = str(self._settings.url)

                self._client = aioredis.from_url(
                    redis_url_as_string,
                    password=password_value,
                    db=int(self._settings.db or 0),
                    socket_connect_timeout=self._settings.socket_connect_timeout,
                    decode_responses=False,  # Must be false for orjson
                )
                await asyncio.wait_for(self._client.ping(), timeout=10)
                self._reconnect_attempts = 0
                log.info("Redis connection established")
                return self._client
            except Exception as e:
                log.warning(f"Initial Redis connection failed: {e}")
                await self._safe_close_client()
                self._circuit_open = True
                self._last_failure = time.time()
                self._reconnect_attempts += 1
                raise ConnectionError("Redis connection failed on initial attempt.") from e

    async def _safe_close_client(self):
        """Safely closes the current client instance, ignoring errors."""
        client_to_close = self._client
        self._client = None
        if client_to_close:
            try:
                await client_to_close.close()
            except Exception as e:
                log.warning(f"Non-critical error while closing stale Redis client: {e}")

    async def close(self):
        async with self._lock:
            await self._safe_close_client()
            log.info("Redis client connection closed.")

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
                client = await self._get_client()
                # Check if pool is None before using it
                if client is None:
                    raise ConnectionError("Redis pool is None - connection not established")
                return await func(client)
            except AttributeError as e:
                # Catch AttributeError when pool methods fail
                log.warning(f"Redis command '{command_name_for_logging}' failed due to AttributeError (attempt {attempt + 1}/{max_retries}): {e}")
                last_exception = e
                await self._safe_close_client()
                if attempt < max_retries - 1:
                    await asyncio.sleep(initial_delay * (2**attempt))
            except (
                redis_exceptions.ConnectionError,
                redis_exceptions.TimeoutError,
                TimeoutError,
                ConnectionError,  # Catch our own ConnectionError
            ) as e:
                log.warning(f"Redis command '{command_name_for_logging}' failed (attempt {attempt + 1}/{max_retries}): {e}")
                last_exception = e
                await self._safe_close_client()
                if attempt < max_retries - 1:
                    await asyncio.sleep(initial_delay * (2**attempt))

        log.error(f"Redis command '{command_name_for_logging}' failed after {max_retries} attempts.")
        raise ConnectionError(f"Failed to execute Redis command '{command_name_for_logging}' after retries.") from last_exception

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
                        except Exception:
                            pass

                # Double-check after recycling
                try:
                    pubsub_conn = self._pubsub_pool.get_nowait()
                except asyncio.QueueEmpty:
                    if len(self._pubsub_connections) < self._pubsub_max_connections:
                        client = await self._get_client()
                        pubsub_conn = client.pubsub()
                        self._pubsub_connections.append(pubsub_conn)
                        self._pubsub_last_used[id(pubsub_conn)] = current_time
                        log.debug(f"Created new PubSub connection (total: {len(self._pubsub_connections)})")
                    else:
                        # Wait with timeout to prevent deadlock
                        try:
                            pubsub_conn = await asyncio.wait_for(self._pubsub_pool.get(), timeout=5.0)
                        except asyncio.TimeoutError as e:
                            raise ConnectionError("No PubSub connections available") from e
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
                                k.encode("utf-8"): (orjson.dumps(v) if isinstance(v, (dict, list, tuple)) else str(v).encode("utf-8"))
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
                log.error(f"Final attempt to send chunk failed. Moving to DLQ stream. Error: {e}")
                await self.xadd_to_dlq(stream_name, chunk)
                # Re-raise to signal that the write operation ultimately failed.
                raise

    async def xadd_to_dlq(
        self,
        original_stream_name: str,
        failed_messages: list[dict],
    ):
        """
        Moves failed messages to a dead-letter queue with a name derived from the
        original stream, compliant with DATA_CONTRACTS.md v2.0.
        """
        if not failed_messages:
            return

        # Correctly construct the DLQ name, e.g., 'market:stream:...' -> 'deadletter:queue:market:stream'
        parts = original_stream_name.split(":", 2)
        if len(parts) >= 2:
            domain, type_ = parts[0], parts[1]
            dlq_stream_name = f"deadletter:queue:{domain}:{type_}"
        else:
            log.error(f"Could not parse domain/type from '{original_stream_name}'. Using fallback DLQ.")
            dlq_stream_name = f"deadletter:queue:malformed:{original_stream_name}"

        try:

            async def command(pool: aioredis.Redis):
                pipe = pool.pipeline()
                for msg in failed_messages:
                    pipe.xadd(dlq_stream_name, {"payload": orjson.dumps(msg)}, maxlen=25000)
                await pipe.execute()

            await self.execute_resiliently(command, f"pipeline.execute(xadd_dlq to {dlq_stream_name})")
            log.warning(f"{len(failed_messages)} message(s) moved to DLQ stream '{dlq_stream_name}' from '{original_stream_name}'")
        except Exception as e:
            log.critical(f"CRITICAL: Failed to write to DLQ stream '{dlq_stream_name}': {e}")

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
            log.info(f"Created consumer group '{group_name}' for stream '{stream_name}'.")
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
        block: int = 5000,
    ) -> list:
        try:

            async def command(pool: aioredis.Redis) -> list:
                try:
                    # The response is a list containing one stream's data, or empty on timeout.
                    # e.g., [[b'stream_name', [(b'id', {...}), ...]]]
                    response = await pool.xreadgroup(
                        groupname=group_name,
                        consumername=consumer_name,
                        streams={stream_name: ">"},  # ">" means new messages only
                        count=count,
                        block=block,
                    )

                    if not response:
                        return []  # This is a normal timeout, no new messages.

                    # Explicitly find our stream in the response for safety
                    for stream_data in response:
                        if stream_data[0].decode() == stream_name:
                            return stream_data[1]  # Return the list of messages

                    return []  # Should not be reached if polling one stream, but safe.

                except redis_exceptions.ResponseError as e:
                    if "NOGROUP" in str(e):
                        log.warning(f"Consumer group '{group_name}' not found for stream '{stream_name}', recreating...")
                        # This should be handled by ensure_consumer_group before calling,
                        # but this is a safe fallback.
                        await pool.xgroup_create(stream_name, group_name, id="0", mkstream=True)
                        return []
                    raise

            return await self.execute_resiliently(command, f"XREADGROUP on {stream_name}")
        except ConnectionError:
            log.error(f"Redis connection lost while reading stream '{stream_name}'.")
            raise  # Re-raise to allow the calling loop to handle reconnection pauses.

    async def read_grouped_streams(
        self,
        group_name: str,
        consumer_name: str,
        streams: dict[str, str],
        count: int = 10,
        block: int = 2000,
    ) -> list:
        """
        Reads messages from multiple streams using XREADGROUP.
        Input 'streams' is a dict of {stream_name: message_id}.
        """
        try:

            async def command(pool: aioredis.Redis) -> list:
                try:
                    response = await pool.xreadgroup(
                        groupname=group_name,
                        consumername=consumer_name,
                        streams=streams,
                        count=count,
                        block=block,
                    )
                    return response if response else []
                except redis_exceptions.ResponseError as e:
                    if "NOGROUP" in str(e):
                        log.warning(f"Consumer group '{group_name}' missing on some streams. Initializing...")
                        for s_name in streams.keys():
                            try:
                                await pool.xgroup_create(s_name, group_name, id="0", mkstream=True)
                            except redis_exceptions.ResponseError as re:
                                if "BUSYGROUP" not in str(re):
                                    raise
                        return []
                    raise

            return await self.execute_resiliently(command, f"XREADGROUP on {list(streams.keys())}")
        except ConnectionError:
            raise

    async def acknowledge_message(
        self,
        stream_name: str,
        group_name: str,
        *message_ids: str,
    ) -> None:
        if not message_ids:
            return
        await self.execute_resiliently(lambda pool: pool.xack(stream_name, group_name, *message_ids), "xack")

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
        """
        DEPRECATED: This method accesses obsolete keys and violates the centralized
        state management protocol defined in DATA_CONTRACTS.md v2.0.

        ARCHITECTURAL MANDATE: Services must receive a state manager repository via
        dependency injection. Direct state access via this client is forbidden.
        """
        raise NotImplementedError(
            "get_system_state is deprecated. Use a dedicated SystemStateManager to ensure compliance with the hierarchical state protocol."
        )

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
            log.error(f"Could not set system state to '{state}' due to Redis connection error.")

    async def get_client_deprecated(self) -> aioredis.Redis:
        """Returns a client instance from the connection pool."""
        pool = await self._get_client()
        return aioredis.Redis(connection_pool=pool)

    async def pipeline(self, transaction: bool = True) -> Pipeline:
        """
        Returns a pipeline object from the underlying client, allowing for atomic transactions.
        """
        client = await self._get_client()
        return client.pipeline(transaction=transaction)

    async def get(self, key: str) -> bytes | None:
        async def command(conn: aioredis.Redis) -> bytes | None:
            return await conn.get(key)

        return await self.execute_resiliently(command, f"GET {key}")

    async def publish(
        self,
        channel: str,
        message: str | bytes,
    ):
        """Publishes a message to a channel."""

        async def command(conn: aioredis.Redis):
            return await conn.publish(channel, message)

        await self.execute_resiliently(command, f"PUBLISH {channel}")

    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
    ):
        async def command(conn: aioredis.Redis):
            await conn.set(key, value, ex=ex)

        await self.execute_resiliently(command, f"SET {key}")

    async def hget(
        self,
        name: str,
        key: str,
    ) -> bytes | None:
        async def command(conn: aioredis.Redis):
            return await conn.hget(name, key)

        return await self.execute_resiliently(command, f"HGET {name}")

    async def hgetall(
        self,
        name: str,
    ) -> dict[bytes, bytes]:
        """Returns all fields and values of the hash stored at key."""

        async def command(conn: aioredis.Redis):
            return await conn.hgetall(name)

        return await self.execute_resiliently(command, f"HGETALL {name}")

    async def hset(
        self,
        name: str,
        key: str | None = None,
        value: Any = None,
        mapping: dict | None = None,
    ):
        """
        Sets a field in a hash. Supports either a single key/value pair
        or a mapping of multiple key/value pairs.
        """
        if mapping is not None:

            async def command(conn: aioredis.Redis):
                await conn.hset(name, mapping=mapping)

            await self.execute_resiliently(command, f"HSET {name} [MAPPING]")
        elif key is not None:

            async def command(conn: aioredis.Redis):
                await conn.hset(name, key, value)

            await self.execute_resiliently(command, f"HSET {name}")
        else:
            raise ValueError("hset requires either a key/value pair or a mapping.")

    async def incr(self, key: str) -> int:
        """
        Increments the number stored at key by one.
        If the key does not exist, it is set to 0 before performing the operation.
        Returns the new value.
        """

        async def command(conn: aioredis.Redis):
            return await conn.incr(key)

        return await self.execute_resiliently(command, f"INCR {key}")

    async def expire(
        self,
        name: str,
        time: int,
    ):
        """
        Sets a timeout on a key.
        """

        async def command(conn: aioredis.Redis):
            return await conn.expire(name, time)

        await self.execute_resiliently(command, f"EXPIRE {name}")

    async def xadd(
        self,
        name: str,
        fields: dict,
        maxlen: int | None = None,
        approximate: bool = True,
    ):
        encoded_fields = {k.encode("utf-8") if isinstance(k, str) else k: v.encode("utf-8") if isinstance(v, str) else v for k, v in fields.items()}

        async def command(conn: aioredis.Redis):
            await conn.xadd(name, encoded_fields, maxlen=maxlen, approximate=approximate)

        await self.execute_resiliently(command, f"XADD {name}")

    async def lpush(self, key: str, value: str | bytes):
        return await self.execute_resiliently(lambda pool: pool.lpush(key, value), f"LPUSH {key}")

    async def brpop(self, key: str, timeout: int) -> tuple[bytes, bytes] | None:
        return await self.execute_resiliently(lambda pool: pool.brpop(key, timeout=timeout), f"BRPOP {key}")

    async def delete(self, key: str):
        """Deletes a key from Redis."""
        return await self.execute_resiliently(lambda pool: pool.delete(key), f"DELETE {key}")

    async def llen(self, key: str) -> int:
        """Returns the length of a list in Redis."""
        return await self.execute_resiliently(lambda pool: pool.llen(key), f"LLEN {key}")

    async def ping(self) -> bool:
        """
        Pings the Redis server to test connectivity.
        Returns True if successful, raises ConnectionError on failure.
        """
        try:
            client = await self._get_client()
            result = await client.ping()
            return result == b"PONG" or result is True
        except Exception as e:
            log.warning(f"Redis ping failed: {e}")
            raise ConnectionError(f"Redis ping failed: {e}") from e

    async def test_connection(self) -> bool:
        """
        Tests if the Redis connection is working.
        Returns True if successful, False otherwise.
        """
        try:
            await self.ping()
            return True
        except Exception:
            return False

    def is_connected(self) -> bool:
        """Returns True if the client has an active connection pool."""
        return self._client is not None and not self._circuit_open

    async def reconnect(self) -> bool:
        """

        Forces a reconnection to Redis.
        Returns True if reconnection succeeded, False otherwise.
        """
        async with self._lock:
            log.info("Attempting to force reconnect to Redis...")

            # Close existing pool if any
            await self._safe_close_client()

            # Reset circuit breaker
            self._circuit_open = False
            self._last_failure = 0

            try:
                # Try to get a new pool
                await self._get_client()
                log.info("Redis reconnection successful")
                return True
            except ConnectionError as e:
                log.error(f"Redis reconnection failed: {e}")
                return False

    async def sadd(self, key: str, *values):
        if not values:
            return
        return await self.execute_resiliently(lambda client: client.sadd(key, *values), f"SADD {key}")

    async def smembers(self, key: str) -> set:
        return await self.execute_resiliently(lambda client: client.smembers(key), f"SMEMBERS {key}")
