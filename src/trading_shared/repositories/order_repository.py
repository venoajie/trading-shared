# src/trading_shared/repositories/order_repository.py

# --- Built Ins ---

# --- Installed ---
import asyncpg

# --- Local Application Imports ---
from trading_shared.clients.postgres_client import PostgresClient


class OrderRepository:
    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    async def fetch_open_orders(
        self,
        user_id: str | None = None,
    ) -> list[asyncpg.Record]:
        query = "SELECT * FROM orders WHERE trade_id IS NULL"
        params = [user_id] if user_id else []
        if user_id:
            query += " AND user_id = $1"
        query += " ORDER BY exchange_timestamp"
        return await self._db.fetch(query, *params)
