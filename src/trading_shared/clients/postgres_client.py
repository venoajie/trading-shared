# src/trading_shared/clients/postgres_client.py

# --- Built Ins  ---
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, List, Optional, TypeVar

# --- Installed  ---
import asyncpg
from loguru import logger as log
import orjson

# --- Local Application Imports ---
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
        self._pool: Optional[asyncpg.Pool] = None
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
                log.warning(
                    f"Postgres command '{command_name_for_logging}' failed "
                    f"(attempt {attempt + 1}/{max_retries}): {e}"
                )
                last_exception = e
                await self.close()
                if attempt < max_retries - 1:
                    await asyncio.sleep(initial_delay * (2**attempt))

        log.error(
            f"Postgres command '{command_name_for_logging}' failed after {max_retries} attempts."
        )
        raise ConnectionError(
            f"Failed to execute Postgres command '{command_name_for_logging}' after retries."
        ) from last_exception

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
        # 1. JSON Codec
        for json_type in ["jsonb", "json"]:
            await connection.set_type_codec(
                json_type,
                encoder=lambda d: orjson.dumps(d).decode("utf-8"),
                decoder=orjson.loads,
                schema="pg_catalog",
            )
            
        # 2. Custom Composite Types.
        # We must register the type so asyncpg can map the Python tuple to the DB type
        try:
            await connection.set_type_codec(
                'public_trade_insert_type',
                schema='public',
                format='tuple' # Tells asyncpg to treat Python tuples as this composite type
            )
            # Also register for OHLC upserts if needed
            await connection.set_type_codec(
                'ohlc_upsert_type',
                schema='public',
                format='tuple'
            )
        except Exception:
            # Type might not exist in some environments (e.g. during migrations), ignore safely
            pass
            
    async def close(self):
        async with self._lock:
            if self._pool:
                await self._pool.close()
                log.info("PostgreSQL connection pool closed.")
                self._pool = None

    async def _setup_json_codec(self, connection: asyncpg.Connection):
        for json_type in ["jsonb", "json"]:
            await connection.set_type_codec(
                json_type,
                encoder=lambda d: orjson.dumps(d).decode("utf-8"),
                decoder=orjson.loads,
                schema="pg_catalog",
            )

    async def execute(self, query: str, *args: Any) -> int:
        command_name = query.strip().split()[0].upper()

        async def command(conn: asyncpg.Connection) -> int:
            result_str = await conn.execute(query, *args)
            try:
                return int(result_str.split(" ")[-1])
            except (ValueError, IndexError):
                return 0

        return await self.execute_resiliently(command, command_name)

    async def fetch(self, query: str, *args: Any) -> List[asyncpg.Record]:
        command_name = query.strip().split()[0].upper()
        return await self.execute_resiliently(
            lambda conn: conn.fetch(query, *args), f"fetch_{command_name}"
        )

    async def fetchrow(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        command_name = query.strip().split()[0].upper()
        return await self.execute_resiliently(
            lambda conn: conn.fetchrow(query, *args), f"fetchrow_{command_name}"
        )

    async def fetchval(self, query: str, *args: Any) -> Any:
        command_name = query.strip().split()[0].upper()
        return await self.execute_resiliently(
            lambda conn: conn.fetchval(query, *args), f"fetchval_{command_name}"
        )
