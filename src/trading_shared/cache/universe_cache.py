# src/trading_shared/cache/universe_cache.py

import asyncio
from typing import Dict, List, Any, Optional
import orjson
from loguru import logger as log
from trading_engine_core.models import StorageMode
from trading_shared.clients.redis_client import CustomRedisClient

class UniverseCache:
    def __init__(self, redis_client: CustomRedisClient, universe_key: str):
        self._redis = redis_client
        self._universe_key = universe_key
        self._canonical_map: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        log.info("UniverseCache (Strict, Shared Library v7.0) initialized.")

    def get_canonical_name(self, raw_symbol: str) -> Optional[str]:
        clean_raw = raw_symbol.strip().replace("-", "").upper()
        return self._canonical_map.get(clean_raw)

    async def refresh(self):
        try:
            raw_ledger_bytes = await self._redis.get(self._universe_key)
            if not raw_ledger_bytes: return
            data = orjson.loads(raw_ledger_bytes)
            new_canonical = {}
            for entry in data:
                name = entry.get("symbol") or entry.get("instrument_name")
                if not name: continue
                raw_key = name.replace("-", "").replace("_", "").upper()
                new_canonical[raw_key] = name
            async with self._lock: self._canonical_map = new_canonical
            log.info(f"UniverseCache refreshed. {len(new_canonical)} symbols mapped.")
        except Exception: log.exception("UniverseCache refresh failed.")