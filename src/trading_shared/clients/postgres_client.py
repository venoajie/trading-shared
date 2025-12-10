# src\trading_shared\clients\postgres_client.py

# --- Installed  ---
import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, TypeVar, Optional

# --- Installed  ---
import asyncpg
from loguru import logger as log
import orjson

# --- Local Application Imports ---
from ..config.models import PostgresSettings

# Type variable for the resilient executor's return type
T = TypeVar("T")


class PostgresClient:
    """A resilient client for interacting with PostgreSQL via asyncpg."""

    _pool: asyncpg.Pool | None = None

    def __init__(self, settings: PostgresSettings | None = None):
        self.postgres_settings = settings
        self.dsn = self.postgres_settings.dsn if self.postgres_settings else None
        self._lock = asyncio.Lock()  # Instance-scoped lock

    async def __aenter__(self):
        """Allows the client to be used as an async context manager."""
        await self.ensure_pool_is_ready()  # Ensure connection is established on entry
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensures the connection pool is closed on exit."""
        await self.close()

    async def _execute_resiliently(
        self,
        command_func: Callable[[asyncpg.Connection], Awaitable[T]],
        command_name_for_logging: str,
    ) -> T:
        """
        Executes a PostgreSQL command with a retry mechanism for connection errors.
        """
        if not self.postgres_settings:
            raise ValueError(
                "Postgres settings not configured for resilient execution."
            )

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
            # If pool exists, return it. acquire() will handle broken connections.
            if self._pool is not None:
                return self._pool

            if not self.dsn or not self.postgres_settings:
                raise ValueError(
                    "Cannot start PostgreSQL pool: No configuration found."
                )

            log.info("PostgreSQL connection pool is not available. Creating new pool.")

            try:
                # Aligned pool size with best practices for PgBouncer.
                self._pool = await asyncpg.create_pool(
                    dsn=self.dsn,
                    min_size=self.postgres_settings.pool_min_size,
                    max_size=self.postgres_settings.pool_max_size,
                    command_timeout=self.postgres_settings.command_timeout,
                    init=self._setup_json_codec,
                    #!This parameter is unsupported by PgBouncer in transaction pooling mode
                    # server_settings={"application_name": "trading-system-db-client"},
                )
                log.info("PostgreSQL pool created successfully.")
                return self._pool
            except Exception as e:
                raise ConnectionError("Fatal: Could not create PostgreSQL pool.") from e

    async def close_pool(self):
        """Closes all connections in the pool."""
        if self._pool:
            await self._pool.close()
            log.info("PostgreSQL connection pool closed.")
            self._pool = None

    async def close(self):
        """
        Standardized alias for close_pool() to conform to the
        resource manager's expected interface.
        """
        await self.close_pool()

    async def _setup_json_codec(
        self,
        connection: asyncpg.Connection,
    ):
        for json_type in ["jsonb", "json"]:
            await connection.set_type_codec(
                json_type,
                encoder=lambda d: orjson.dumps(d).decode("utf-8"),
                decoder=orjson.loads,
                schema="pg_catalog",
            )

    # --- START OF PUBLIC API METHODS ---

    async def execute(
        self,
        query: str,
        *args: Any,
    ) -> int:
        """
        Public: Executes a command that does not return rows (e.g., INSERT, UPDATE, DELETE).
        Returns the number of rows affected.
        """
        command_name = query.strip().split()[0].upper()
        log.debug(f"Executing command: {command_name}")

        async def command(conn: asyncpg.Connection) -> int:
            result_str = await conn.execute(query, *args)
            try:
                # Handles formats like "DELETE 5", "INSERT 0 1"
                return int(result_str.split(" ")[-1])
            except (ValueError, IndexError):
                return 0

        return await self._execute_resiliently(command, command_name)

    async def fetch(
        self,
        query: str,
        *args: Any,
    ) -> List[asyncpg.Record]:
        """Public: Fetches multiple rows from the database."""
        command_name = query.strip().split()[0].upper()
        return await self._execute_resiliently(
            lambda conn: conn.fetch(query, *args), f"fetch_{command_name}"
        )

    async def fetchrow(
        self,
        query: str,
        *args: Any,
    ) -> Optional[asyncpg.Record]:
        """Public: Fetches a single row from the database."""
        command_name = query.strip().split()[0].upper()
        return await self._execute_resiliently(
            lambda conn: conn.fetchrow(query, *args), f"fetchrow_{command_name}"
        )

    async def fetchval(
        self,
        query: str,
        *args: Any,
    ) -> Any:
        """Public: Fetches a single scalar value from the database."""
        command_name = query.strip().split()[0].upper()
        return await self._execute_resiliently(
            lambda conn: conn.fetchval(query, *args), f"fetchval_{command_name}"
        )

    async def bulk_upsert_instruments(
        self,
        instruments: List[Dict[str, Any]],
        exchange_name: str,
    ):
        """
        Performs a bulk upsert of instrument data by passing an array of JSONB
        objects to the legacy database function.
        """
        if not instruments:
            return

        # Create a new list to avoid side effects.
        instruments_with_exchange = [
            {**inst, "exchange": exchange_name} for inst in instruments
        ]

        async def command(conn: asyncpg.Connection):
            # The 'instruments' list of dicts is automatically encoded to JSONB[].
            await conn.execute(
                "SELECT bulk_upsert_instruments($1::jsonb[])",
                instruments_with_exchange,
            )

        await self._execute_resiliently(command, "bulk_upsert_instruments")
        log.info(
            f"Successfully bulk-upserted {len(instruments)} instruments for '{exchange_name}'."
        )

    async def bulk_upsert_ohlc(
        self,
        candles: list[dict[str, Any]],
    ):
        if not candles:
            return
        records = [self._prepare_ohlc_record(c) for c in candles]

        async def command(conn: asyncpg.Connection):
            await conn.execute(
                "SELECT bulk_upsert_ohlc($1::ohlc_upsert_type[])", records
            )

        await self._execute_resiliently(command, "bulk_upsert_ohlc")

    async def fetch_all_instruments(self) -> list[asyncpg.Record]:
        async def command(conn: asyncpg.Connection):
            return await conn.fetch("SELECT * FROM v_instruments")

        return await self._execute_resiliently(command, "fetch_all_instruments")

    async def fetch_instruments_by_exchange(
        self,
        exchange_name: str,
    ) -> list[asyncpg.Record]:
        """Fetches all instrument definitions for a specific exchange."""
        query = "SELECT * FROM v_instruments WHERE exchange = $1"
        return await self.fetch(query, exchange_name)

    async def fetch_active_trades(
        self,
        user_id: str | None = None,
    ) -> list[asyncpg.Record]:
        async def command(conn: asyncpg.Connection):
            query = "SELECT * FROM v_active_trades"
            params = [user_id] if user_id else []
            if user_id:
                query += " WHERE user_id = $1"
            return await conn.fetch(query, *params)

        return await self._execute_resiliently(command, "fetch_active_trades")

    async def fetch_open_orders(
        self, user_id: str | None = None
    ) -> list[asyncpg.Record]:
        async def command(conn: asyncpg.Connection):
            query = "SELECT * FROM orders WHERE trade_id IS NULL"
            params = [user_id] if user_id else []
            if user_id:
                query += " AND user_id = $1"
            query += " ORDER BY exchange_timestamp"
            return await conn.fetch(query, *params)

        return await self._execute_resiliently(command, "fetch_open_orders")

    async def check_bootstrap_status(self, exchange_name: str) -> bool:
        async def command(conn: asyncpg.Connection):
            key = f"bootstrap_status:{exchange_name}"
            query = "SELECT value FROM system_metadata WHERE key = $1"
            result = await conn.fetchval(query, key)
            return result == "complete"

        return await self._execute_resiliently(command, "check_bootstrap_status")

    async def set_bootstrap_status(self, is_complete: bool, exchange_name: str):
        async def command(conn: asyncpg.Connection):
            key = f"bootstrap_status:{exchange_name}"
            query = """
                INSERT INTO system_metadata (key, value) VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
            """
            status = "complete" if is_complete else "incomplete"
            await conn.execute(query, key, status)

        await self._execute_resiliently(command, "set_bootstrap_status")
        log.info(
            f"Set bootstrap_status:{exchange_name} to '{'complete' if is_complete else 'incomplete'}' in database."
        )

    def _parse_resolution_to_timedelta(
        self,
        resolution: str,
    ) -> timedelta:
        """
        Parses a resolution string (e.g., '1', '60', '1D', '5 minutes', '1 hour') into a timedelta object..
        """
        parts = resolution.split()

        if len(parts) == 2:
            value = int(parts[0])
            unit = parts[1].lower()
            if "minute" in unit:
                return timedelta(minutes=value)
            if "hour" in unit:
                return timedelta(hours=value)
            if "day" in unit:
                return timedelta(days=value)
            if "week" in unit:
                return timedelta(weeks=value)
            if "second" in unit:
                return timedelta(seconds=value)

        try:
            if resolution.upper().endswith("D"):
                return timedelta(days=int(resolution[:-1]))
            if resolution.upper().endswith("W"):
                return timedelta(weeks=int(resolution[:-1]))
            if resolution.upper().endswith("H"):
                return timedelta(hours=int(resolution[:-1]))
            return timedelta(minutes=int(resolution))
        except ValueError as e:
            raise ValueError(f"Unknown resolution format: {resolution}") from e

    async def fetch_latest_ohlc_timestamp(
        self,
        exchange_name: str,
        instrument_name: str,
        resolution_td: timedelta,
    ) -> Optional[datetime]:
        """
        Fetches the most recent timestamp for a given instrument's OHLC data
        at a specific resolution.
        """
        query = """
            SELECT MAX(tick) AS latest_tick FROM ohlc
            WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3
        """

        # This uses the generic, resilient fetchrow method already in the class
        result = await self.fetchrow(
            query, exchange_name, instrument_name, resolution_td
        )

        if result and result["latest_tick"]:
            return result["latest_tick"]
        return None

    def _prepare_ohlc_record(
        self,
        candle_data: dict[str, Any],
    ) -> tuple:
        tick_dt = datetime.fromtimestamp(candle_data["tick"] / 1000, tz=UTC)
        resolution_str = candle_data["resolution"]
        resolution_td = self._parse_resolution_to_timedelta(resolution_str)

        return (
            candle_data["exchange"],
            candle_data["instrument_name"],
            resolution_td,
            tick_dt,
            candle_data["open"],
            candle_data["high"],
            candle_data["low"],
            candle_data["close"],
            candle_data["volume"],
            candle_data.get("open_interest"),
        )

    async def bulk_upsert_tickers(
        self,
        tickers_data: list[dict[str, Any]],
    ):
        if not tickers_data:
            return

        records_to_upsert = []
        for ticker in tickers_data:
            ts_ms = ticker.get("exchange_timestamp")
            if not ts_ms:
                log.warning(
                    f"Ticker data for {ticker.get('instrument_name')} is missing 'exchange_timestamp'. Skipping."
                )
                continue

            ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
            records_to_upsert.append(
                (
                    ticker.get("instrument_name"),
                    ticker.get("last_price"),
                    ticker.get("mark_price"),
                    ticker.get("index_price"),
                    ticker.get("open_interest"),
                    ticker.get("best_bid_price"),
                    ticker.get("best_ask_price"),
                    ticker,
                    ts,
                )
            )

        async def command(conn: asyncpg.Connection):
            query = """
                INSERT INTO tickers (
                    exchange, instrument_name, last_price, mark_price, index_price, open_interest,
                    best_bid_price, best_ask_price, data, exchange_timestamp, recorded_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                ON CONFLICT (exchange, instrument_name) DO UPDATE SET
                    last_price = EXCLUDED.last_price, mark_price = EXCLUDED.mark_price, index_price = EXCLUDED.index_price,
                    open_interest = EXCLUDED.open_interest, best_bid_price = EXCLUDED.best_bid_price,
                    best_ask_price = EXCLUDED.best_ask_price, data = EXCLUDED.data,
                    exchange_timestamp = EXCLUDED.exchange_timestamp, recorded_at = NOW();
            """
            async with conn.transaction():
                await conn.executemany(query, records_to_upsert)

        try:
            await self._execute_resiliently(command, "bulk_upsert_tickers")
            log.debug(f"Successfully bulk-upserted {len(records_to_upsert)} tickers.")
        except Exception as e:
            log.error(f"Error during bulk upsert of tickers: {e}")
            raise
