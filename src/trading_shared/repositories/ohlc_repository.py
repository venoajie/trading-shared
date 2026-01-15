# src/trading_shared/repositories/ohlc_repository.py

from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
from loguru import logger as log

from trading_shared.clients.postgres_client import PostgresClient


class OhlcRepository:
    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    def _parse_resolution_to_timedelta(self, resolution: str | timedelta) -> timedelta:
        """
        robustly converts resolution strings (or existing timedeltas) to timedelta objects.
        """
        if isinstance(resolution, timedelta):
            return resolution

        try:
            # Normalize string
            res_str = str(resolution).upper().strip()

            if res_str.endswith("D"):
                return timedelta(days=int(res_str[:-1]))
            if res_str.endswith("W"):
                return timedelta(weeks=int(res_str[:-1]))
            if res_str.endswith("H"):
                return timedelta(hours=int(res_str[:-1]))
            if res_str.endswith("M"):
                # Note: In standard crypto context, 'm' is minutes.
                return timedelta(minutes=int(res_str[:-1]))

            # Default to minutes if just a number string (e.g. "60")
            return timedelta(minutes=int(res_str))
        except (ValueError, TypeError):
            log.warning(f"Could not parse resolution '{resolution}', defaulting to 1 minute.")
            return timedelta(minutes=1)

    def _prepare_ohlc_record(self, candle_data: dict[str, Any]) -> tuple | None:
        """
        Prepares a single candle dictionary into a tuple for the 'ohlc_upsert_type' composite type.
        Handles None values defensively.
        """
        try:
            # Handle timestamps (ms int -> datetime)
            tick = candle_data.get("tick")
            if isinstance(tick, (int, float)):
                tick_dt = datetime.fromtimestamp(tick / 1000, tz=timezone.utc)
            else:
                tick_dt = tick  # Assume already datetime or let DB handle error

            resolution_td = self._parse_resolution_to_timedelta(candle_data.get("resolution"))

            # Defensive casting with defaults
            return (
                candle_data.get("exchange"),
                candle_data.get("instrument_name"),
                resolution_td,
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
        resolution: str | timedelta,
    ) -> datetime | None:
        """
        Fetches the timestamp of the most recent candle for a given instrument.
        """
        # [FIX] Auto-convert string resolution to timedelta for DB query
        res_td = self._parse_resolution_to_timedelta(resolution)

        query = "SELECT MAX(tick) AS latest_tick FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3"
        try:
            result = await self._db.fetchrow(query, exchange, instrument, res_td)
            return result["latest_tick"] if result and result["latest_tick"] else None
        except Exception as e:
            log.error(f"Error fetching latest timestamp for {instrument}: {e}")
            raise e

    async def fetch_for_instrument(
        self,
        exchange: str,
        instrument: str,
        resolution: str | timedelta,
        limit: int,
    ) -> list[asyncpg.Record]:
        """
        Fetches the most recent N candles.
        """
        res_td = self._parse_resolution_to_timedelta(resolution)
        query = "SELECT * FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3 ORDER BY tick DESC LIMIT $4"
        return await self._db.fetch(query, exchange, instrument, res_td, limit)

    async def bulk_upsert(self, candles: list[dict[str, Any]]):
        if not candles:
            return

        records = [self._prepare_ohlc_record(c) for c in candles]
        valid_records = [r for r in records if r is not None]

        if not valid_records:
            return

        try:
            # Assumes 'bulk_upsert_ohlc' stored procedure exists in Postgres
            await self._db.execute("SELECT bulk_upsert_ohlc($1::ohlc_upsert_type[])", valid_records)
        except Exception as e:
            log.error(f"Bulk upsert failed: {e}")
            raise e
