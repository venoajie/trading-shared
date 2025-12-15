# src/trading_shared/repositories/trade_repository.py

# --- Built Ins ---
from typing import List, Optional, Dict, Any, Tuple

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

    async def bulk_insert_public(self, trades: List[Dict[str, Any]]):
        """
        Inserts a batch of public trades using the Postgres Composite Type.
        """
        if not trades:
            return

        # Convert Dicts to Tuples in the EXACT order of the Postgres Type.
        # Type: public_trade_insert_type
        # (exchange, instrument_name, market_type, trade_id, price, quantity, 
        #  is_buyer_maker, was_best_price_match, trade_timestamp)
        trade_tuples = [
            (
                t["exchange"],
                t["instrument_name"],
                t["market_type"],
                t["trade_id"],
                t["price"],
                t["quantity"],
                t["is_buyer_maker"],
                t["was_best_price_match"],
                t["trade_timestamp"],
            )
            for t in trades
        ]

        query = """
            SELECT bulk_insert_public_trades($1::public_trade_insert_type[])
        """
        
        # We pass the list of tuples as a single argument. 
        # The PostgresClient's registered codec handles the array serialization.
        await self._db.execute(query, trade_tuples)