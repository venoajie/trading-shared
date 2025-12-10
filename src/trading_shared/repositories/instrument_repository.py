# src/trading_shared/repositories/instrument_repository.py

# --- Built Ins  ---
from typing import List, Dict, Any

# --- Installed  ---
import asyncpg

# --- Local Application Imports ---
from trading_shared.clients.postgres_client import PostgresClient


class InstrumentRepository:
    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    async def fetch_all(self) -> List[asyncpg.Record]:
        return await self._db.fetch("SELECT * FROM v_instruments")

    async def fetch_by_exchange(
        self,
        exchange_name: str,
    ) -> List[asyncpg.Record]:
        query = "SELECT * FROM v_instruments WHERE exchange = $1"
        return await self._db.fetch(query, exchange_name)

    async def bulk_upsert(
        self,
        instruments: List[Dict[str, Any]],
        exchange_name: str,
    ):
        if not instruments:
            return
        instruments_with_exchange = [
            {**inst, "exchange": exchange_name} for inst in instruments
        ]
        await self._db.execute(
            "SELECT bulk_upsert_instruments($1::jsonb[])",
            instruments_with_exchange,
        )
