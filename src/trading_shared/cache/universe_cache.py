
# src/trading_shared/cache/universe_cache.py

import asyncio
import orjson # Optimization: Replaces json
from typing import List, Dict, Any, Optional

from loguru import logger as log
from trading_engine_core.models import StorageMode
from trading_shared.clients.redis_client import CustomRedisClient

class UniverseCache:
    """
    An in-memory cache of the active universe's storage modes.
    Acts as the Single Source of Truth for routing and execution lists.
    """

    def __init__(self, redis_client: CustomRedisClient, universe_key: str):
        self._redis = redis_client
        self._universe_key = universe_key
        
        # Maps instrument_name -> StorageMode
        self._cache: Dict[str, StorageMode] = {}
        # Stores the full list of dictionaries for the Analyzer loop
        self._raw_ledger: List[Dict[str, Any]] = []
        
        self._lock = asyncio.Lock()

    async def get_storage_mode(self, instrument_name: str) -> StorageMode:
        """
        Returns the storage mode for an instrument.
        LEGACY SAFETY: Defaults to PERSISTENT (Postgres) if unknown.
        This prevents data loss during startup/race conditions.
        """
        async with self._lock:
            return self._cache.get(instrument_name, StorageMode.PERSISTENT)

    def get_all_instruments(self) -> List[Dict[str, Any]]:
        """
        Returns the full raw ledger.
        REQUIRED by Analyzer to iterate over the Broad universe.
        """
        # Returns a reference to the list. 
        # Since _raw_ledger is replaced atomically in refresh, this is safe for reading.
        return self._raw_ledger

    async def refresh(self):
        """Reloads the entire universe map from the canonical Redis key."""
        try:
            raw_ledger_bytes = await self._redis.get(self._universe_key)
            if not raw_ledger_bytes:
                log.warning(f"Active ledger key '{self._universe_key}' not found in Redis. Cache remains empty.")
                return

            # Optimization: Use orjson for faster deserialization
            data = orjson.loads(raw_ledger_bytes)

            new_cache = {}
            # Legacy Robustness: Handle variable field names
            for entry in data:
                name = entry.get("spot_symbol") or entry.get("instrument_name")
                
                # Logic: Check specific string "POSTGRES" to map to Enum, otherwise default to buffer
                mode_str = entry.get("storage_mode", "REDIS_BUFFER")
                mode = StorageMode.PERSISTENT if mode_str == "POSTGRES" else StorageMode.EPHEMERAL
                
                if name:
                    new_cache[name] = mode

            async with self._lock:
                self._cache = new_cache
                self._raw_ledger = data

            log.info(f"UniverseCache refreshed. Loaded {len(self._cache)} instruments.")

        except Exception as e:
            log.error(f"Failed to refresh UniverseCache: {e}")