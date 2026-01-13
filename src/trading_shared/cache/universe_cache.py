
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
    Acts as the Single Source of Truth for symbol normalization in downstream services.
    """
    def __init__(self, redis_client: CustomRedisClient, universe_key: str):
        self._redis = redis_client
        self._universe_key = universe_key
        
        # Maps 'BTCUSDT' (Raw) -> 'BTC-USDT' (Canonical)
        self._raw_to_canonical: Dict[str, str] = {}
        # Maps 'BTC-USDT' -> StorageMode.PERSISTENT
        self._storage_cache: Dict[str, StorageMode] = {}
        # Full list of instruments for Analyzer/Strategy iteration
        self._instrument_list: List[Dict[str, Any]] = []
        
        self._lock = asyncio.Lock()

    def get_canonical_name(self, raw_symbol: str) -> Optional[str]:
        """Looks up the canonical name from the dynamic map. Returns None if unknown."""
        if not raw_symbol: return None
        # Normalize the raw input to uppercase and strip separators for the lookup key
        lookup_key = raw_symbol.strip().replace("-", "").replace("_", "").upper()
        return self._raw_to_canonical.get(lookup_key)

    def get_all_instruments(self) -> List[Dict[str, Any]]:
        """Returns the cached list of all active instruments."""
        return self._instrument_list

    async def get_storage_mode(self, instrument_name: str) -> StorageMode:
        async with self._lock:
            # Default to PERSISTENT to prevent data loss if cache is momentarily desynced
            return self._storage_cache.get(instrument_name, StorageMode.PERSISTENT)

    async def refresh(self):
        """
        Fetches the active ledger from Redis and rebuilds local lookup maps.
        """
        try:
            raw_bytes = await self._redis.get(self._universe_key)
            if not raw_bytes: 
                log.warning(f"Universe key '{self._universe_key}' is empty or missing.")
                async with self._lock:
                    self._instrument_list = []
                    self._raw_to_canonical = {}
                return
            
            # The value is a JSON array of dicts
            data = orjson.loads(raw_bytes)
            
            new_storage = {}
            new_canonical = {}
            new_instrument_list = []
            
            for entry in data:
                # [CRITICAL FIX] Janitor publishes 'symbol', Model expects 'instrument_name'.
                # We must support BOTH to ensure compatibility.
                name = entry.get("instrument_name") or entry.get("symbol")
                exchange = entry.get("exchange")
                
                if not name or not exchange:
                    continue
                
                # 1. Build Instrument List (for Analyzer)
                # Ensure we standardize on 'instrument_name' for internal usage
                clean_entry = entry.copy()
                clean_entry["instrument_name"] = name
                new_instrument_list.append(clean_entry)
                
                # 2. Build Storage Mode Map
                new_storage[name] = StorageMode.PERSISTENT
                
                # 3. Build Normalization Map (Raw -> Canonical)
                # Create the raw key: 'BTC-USDT' -> 'BTCUSDT'
                raw_key_no_hyphen = name.replace("-", "").replace("_", "").upper()
                
                # Map 'BTCUSDT' -> 'BTC-USDT'
                new_canonical[raw_key_no_hyphen] = name
                # Map 'BTC-USDT' -> 'BTC-USDT' (Identity redundancy)
                new_canonical[name.upper()] = name

            async with self._lock:
                self._storage_cache = new_storage
                self._raw_to_canonical = new_canonical
                self._instrument_list = new_instrument_list

            log.info(f"UniverseCache refreshed. {len(new_canonical)} mappings active. {len(new_instrument_list)} instruments loaded.")
            
        except Exception as e:
            log.exception(f"UniverseCache refresh failed: {e}")