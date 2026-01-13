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
        
        self._instrument_list: List[Dict[str, Any]] = []
        
        self._lock = asyncio.Lock()

    def get_canonical_name(self, raw_symbol: str) -> Optional[str]:
        """Looks up the canonical name from the dynamic map. Returns None if unknown."""
        # Normalize the raw input to uppercase and strip separators for the lookup key
        lookup_key = raw_symbol.strip().replace("-", "").replace("_", "").upper()
        return self._raw_to_canonical.get(lookup_key)

    def get_all_instruments(self) -> List[Dict[str, Any]]:
        """Returns the cached list of all active instruments."""
        return self._instrument_list

    async def get_storage_mode(self, instrument_name: str) -> StorageMode:
        async with self._lock:
            return self._storage_cache.get(instrument_name, StorageMode.PERSISTENT)

    async def refresh(self):
        try:
            raw_bytes = await self._redis.get(self._universe_key)
            if not raw_bytes: 
                async with self._lock:
                    self._instrument_list = [] # Clear the list if Redis key is gone
                return
            
            # The value of the string key is a JSON array of ActiveLedgerEntry objects
            data = orjson.loads(raw_bytes)
            new_storage, new_canonical = {}, {}
            new_instrument_list = []
            
            for entry in data:
                # Per trading_engine_core/models.py, ActiveLedgerEntry
                name = entry.get("instrument_name")
                exchange = entry.get("exchange")
                if not name or not exchange: continue
                
                # Populate the instrument list for the Analyzer
                new_instrument_list.append({"symbol": name, "exchange": exchange})
                
                new_storage[name] = StorageMode.PERSISTENT
                
                # Create the raw key for mapping: 'BTC-USDT' -> 'BTCUSDT'
                raw_key = name.replace("-", "").replace("_", "").upper()
                new_canonical[raw_key] = name
                new_canonical[name.upper()] = name # Redundancy

            async with self._lock:
                self._storage_cache = new_storage
                self._raw_to_canonical = new_canonical
                self._instrument_list = new_instrument_list

            log.info(f"UniverseCache refreshed. {len(new_canonical)} mappings active. {len(new_instrument_list)} instruments loaded.")
        except Exception:
            log.exception("UniverseCache refresh failed.")