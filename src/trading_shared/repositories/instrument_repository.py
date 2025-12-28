# src/trading_shared/repositories/instrument_repository.py

# --- Built Ins  ---
from typing import List, Dict, Any, Optional

# --- Installed  ---
import asyncpg
from loguru import logger as log

# --- Local Application Imports ---
from trading_shared.clients.postgres_client import PostgresClient


class InstrumentRepository:
    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    async def fetch_all(self) -> List[asyncpg.Record]:
        return await self._db.fetch("SELECT * FROM v_instruments")

    async def fetch_by_exchange(self, exchange_name: str) -> List[asyncpg.Record]:
        query = "SELECT * FROM v_instruments WHERE exchange = $1"
        return await self._db.fetch(query, exchange_name)

    async def find_instrument_by_name_and_kind(
        self, exchange: str, canonical_name: str, instrument_kind: str
    ) -> Optional[asyncpg.Record]:
        """
        Finds a specific instrument record based on its canonical name and kind.
        e.g., Find the 'perpetual' instrument for the canonical name 'BTCUSDT'.
        """
        query = """
            SELECT * FROM v_instruments
            WHERE exchange = $1
            AND instrument_name = $2
            AND instrument_kind = $3
            LIMIT 1;
        """

        return await self._db.fetchrow(query, exchange, canonical_name, instrument_kind)

    async def bulk_upsert(self, instruments: List[Dict[str, Any]], exchange_name: str):
        if not instruments:
            return
        instruments_with_exchange = [
            {**inst, "exchange": exchange_name} for inst in instruments
        ]
        await self._db.execute(
            "SELECT bulk_upsert_instruments($1::jsonb[])",
            instruments_with_exchange,
        )
        log.info(
            f"Successfully bulk-upserted {len(instruments)} instruments for '{exchange_name}'."
        )
