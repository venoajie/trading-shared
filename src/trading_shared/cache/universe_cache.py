
# src/trading_shared/trading_shared/cache/universe_cache.py

import asyncio
import orjson
from typing import Dict, List, Any, Optional
from loguru import logger as log
from trading_engine_core.models import StorageMode
from trading_shared.clients.redis_client import CustomRedisClient

class UniverseCache:
    """
    In-memory cache of the active universe.
    Acts as the Single Source of Truth for symbol normalization and routing.
    Synchronizes with the 'system:state:janitor:active_ledger' Redis key.
    """
    def __init__(self, redis_client: CustomRedisClient, universe_key: str):
        self._redis = redis_client
        self._universe_key = universe_key

        # Fast Lookup: RAW (BTCUSDT) -> CANONICAL (BTC-USDT)
        self._raw_to_canonical: Dict[str, str] = {}
        # Storage Rules: CANONICAL -> StorageMode
        self._storage_cache: Dict[str, StorageMode] = {}
        # Iteration List: List of all active instrument dicts (for Analyzer)
        self._instrument_list: List[Dict[str, Any]] = []

        self._lock = asyncio.Lock()

    def get_canonical_name(self, raw_symbol: str) -> Optional[str]:
        """
        Normalizes a raw symbol. Returns None if symbol is not in the active universe.
        This provides the 'Strict Gating' capability.
        """
        if not raw_symbol: return None
        lookup_key = raw_symbol.strip().replace("-", "").replace("_", "").upper()
        return self._raw_to_canonical.get(lookup_key)

    def get_all_instruments(self) -> List[Dict[str, Any]]:
        """Returns the full list of active instruments (Thread-safe due to copy-on-write)."""
        return self._instrument_list

    async def get_storage_mode(self, instrument_name: str) -> StorageMode:
        """Returns storage persistence preference for an instrument."""
        async with self._lock:
            # Default to PERSISTENT to prevent data loss if cache is momentarily desynced
            return self._storage_cache.get(instrument_name, StorageMode.PERSISTENT)

    async def refresh(self):
        """Reloads the cache from Redis."""
        try:
            raw_bytes = await self._redis.get(self._universe_key)
            if not raw_bytes:
                log.warning(f"Universe key '{self._universe_key}' is empty or missing.")
                async with self._lock:
                    self._instrument_list, self._raw_to_canonical, self._storage_cache = [], {}, {}
                return

            data = orjson.loads(raw_bytes)
            new_storage, new_canonical, new_list = {}, {}, []

            for entry in data:
                # Schema Compatibility: Support 'instrument_name' (Model) and 'symbol' (Janitor's SQL alias)
                name = entry.get("instrument_name") or entry.get("symbol")
                exchange = entry.get("exchange")
                if not name or not exchange: continue

                # 1. Build List for Analyzer
                clean_entry = entry.copy()
                clean_entry["instrument_name"] = name
                new_list.append(clean_entry)

                # 2. Build Normalization Map
                raw_key = name.replace("-", "").replace("_", "").upper()
                new_canonical[raw_key] = name
                new_canonical[name.upper()] = name # Identity mapping

                # 3. Build Storage Map
                new_storage[name] = StorageMode.PERSISTENT

            async with self._lock:
                self._storage_cache = new_storage
                self._raw_to_canonical = new_canonical
                self._instrument_list = new_list

            log.info(f"UniverseCache refreshed. {len(new_canonical)} mappings active. {len(new_list)} instruments loaded.")
        except Exception as e:
            log.exception(f"UniverseCache refresh failed: {e}")