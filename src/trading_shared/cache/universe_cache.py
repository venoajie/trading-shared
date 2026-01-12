
# src/trading_shared/cache/universe_cache.py

import asyncio
from typing import Dict, List, Any, Optional
import orjson
from loguru import logger as log

from trading_engine_core.models import StorageMode
from trading_shared.clients.redis_client import CustomRedisClient

class UniverseCache:
    """
    AUTHORITATIVE in-memory cache of the active universe.
    Provides Strict Dynamic Normalization for all downstream services.
    """
    def __init__(self, redis_client: CustomRedisClient, universe_key: str):
        self._redis = redis_client
        self._universe_key = universe_key
        self._canonical_map: Dict[str, str] = {}
        self._storage_cache: Dict[str, StorageMode] = {}
        self._raw_ledger: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        log.info("UniverseCache (Strict, Shared Library v6.0) initialized.")

    def get_canonical_name(self, raw_symbol: str) -> Optional[str]:
        """
        Looks up the canonical BASE-QUOTE name. Returns NONE if not found.
        This is the strict gate that prevents data corruption.
        """
        clean_raw = raw_symbol.strip().replace("-", "").upper()
        return self._canonical_map.get(clean_raw)

    async def get_storage_mode(self, instrument_name: str) -> StorageMode:
        async with self._lock:
            return self._storage_cache.get(instrument_name, StorageMode.PERSISTENT)

    async def refresh(self):
        try:
            raw_ledger_bytes = await self._redis.get(self._universe_key)
            if not raw_ledger_bytes:
                log.warning(f"Active ledger key '{self._universe_key}' not found.")
                return

            data = orjson.loads(raw_ledger_bytes)
            new_storage, new_canonical = {}, {}
            for entry in data:
                name = entry.get("symbol") or entry.get("instrument_name")
                if not name: continue
                
                mode_str = entry.get("storage_mode", "POSTGRES")
                new_storage[name] = StorageMode.PERSISTENT if mode_str in ("POSTGRES", "PERSISTENT") else StorageMode.EPHEMERAL
                
                raw_key = name.replace("-", "").replace("_", "").upper()
                new_canonical[raw_key] = name
                new_canonical[name.upper()] = name

            async with self._lock:
                self._storage_cache, self._canonical_map, self._raw_ledger = new_storage, new_canonical, data
            log.info(f"UniverseCache refreshed. {len(new_canonical)} symbols mapped.")
        except Exception as e:
            log.exception("UniverseCache refresh failed.")