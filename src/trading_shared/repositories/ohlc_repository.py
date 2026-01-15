
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
        if isinstance(resolution, timedelta): return resolution
        try:
            res_str = str(resolution).upper().strip()
            if res_str.endswith("D"): return timedelta(days=int(res_str[:-1]))
            if res_str.endswith("W"): return timedelta(weeks=int(res_str[:-1]))
            if res_str.endswith("H"): return timedelta(hours=int(res_str[:-1]))
            if res_str.endswith("M"): return timedelta(minutes=int(res_str[:-1]))
            return timedelta(minutes=int(res_str))
        except (ValueError, TypeError): return timedelta(minutes=1)

    def _prepare_ohlc_record(self, candle_data: dict[str, Any]) -> Optional[tuple]:
        """Prepares a candle for DB composite type, returning None if critical data is missing."""
        try:
            # [DEFENSIVE CODING] Use `or 0.0` fallback to safely handle None during float conversion.
            return (
                candle_data["exchange"],
                candle_data["instrument_name"],
                self._parse_resolution_to_timedelta(candle_data["resolution"]),
                datetime.fromtimestamp(candle_data["tick"] / 1000, tz=timezone.utc),
                float(candle_data.get("open") or 0.0),
                float(candle_data.get("high") or 0.0),
                float(candle_data.get("low") or 0.0),
                float(candle_data.get("close") or 0.0),
                float(candle_data.get("volume") or 0.0),
                float(candle_data.get("open_interest") or 0.0),
                float(candle_data.get("taker_buy_volume") or 0.0),
                float(candle_data.get("taker_sell_volume") or 0.0),
            )
        except (KeyError, TypeError) as e:
            log.error(f"Failed to prepare OHLC record due to missing critical keys: {e}")
            return None

    async def bulk_upsert(self, candles: List[dict[str, Any]]):
        if not candles: return

        records = [self._prepare_ohlc_record(c) for c in candles]
        valid_records = [r for r in records if r is not None]

        if not valid_records:
            log.warning("Bulk upsert skipped: no valid records after preparation.")
            return

        if len(valid_records) < len(candles):
            log.warning(f"Filtered {len(candles) - len(valid_records)} invalid records from upsert batch.")

        try:
            await self._db.execute("SELECT bulk_upsert_ohlc($1::ohlc_upsert_type[])", valid_records)
            log.debug(f"Successfully bulk-upserted {len(valid_records)} OHLC records.")
        except Exception as e:
            log.error(f"Bulk upsert transaction failed: {e}")
            raise