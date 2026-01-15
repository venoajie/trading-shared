
# src/trading_shared/repositories/ohlc_repository.py

from datetime import datetime, timedelta, timezone
from typing import Any, List, Union, Optional

import asyncpg
from loguru import logger as log
from trading_shared.clients.postgres_client import PostgresClient

class OhlcRepository:
    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    def _parse_resolution_to_timedelta(self, resolution: Union[str, timedelta]) -> timedelta:
        """
        Parses a resolution string (e.g., '1', '1m', '1h', '1D') into a timedelta.
        
        This method is made robust to also accept a timedelta object as input, in which
        case it will be returned directly. This prevents crashes in services like Backfill
        that may work with timedelta objects internally.
        """
        # [ROBUSTNESS FIX] If the input is already a timedelta, return it immediately.
        if isinstance(resolution, timedelta):
            return resolution

        try:
            # Normalize to a common format for parsing
            res_str = str(resolution).upper().strip()

            if res_str.endswith("D"):
                return timedelta(days=int(res_str[:-1]))
            if res_str.endswith("W"):
                return timedelta(weeks=int(res_str[:-1]))
            if res_str.endswith("H"):
                return timedelta(hours=int(res_str[:-1]))
            if res_str.endswith("M"):
                return timedelta(minutes=int(res_str[:-1]))

            # Fallback for formats without a suffix, like "1", "5", "60"
            return timedelta(minutes=int(res_str))
        except (ValueError, TypeError):
            log.warning(f"Could not parse resolution '{resolution}', defaulting to 1 minute.")
            return timedelta(minutes=1)

    def _prepare_ohlc_record(self, candle_data: dict[str, Any]) -> tuple:
        """
        Prepares a single candle dictionary into a tuple that EXACTLY matches
        the 'ohlc_upsert_type' composite type defined in PostgreSQL. This ensures
        type safety and performance for bulk database operations.
        """
        try:
            # Millisecond timestamps from exchanges must be converted to seconds for fromtimestamp
            tick_ms = candle_data["tick"]
            tick_dt = datetime.fromtimestamp(tick_ms / 1000, tz=timezone.utc) if isinstance(tick_ms, (int, float)) else tick_ms

            resolution_td = self._parse_resolution_to_timedelta(candle_data["resolution"])

            return (
                candle_data["exchange"],
                candle_data["instrument_name"],
                resolution_td,
                tick_dt,
                float(candle_data["open"]),
                float(candle_data["high"]),
                float(candle_data["low"]),
                float(candle_data["close"]),
                float(candle_data["volume"]),
                # Use .get() with defaults for optional fields to prevent KeyErrors
                float(candle_data.get("open_interest", 0.0)),
                float(candle_data.get("taker_buy_volume", 0.0)),
                float(candle_data.get("taker_sell_volume", 0.0)),
            )
        except (KeyError, ValueError, TypeError) as e:
            log.error(f"Failed to prepare OHLC record due to data contract violation: {e}")
            # Propagate the error to fail the batch, preventing partial data insertion.
            raise e

    async def fetch_latest_timestamp(
        self,
        exchange: str,
        instrument: str,
        res_td: timedelta,
    ) -> Optional[datetime]:
        """Fetches the most recent timestamp for a given instrument and resolution."""
        query = "SELECT MAX(tick) AS latest_tick FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3"
        result = await self._db.fetchrow(query, exchange, instrument, res_td)
        return result["latest_tick"] if result and result["latest_tick"] else None

    async def fetch_for_instrument(
        self,
        exchange: str,
        instrument: str,
        res_str: str,
        limit: int,
    ) -> List[asyncpg.Record]:
        """Fetches a limited number of recent OHLC records for an instrument."""
        res_td = self._parse_resolution_to_timedelta(res_str)
        query = "SELECT * FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3 ORDER BY tick DESC LIMIT $4"
        return await self._db.fetch(query, exchange, instrument, res_td, limit)

    async def bulk_upsert(self, candles: List[dict[str, Any]]):
        """
        Performs a high-performance bulk upsert of OHLC data using a PostgreSQL
        stored procedure ('bulk_upsert_ohlc') and a composite type ('ohlc_upsert_type').
        """
        if not candles:
            return

        try:
            records = [self._prepare_ohlc_record(c) for c in candles]
            await self._db.execute("SELECT bulk_upsert_ohlc($1::ohlc_upsert_type[])", records)
            log.debug(f"Successfully bulk-upserted {len(records)} OHLC records.")
        except Exception as e:
            # Errors from _prepare_ohlc_record are caught and logged there.
            # This catches the transaction-level failure.
            log.error(f"Bulk upsert transaction failed: {e}")
            raise