# src/trading_shared/repositories/universe_repository.py
from typing import Dict, Any, List

from loguru import logger as log

from trading_shared.clients.postgres_client import PostgresClient


class UniverseRepository:
    """
    Read-only repository for querying materialized universe views.
    Used by Backfill and Maintenance services to identify persistent assets.
    """

    def __init__(self, db_client: PostgresClient):
        self.db = db_client

    async def get_persistent_instruments_by_exchange(self, exchange: str) -> list[str]:
        """
        Queries the 'v_persistent_instruments' view to find all assets
        designated for persistent storage (Tier 1).
        """
        query = """
        SELECT instrument_name
        FROM v_persistent_instruments
        WHERE exchange = $1
        """
        try:
            records = await self.db.fetch(query, exchange)
            return [r["instrument_name"] for r in records]
        except Exception as e:
            log.error(f"Failed to fetch persistent instruments for {exchange}: {e}")
            return []


    async def get_all_persistent_instruments(self) -> List[Dict[str, Any]]:
        """
        Queries the 'v_persistent_instruments' view to get ALL assets
        designated for persistent storage, across all exchanges.
        """
        query = "SELECT instrument_name, exchange FROM v_persistent_instruments"
        try:
            records = await self.db.fetch(query)
            # Convert to the dict structure the Analyzer expects
            return [dict(r) for r in records]
        except Exception as e:
            # It's critical to log this, as it's a sign the Janitor has failed
            log.error(f"Failed to fetch all persistent instruments from view. Has Janitor run successfully? Error: {e}")
            return []