# src/trading_shared/cache/universe_cache.py

import asyncio
from typing import Dict, List, Any

import orjson
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
        log.info("UniverseCache (Patch v4.2 - Library Version) initialized.")

    async def get_storage_mode(self, instrument_name: str) -> StorageMode:
        """
        Returns the storage mode for an instrument.
        LEGACY SAFETY: Defaults to PERSISTENT (Postgres) if unknown.
        This prevents data loss during startup/race conditions.
        """
        async with self._lock:
            # Check exact match first
            if instrument_name in self._cache:
                return self._cache[instrument_name]

            # Fallback: Check normalized key (e.g., ETH-USDT -> ETHUSDT) if needed
            normalized = instrument_name.replace("-", "").replace("_", "")
            return self._cache.get(normalized, StorageMode.PERSISTENT)

    def get_all_instruments(self) -> List[Dict[str, Any]]:
        """
        Returns the full raw ledger.
        REQUIRED by Analyzer to iterate over the Broad universe.
        """
        return self._raw_ledger

    async def refresh(self):
        """Reloads the entire universe map from the canonical Redis key."""
        try:
            raw_ledger_bytes = await self._redis.get(self._universe_key)
            if not raw_ledger_bytes:
                log.warning(f"Active ledger key '{self._universe_key}' not found in Redis. Cache remains empty.")
                return

            try:
                data = orjson.loads(raw_ledger_bytes)
            except orjson.JSONDecodeError:
                log.error(f"Failed to decode ledger JSON from key '{self._universe_key}'.")
                return

            if not isinstance(data, list):
                log.error(f"Ledger data format invalid. Expected list, got {type(data)}.")
                return

            new_cache = {}
            processed_count = 0

            for entry in data:
                if not isinstance(entry, dict):
                    continue

                # [CRITICAL FIX] Support both 'symbol' (Janitor output) and 'instrument_name' (Model contract)
                name = entry.get("symbol") or entry.get("instrument_name") or entry.get("spot_symbol")

                # Logic: Check specific string "POSTGRES" to map to Enum, otherwise default to buffer
                mode_str = entry.get("storage_mode", "POSTGRES")  # Default to POSTGRES for safety
                mode = StorageMode.PERSISTENT if mode_str in ("POSTGRES", "PERSISTENT") else StorageMode.EPHEMERAL

                if name:
                    # Storing exact name as primary key
                    new_cache[name] = mode

                    # Also store normalized version for loose lookups
                    normalized_name = name.replace("-", "").replace("_", "")
                    if normalized_name != name:
                        new_cache[normalized_name] = mode

                    processed_count += 1

            async with self._lock:
                self._cache = new_cache
                self._raw_ledger = data

            if processed_count > 0:
                log.info(f"UniverseCache refreshed. Loaded {processed_count} instruments (Unique keys: {len(new_cache)}).")
            else:
                log.warning("UniverseCache refreshed but 0 valid instruments were found.")

        except Exception as e:
            log.exception(f"Unexpected error during UniverseCache refresh: {e}")
