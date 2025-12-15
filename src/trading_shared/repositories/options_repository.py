# src/trading_shared/repositories/options_repository.py

# --- Built Ins ---
from typing import List, Dict, Any

# --- Local Application Imports ---
from trading_shared.clients.postgres_client import PostgresClient


class OptionsRepository:
    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    async def bulk_insert(self, options_data: List[Dict[str, Any]]):
        """
        Inserts a batch of options market data using the Postgres Composite Type.
        """
        if not options_data:
            return

        # Map Dicts to Tuples matching 'option_trade_insert_type' order:
        # (exchange, instrument_name, tick, price, quantity,
        #  iv, delta, gamma, vega, theta, rho, underlying_price)
        data_tuples = [
            (
                d["exchange"],
                d["instrument_name"],
                d["tick"],
                d["price"],
                d["quantity"],
                d.get("iv"),
                d.get("delta"),
                d.get("gamma"),
                d.get("vega"),
                d.get("theta"),
                d.get("rho"),
                d.get("underlying_price"),
            )
            for d in options_data
        ]

        query = """
            SELECT bulk_insert_options_data($1::option_trade_insert_type[])
        """

        await self._db.execute(query, data_tuples)
