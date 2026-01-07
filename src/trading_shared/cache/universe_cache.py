# src/trading_shared/trading_shared/cache/universe_cache.py

import asyncio
import json

from loguru import logger as log
from trading_engine_core.models import StorageMode

from trading_shared.clients.redis_client import CustomRedisClient


class UniverseCache:
    """
    An in-memory cache of the active universe's storage modes.
    Used by Distributor and Analyzer to make routing decisions without hitting Redis for every single tick.
    """

    def __init__(self, redis_client: CustomRedisClient, universe_key: str):
        self._redis = redis_client
        self._universe_key = universe_key
        self._cache: dict[str, StorageMode] = {}
        self._lock = asyncio.Lock()

    async def get_storage_mode(self, instrument_name: str) -> StorageMode:
        """
        Returns the storage mode for an instrument.
        Defaults to PERSISTENT (Postgres) if unknown, for safety.
        """
        async with self._lock:
            # Defaulting to PERSISTENT means "save it" if we are unsure.
            # This prevents data loss during startup/race conditions.
            return self._cache.get(instrument_name, StorageMode.PERSISTENT)

    async def refresh(self):
        """Reloads the entire universe map from the canonical Redis key."""
        try:
            raw_ledger = await self._redis.get(self._universe_key)
            if not raw_ledger:
                log.warning(f"Active ledger key '{self._universe_key}' not found in Redis. Cache remains empty.")
                return

            # Deserialize: List[Dict] -> List[Model] -> Dict[Symbol, Mode]
            # Assumes the JSON is a list of ActiveLedgerEntry objects
            data = json.loads(raw_ledger)

            # Robust parsing: handle if data is just a list of dicts from the old format
            # or the new ActiveLedgerEntry format.
            new_cache = {}
            for entry in data:
                # Handle both object and dict access for robustness
                name = entry.get("spot_symbol") or entry.get("instrument_name")
                mode = entry.get("storage_mode", StorageMode.PERSISTENT)
                if name:
                    new_cache[name] = mode

            async with self._lock:
                self._cache = new_cache

            log.info(f"UniverseCache refreshed. Loaded {len(self._cache)} instruments.")

        except Exception as e:
            log.error(f"Failed to refresh UniverseCache: {e}")
