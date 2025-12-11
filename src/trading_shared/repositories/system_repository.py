# src/trading_shared/repositories/system_repository.py

# --- Installed ---
from loguru import logger as log

# --- Local Application Imports ---
from trading_shared.clients.postgres_client import PostgresClient


class SystemRepository:
    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    async def check_bootstrap_status(self, exchange_name: str) -> bool:
        key = f"bootstrap_status:{exchange_name}"
        query = "SELECT value FROM system_metadata WHERE key = $1"
        result = await self._db.fetchval(query, key)
        return result == "complete"

    async def set_bootstrap_status(self, is_complete: bool, exchange_name: str):
        key = f"bootstrap_status:{exchange_name}"
        status = "complete" if is_complete else "incomplete"
        query = """
            INSERT INTO system_metadata (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
        """
        await self._db.execute(query, key, status)
        log.info(f"Set bootstrap_status:{exchange_name} to '{status}' in database.")
