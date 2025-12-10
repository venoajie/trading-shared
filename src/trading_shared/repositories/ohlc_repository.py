# src/trading_shared/repositories/ohlc_repository.py

from typing import Any, List, Optional
import asyncpg
from datetime import datetime, timedelta
from trading_shared.clients.postgres_client import PostgresClient


class OhlcRepository:
    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    async def fetch_latest_timestamp(
        self, exchange: str, instrument: str, res_td: timedelta
    ) -> Optional[datetime]:
        query = "SELECT MAX(tick) AS latest_tick FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3"
        result = await self._db.fetchrow(query, exchange, instrument, res_td)
        return result["latest_tick"] if result and result["latest_tick"] else None

    async def fetch_for_instrument(
        self, exchange: str, instrument: str, res_str: str, limit: int
    ) -> List[asyncpg.Record]:
        # This is the implementation for the missing method
        res_td = self._db._parse_resolution_to_timedelta(res_str)
        query = "SELECT * FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3 ORDER BY tick DESC LIMIT $4"
        return await self._db.fetch(query, exchange, instrument, res_td, limit)

    async def bulk_upsert(self, candles: list[dict[str, Any]]):
        # This requires moving _prepare_ohlc_record to the repo or making it public.
        # For simplicity, we assume _parse_resolution_to_timedelta is accessible.
        records = [self._prepare_ohlc_record(c) for c in candles]
        await self._db.execute(
            "SELECT bulk_upsert_ohlc($1::ohlc_upsert_type[])", records
        )

    def _prepare_ohlc_record(self, candle_data):  # Simplified for brevity
        # ... logic from PostgresClient._prepare_ohlc_record ...
        pass
