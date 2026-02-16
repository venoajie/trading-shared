# src/trading_shared/repositories/instrument_repository.py

# --- Built Ins  ---
from typing import Any, Optional

# --- Installed  ---
import asyncpg
from loguru import logger as log

# --- Local Application Imports ---
from trading_shared.clients.postgres_client import PostgresClient


class InstrumentRepository:
    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    async def fetch_all(self) -> list[asyncpg.Record]:
        return await self._db.fetch("SELECT * FROM public.instruments")

    async def fetch_by_exchange(self, exchange_name: str) -> list[asyncpg.Record]:
        query = "SELECT * FROM public.instruments WHERE exchange = $1"
        return await self._db.fetch(query, exchange_name)

    async def find_instrument_by_name_and_kind(self, exchange: str, canonical_name: str, instrument_kind: str) -> asyncpg.Record | None:
        """
        Finds a specific instrument record based on its canonical name and kind.
        e.g., Find the 'perpetual' instrument for the canonical name 'BTCUSDT'.
        """
        query = """
            SELECT * FROM public.instruments
            WHERE exchange = $1
            AND instrument_name = $2
            AND instrument_kind = $3
            LIMIT 1;
        """

        return await self._db.fetchrow(query, exchange, canonical_name, instrument_kind)

    async def bulk_upsert(self, instruments: list[dict[str, Any]], exchange_name: str):
        if not instruments:
            return
        instruments_with_exchange = [{**inst, "exchange": exchange_name} for inst in instruments]
        await self._db.execute(
            "SELECT bulk_upsert_instruments($1::jsonb[])",
            instruments_with_exchange,
        )
        log.info(f"Successfully bulk-upserted {len(instruments)} instruments for '{exchange_name}'.")

    async def get_furthest_active_future(self, currency: str) -> Optional[str]:
        """
        Finds the active future instrument with the furthest expiration date
        for the given currency.
        """
        # Note: Deribit 'base_asset' is usually the currency code (BTC, ETH)
        query = """
            SELECT instrument_name 
            FROM public.instruments 
            WHERE base_asset = $1 
              AND market_type = 'future' 
              AND is_active = TRUE 
            ORDER BY expiration_timestamp DESC 
            LIMIT 1;
        """
        try:
            record = await self.db_client.fetch_one(query, currency)
            return record["instrument_name"] if record else None
        except Exception:
            # Fallback or logging handled by caller/wrapper
            return None
