
# src/trading_shared/clients/postgres_client.py

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import asyncpg
import orjson
from loguru import logger as log

from ..config.models import PostgresSettings

T = TypeVar("T")


class PostgresClient:
    """
    A resilient, instance-safe, and generic client for PostgreSQL.
    It manages a connection pool and provides generic execution methods.
    It has no knowledge of the application's domain or schema.
    """

    def __init__(self, settings: PostgresSettings):
        self.postgres_settings = settings
        self.dsn = self.postgres_settings.dsn
        self._pool: asyncpg.Pool | None = None
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        await self.ensure_pool_is_ready()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def execute_resiliently(
        self,
        command_func: Callable[[asyncpg.Connection], Awaitable[T]],
        command_name_for_logging: str,
    ) -> T:
        last_exception: Exception | None = None
        max_retries = self.postgres_settings.max_retries
        initial_delay = self.postgres_settings.initial_retry_delay_s

        for attempt in range(max_retries):
            try:
                pool = await self.ensure_pool_is_ready()
                async with pool.acquire() as conn:
                    return await command_func(conn)
            except (
                asyncpg.PostgresConnectionError,
                asyncpg.InterfaceError,
                TimeoutError,
            ) as e:
                log.warning(f"Postgres command '{command_name_for_logging}' failed (attempt {attempt + 1}/{max_retries}): {e}")
                last_exception = e
                await self.close()
                if attempt < max_retries - 1:
                    await asyncio.sleep(initial_delay * (2**attempt))

        log.error(f"Postgres command '{command_name_for_logging}' failed after {max_retries} attempts.")
        raise ConnectionError(f"Failed to execute Postgres command '{command_name_for_logging}' after retries.") from last_exception

    async def ensure_pool_is_ready(self) -> asyncpg.Pool:
        async with self._lock:
            if self._pool is not None and not self._pool._closed:
                return self._pool
            log.info("PostgreSQL connection pool is not available. Creating new pool.")
            try:
                self._pool = await asyncpg.create_pool(
                    dsn=self.dsn,
                    min_size=self.postgres_settings.pool_min_size,
                    max_size=self.postgres_settings.pool_max_size,
                    command_timeout=self.postgres_settings.command_timeout,
                    init=self._setup_codecs,
                )
                log.info("PostgreSQL pool created successfully.")
                return self._pool
            except Exception as e:
                self._pool = None
                raise ConnectionError("Fatal: Could not create PostgreSQL pool.") from e

    async def _setup_codecs(self, connection: asyncpg.Connection):
        """
        [CORRECTED] This function is now syntactically correct and fail-fast.
        It properly registers all required application types.
        """
        log.info("Registering custom PostgreSQL type codecs for new connection.")
        try:
            # 1. JSON/JSONB Codec (Requires encoder/decoder)
            for json_type in ["jsonb", "json"]:
                await connection.set_type_codec(
                    json_type,
                    encoder=lambda d: orjson.dumps(d).decode("utf-8"),
                    decoder=orjson.loads,
                    schema="pg_catalog",
                )

            # 2. Custom Composite Types (Requires format='tuple')
            await connection.set_type_codec(
                "public_trade_insert_type", 
                schema="public", 
                format="tuple"
            )
            # This may fail if the type doesn't exist, which is acceptable for services
            # that don't use it. We can add optional registration later if needed.
            # For now, keeping it explicit.
            await connection.set_type_codec(
                "option_trade_insert_type", 
                schema="public", 
                format="tuple"
            )
            await connection.set_type_codec(
                "ohlc_upsert_type", 
                schema="public", 
                format="tuple"
            )
            log.success("All custom type codecs registered successfully.")
            
        except Exception as e:
            log.critical(
                f"Failed to register a mandatory type codec. This is a fatal error. "
                f"Ensure the database schema is up to date. Error: {e}"
            )
            raise

    async def close(self):
        async with self._lock:
            if self._pool:
                await self._pool.close()
                log.info("PostgreSQL connection pool closed.")
                self._pool = None

    async def execute(self, query: str, *args: Any) -> int:
        command_name = query.strip().split()[0].upper()

        async def command(conn: asyncpg.Connection) -> int:
            result_str = await conn.execute(query, *args)
            try:
                return int(result_str.split(" ")[-1])
            except (ValueError, IndexError):
                return 0

        return await self.execute_resiliently(command, command_name)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        command_name = query.strip().split()[0].upper()
        return await self.execute_resiliently(lambda conn: conn.fetch(query, *args), f"fetch_{command_name}")

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        command_name = query.strip().split()[0].upper()
        return await self.execute_resiliently(lambda conn: conn.fetchrow(query, *args), f"fetchrow_{command_name}")

    async def fetchval(self, query: str, *args: Any) -> Any:
        command_name = query.strip().split()[0].upper()
        return await self.execute_resiliently(lambda conn: conn.fetchval(query, *args), f"fetchval_{command_name}")