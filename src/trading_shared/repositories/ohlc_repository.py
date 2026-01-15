
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
        Parses a resolution string (e.g., '1', '1m', '1h') to a timedelta.
        Robustly handles inputs that are already timedelta objects.
        """
        if isinstance(resolution, timedelta):
            return resolution

        try:
            res_str = str(resolution).upper().strip()
            if res_str.endswith("D"): return timedelta(days=int(res_str[:-1]))
            if res_str.endswith("W"): return timedelta(weeks=int(res_str[:-1]))
            if res_str.endswith("H"): return timedelta(hours=int(res_str[:-1]))
            if res_str.endswith("M"): return timedelta(minutes=int(res_str[:-1]))
            return timedelta(minutes=int(res_str))
        except (ValueError, TypeError):
            log.warning(f"Could not parse resolution '{resolution}', defaulting to 1 minute.")
            return timedelta(minutes=1)

    def _prepare_ohlc_record(self, candle_data: dict[str, Any]) -> Optional[tuple]:
        """
        Prepares a candle dictionary for the 'ohlc_upsert_type' composite type.
        Returns None if critical data is missing, preventing the batch from failing.
        """
        try:
            # Critical fields that MUST exist.
            exchange = candle_data["exchange"]
            instrument_name = candle_data["instrument_name"]
            tick_ms = candle_data["tick"]
            
            # Convert timestamp if necessary
            tick_dt = datetime.fromtimestamp(tick_ms / 1000, tz=timezone.utc) if isinstance(tick_ms, (int, float)) else tick_ms
            resolution_td = self._parse_resolution_to_timedelta(candle_data["resolution"])

            # [ROBUSTNESS FIX] Use .get() with a default of 0.0 for all numeric fields.
            # This handles cases where the upstream source sends None for a price or volume.
            return (
                exchange,
                instrument_name,
                resolution_td,
                tick_dt,
                float(candle_data.get("open", 0.0)),
                float(candle_data.get("high", 0.0)),
                float(candle_data.get("low", 0.0)),
                float(candle_data.get("close", 0.0)),
                float(candle_data.get("volume", 0.0)),
                float(candle_data.get("open_interest", 0.0)),
                float(candle_data.get("taker_buy_volume", 0.0)),
                float(candle_data.get("taker_sell_volume", 0.0)),
            )
        except (KeyError, ValueError, TypeError) as e:
            # If even critical fields are missing, log the error and reject this record.
            log.error(f"Failed to prepare OHLC record due to missing critical keys: {e}")
            return None

    async def fetch_latest_timestamp(
        self, exchange: str, instrument: str, res_td: timedelta
    ) -> Optional[datetime]:
        """Fetches the most recent timestamp for a given instrument and resolution."""
        query = "SELECT MAX(tick) AS latest_tick FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3"
        result = await self._db.fetchrow(query, exchange, instrument, res_td)
        return result["latest_tick"] if result and result["latest_tick"] else None

    async def bulk_upsert(self, candles: List[dict[str, Any]]):
        """
        Performs a high-performance bulk upsert of OHLC data.
        Invalid records are filtered out to prevent the entire batch from failing.
        """
        if not candles:
            return

        # Filter out any records that failed preparation (returned None)
        records = [self._prepare_ohlc_record(c) for c in candles]
        valid_records = [r for r in records if r is not None]

        if not valid_records:
            log.warning("Bulk upsert skipped: no valid OHLC records remained after preparation.")
            return

        if len(valid_records) < len(candles):
            log.warning(f"Filtered out {len(candles) - len(valid_records)} invalid records from bulk upsert batch.")

        try:
            await self._db.execute("SELECT bulk_upsert_ohlc($1::ohlc_upsert_type[])", valid_records)
            log.debug(f"Successfully bulk-upserted {len(valid_records)} OHLC records.")
        except Exception as e:
            log.error(f"Bulk upsert transaction failed: {e}")
            raise