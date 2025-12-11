# src/trading_shared/repositories/trade_repository.py

# --- Built Ins ---
from typing import List, Optional

# --- Installed ---
import asyncpg

# --- Local Application Imports ---
from trading_shared.clients.postgres_client import PostgresClient


class TradeRepository:
    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    async def fetch_active_trades(
        self, user_id: Optional[str] = None
    ) -> List[asyncpg.Record]:
        query = "SELECT * FROM v_active_trades"
        params = [user_id] if user_id else []
        if user_id:
            query += " WHERE user_id = $1"
        return await self._db.fetch(query, *params)
