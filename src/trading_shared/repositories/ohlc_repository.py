# src/trading_shared/repositories/ohlc_repository.py

# --- Built Ins  ---
from typing import Any, List, Optional
from datetime import UTC, datetime, timedelta

# --- Installed  ---
import asyncpg
from loguru import logger as log

# --- Local Application Imports ---
from trading_shared.clients.postgres_client import PostgresClient


class OhlcRepository:
    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    def _parse_resolution_to_timedelta(self, resolution: str) -> timedelta:
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

    def _prepare_ohlc_record(self, candle_data: dict[str, Any]) -> tuple:
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
        )

    async def fetch_latest_timestamp(
        self, exchange: str, instrument: str, res_td: timedelta
    ) -> Optional[datetime]:
        query = "SELECT MAX(tick) AS latest_tick FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3"
        result = await self._db.fetchrow(query, exchange, instrument, res_td)
        return result["latest_tick"] if result and result["latest_tick"] else None

    async def fetch_for_instrument(
        self, exchange: str, instrument: str, res_str: str, limit: int
    ) -> List[asyncpg.Record]:
        res_td = self._parse_resolution_to_timedelta(res_str)
        query = "SELECT * FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3 ORDER BY tick DESC LIMIT $4"
        return await self._db.fetch(query, exchange, instrument, res_td, limit)

    async def bulk_upsert(self, candles: list[dict[str, Any]]):
        if not candles:
            return
        records = [self._prepare_ohlc_record(c) for c in candles]
        await self._db.execute(
            "SELECT bulk_upsert_ohlc($1::ohlc_upsert_type[])", records
        )
