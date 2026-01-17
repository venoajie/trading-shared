# src/trading_shared/repositories/ohlc_repository.py

from datetime import datetime, timezone
from typing import Any

import asyncpg
from loguru import logger as log

from trading_shared.clients.postgres_client import PostgresClient


class OhlcRepository:
    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    def _prepare_ohlc_record(self, candle_data: dict[str, Any]) -> tuple | None:
        """
        Prepares a single candle dictionary into a tuple for the 'ohlc_upsert_type' composite type.
        """
        try:
            # Handle timestamps (ms int -> datetime)
            tick = candle_data.get("tick")
            if isinstance(tick, (int, float)):
                tick_dt = datetime.fromtimestamp(tick / 1000, tz=timezone.utc)
            else:
                tick_dt = tick

            # [FIX] Pass resolution as a string directly.
            # The DB expects VARCHAR/TEXT, not an INTERVAL/timedelta.
            resolution_str = str(candle_data.get("resolution") or "")

            return (
                candle_data.get("exchange"),
                candle_data.get("instrument_name"),
                resolution_str,
                tick_dt,
                float(candle_data.get("open") or 0.0),
                float(candle_data.get("high") or 0.0),
                float(candle_data.get("low") or 0.0),
                float(candle_data.get("close") or 0.0),
                float(candle_data.get("volume") or 0.0),
                float(candle_data.get("open_interest") or 0.0),
                float(candle_data.get("taker_buy_volume") or 0.0),
                float(candle_data.get("taker_sell_volume") or 0.0),
            )
        except Exception as e:
            log.error(f"Failed to prepare OHLC record: {e}")
            return None

    async def fetch_latest_timestamp(
        self,
        exchange: str,
        instrument: str,
        resolution: str,
    ) -> datetime | None:
        """
        Fetches the timestamp of the most recent candle for a given instrument.
        """
        # [FIX] Removed timedelta conversion. Passed raw string to DB.
        query = "SELECT MAX(tick) AS latest_tick FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3"
        try:
            # Ensure resolution is a string
            res_str = str(resolution)
            result = await self._db.fetchrow(query, exchange, instrument, res_str)
            return result["latest_tick"] if result and result["latest_tick"] else None
        except Exception as e:
            log.error(f"Error fetching latest timestamp for {instrument} ({resolution}): {e}")
            raise e

    async def fetch_for_instrument(
        self,
        exchange: str,
        instrument: str,
        resolution: str,
        limit: int,
    ) -> list[asyncpg.Record]:
        """
        Fetches the most recent N candles.
        """
        # [FIX] Removed timedelta conversion. Passed raw string to DB.
        res_str = str(resolution)
        query = "SELECT * FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3 ORDER BY tick DESC LIMIT $4"
        return await self._db.fetch(query, exchange, instrument, res_str, limit)

    async def bulk_upsert(self, candles: list[dict[str, Any]]):
        if not candles:
            return

        records = [self._prepare_ohlc_record(c) for c in candles]
        valid_records = [r for r in records if r is not None]

        if not valid_records:
            return

        try:
            # Assumes 'bulk_upsert_ohlc' stored procedure exists in Postgres
            # and accepts the tuple structure defined in _prepare_ohlc_record
            await self._db.execute("SELECT bulk_upsert_ohlc($1::ohlc_upsert_type[])", valid_records)
        except Exception as e:
            log.error(f"Bulk upsert failed: {e}")
            raise e
