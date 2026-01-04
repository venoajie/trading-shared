# src/trading_shared/repositories/ohlc_repository.py

# --- Built Ins  ---
from datetime import UTC, datetime, timedelta
from typing import Any

# --- Installed  ---
import asyncpg
from loguru import logger as log

# --- Local Application Imports ---
from trading_shared.clients.postgres_client import PostgresClient


class OhlcRepository:
    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    def _parse_resolution_to_timedelta(self, resolution: str) -> timedelta:
        # NOTE: This logic could be simplified, but is functionally correct.
        # Keeping as-is to focus on the critical bug fix.
        try:
            if resolution.upper().endswith("D"):
                return timedelta(days=int(resolution[:-1]))
            if resolution.upper().endswith("W"):
                return timedelta(weeks=int(resolution[:-1]))
            if resolution.upper().endswith("H"):
                return timedelta(hours=int(resolution[:-1]))
            return timedelta(minutes=int(resolution))
        except ValueError as e:
            log.warning(f"Could not parse resolution '{resolution}', defaulting to minutes.")
            # Fallback for formats like "1", "5", "60"
            return timedelta(minutes=int(resolution))

    def _prepare_ohlc_record(self, candle_data: dict[str, Any]) -> tuple:
        """
        Prepares a single candle dictionary into a tuple that EXACTLY matches
        the 'ohlc_upsert_type' composite type in PostgreSQL.
        
        CORRECTED: Now includes taker_buy_volume and taker_sell_volume.
        """
        # The tick from upstream sources is a millisecond timestamp.
        # datetime.fromtimestamp expects seconds.
        tick_dt = datetime.fromtimestamp(candle_data["tick"] / 1000, tz=UTC)
        resolution_td = self._parse_resolution_to_timedelta(candle_data["resolution"])
        
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
            # --- ADD MISSING MICROSTRUCTURE FIELDS ---
            # Use .get() with a default of 0.0 to safely handle data from exchanges
            # like Deribit that do not provide these metrics.
            candle_data.get("taker_buy_volume", 0.0),
            candle_data.get("taker_sell_volume", 0.0),
        )

    async def fetch_latest_timestamp(
        self,
        exchange: str,
        instrument: str,
        res_td: timedelta,
    ) -> datetime | None:
        query = "SELECT MAX(tick) AS latest_tick FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3"
        result = await self._db.fetchrow(query, exchange, instrument, res_td)
        return result["latest_tick"] if result and result["latest_tick"] else None

    async def fetch_for_instrument(
        self,
        exchange: str,
        instrument: str,
        res_str: str,
        limit: int,
    ) -> list[asyncpg.Record]:
        res_td = self._parse_resolution_to_timedelta(res_str)
        query = "SELECT * FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3 ORDER BY tick DESC LIMIT $4"
        return await self._db.fetch(query, exchange, instrument, res_td, limit)

    async def bulk_upsert(self, candles: list[dict[str, Any]]):
        if not candles:
            return
            
        try:
            records = [self._prepare_ohlc_record(c) for c in candles]
            await self._db.execute("SELECT bulk_upsert_ohlc($1::ohlc_upsert_type[])", records)
        except (KeyError, TypeError) as e:
            log.error(f"Data contract violation: A candle was missing a required key. Error: {e}")
            # Optionally, you could filter out the bad candle and retry, but for now we fail the batch.
            raise