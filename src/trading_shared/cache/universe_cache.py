# src/trading_shared/trading_shared/cache/universe_cache.py

import asyncio
from typing import Any

import orjson
from loguru import logger as log

from trading_shared.clients.redis_client import CustomRedisClient
from trading_shared.core.models import StorageMode


class UniverseCache:
    """
    In-memory cache of the active universe, including storage tiering.
    Synchronizes with the 'system:state:janitor:active_ledger' Redis key.
    """

    def __init__(self, redis_client: CustomRedisClient, universe_key: str):
        self._redis = redis_client
        self._universe_key = universe_key

        self._raw_to_canonical: dict[str, str] = {}
        self._storage_cache: dict[str, StorageMode] = {}
        self._instrument_list: list[dict[str, Any]] = []

        self._lock = asyncio.Lock()

    def get_canonical_name(self, raw_symbol: str) -> str | None:
        if not raw_symbol:
            return None
        # Normalization: STRIP -> REMOVE '-'/'_' -> UPPER
        lookup_key = raw_symbol.strip().replace("-", "").replace("_", "").upper()
        return self._raw_to_canonical.get(lookup_key)

    def get_all_instruments(self) -> list[dict[str, Any]]:
        return self._instrument_list

    async def get_storage_mode(self, instrument_name: str) -> StorageMode:
        """Returns storage persistence preference for an instrument."""
        async with self._lock:
            # Default to EPHEMERAL to prevent accidental data bloat
            return self._storage_cache.get(instrument_name, StorageMode.EPHEMERAL)

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
                name = entry.get("instrument_name") or entry.get("symbol")
                if not name:
                    continue

                # 1. Build List for Iteration
                new_list.append(entry)

                # 2. Build Normalization Map (Bidirectional robustness)
                # Key: BTCUSDT -> Value: BTC-USDT
                raw_key = name.replace("-", "").replace("_", "").upper()
                new_canonical[raw_key] = name
                # Key: BTC-USDT -> Value: BTC-USDT (Self-reference)
                new_canonical[name.upper()] = name

                # 3. Build Storage Map
                tier_str = entry.get("storage_tier", "EPHEMERAL").upper()
                new_storage[name] = StorageMode[tier_str]

            async with self._lock:
                self._storage_cache = new_storage
                self._raw_to_canonical = new_canonical
                self._instrument_list = new_list

            log.info(f"UniverseCache refreshed. {len(new_list)} instruments loaded.")
            # Diagnostic log to verify mapping
            sample_keys = list(new_canonical.keys())[:5]
            log.debug(f"UniverseCache Sample Keys: {sample_keys}")

        except Exception as e:
            log.exception(f"UniverseCache refresh failed: {e}")
