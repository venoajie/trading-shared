
# src/trading_shared/trading_shared/cache/universe_cache.py

import asyncio
from typing import Dict, List, Any, Optional
import orjson
from loguru import logger as log
from trading_engine_core.models import StorageMode
from trading_shared.clients.redis_client import CustomRedisClient

class UniverseCache:
    """
    Maintains a dynamic mapping between raw exchange symbols and canonical internal names.
    Inherits the hyphenation structure from the Janitor via the active ledger.
    """
    def __init__(self, redis_client: CustomRedisClient, universe_key: str):
        self._redis = redis_client
        self._universe_key = universe_key
        # Maps 'BTCUSDT' (Raw) -> 'BTC-USDT' (Canonical)
        self._raw_to_canonical: Dict[str, str] = {}
        self._storage_cache: Dict[str, StorageMode] = {}
        self._lock = asyncio.Lock()

    def get_canonical_name(self, raw_symbol: str) -> Optional[str]:
        """Looks up the canonical name from the dynamic map. Returns None if unknown."""
        # Normalize the raw input to uppercase and strip separators for the lookup key
        lookup_key = raw_symbol.strip().replace("-", "").replace("_", "").upper()
        return self._raw_to_canonical.get(lookup_key)

    async def get_storage_mode(self, instrument_name: str) -> StorageMode:
        async with self._lock:
            return self._storage_cache.get(instrument_name, StorageMode.PERSISTENT)

    async def refresh(self):
        try:
            raw_bytes = await self._redis.get(self._universe_key)
            if not raw_bytes: return
            
            data = orjson.loads(raw_bytes)
            new_storage, new_canonical = {}, {}
            
            for entry in data:
                # Canonical name from Janitor (e.g., 'BTC-USDT')
                name = entry.get("symbol") or entry.get("instrument_name")
                if not name: continue
                
                new_storage[name] = StorageMode.PERSISTENT
                
                # Create the raw key for mapping: 'BTC-USDT' -> 'BTCUSDT'
                raw_key = name.replace("-", "").replace("_", "").upper()
                new_canonical[raw_key] = name
                # Redundancy: map the name itself
                new_canonical[name.upper()] = name

            async with self._lock:
                self._storage_cache, self._raw_to_canonical = new_storage, new_canonical
            log.info(f"UniverseCache refreshed. {len(new_canonical)} dynamic mappings active.")
        except Exception:
            log.exception("UniverseCache refresh failed.")