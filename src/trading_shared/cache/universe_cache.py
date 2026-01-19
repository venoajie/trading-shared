# src/trading_shared/trading_shared/cache/universe_cache.py

import orjson
from loguru import logger as log

from trading_shared.clients.redis_client import CustomRedisClient
from trading_shared.core.enums import StorageMode


class UniverseCache:
    """
    A unified, multi-layered cache for the active trading universe.

    Layers:
    1. Base Layer: The static universe definition (from Janitor/Config).
    2. Spotlight Layer: Dynamic overrides (promotions) from Strategist.

    This ensures that when an asset is promoted to PERSISTENT, all consumers
    (Distributor, Analyzer) immediately respect the new storage mode.
    """

    def __init__(self, redis_client: CustomRedisClient, universe_key: str):
        self._redis = redis_client
        self.universe_key = universe_key
        # [NEW] The "Spotlight" Key defined in DATA_CONTRACTS.md
        self.override_key = "system:map:strategist:overrides"

        # Local Memory Caches
        self._instrument_map: dict[str, dict] = {}
        self._overrides: dict[str, str] = {}
        # Pre-computed map for Distributor's fast lookup
        self._raw_to_canonical_map: dict[str, str] = {}

    async def refresh(self):
        """
        Refreshes both the standard universe and the dynamic overrides from Redis.
        """
        try:
            # 1. Load Standard Universe (The "Base" Layer)
            data = await self._redis.get(self.universe_key)
            if data:
                self._instrument_map = orjson.loads(data)

            # 2. Load Overrides (The "Spotlight" Layer)
            # We fetch all currently active promotions
            overrides_data = await self._redis.hgetall(self.override_key)
            if overrides_data:
                self._overrides = {k.decode(): v.decode() for k, v in overrides_data.items()}
            else:
                self._overrides = {}

            # 3. Rebuild the optimized map
            self._rebuild_canonical_map()

        except Exception as e:
            log.error(f"UniverseCache refresh failed: {e}")

    def _rebuild_canonical_map(self):
        """Rebuilds the map used by Distributor for O(1) symbol normalization."""
        mapping = {}
        # [FIX] Iterate over keys directly to resolve B007 linter error.
        for name in self._instrument_map:
            # Logic: "BTC-USDT" -> "BTCUSDT"
            raw = name.replace("-", "").replace("_", "").upper()
            mapping[raw] = name
        self._raw_to_canonical_map = mapping

    async def get_storage_mode(self, instrument_name: str) -> StorageMode:
        """
        Determines storage mode for an asset.
        Priority: Override (Spotlight) > Standard Config
        """
        # 1. Check Spotlight (Dynamic Promotion)
        if instrument_name in self._overrides:
            # If the key exists in the override map, it is strictly PERSISTENT
            return StorageMode.PERSISTENT

        # 2. Check Standard Config (Base Layer)
        instrument_data = self._instrument_map.get(instrument_name)
        if instrument_data:
            # Default to EPHEMERAL if not specified
            return StorageMode(instrument_data.get("storage_mode", StorageMode.EPHEMERAL.value))

        return StorageMode.EPHEMERAL

    def get_all_instruments(self) -> list[dict]:
        """
        Returns flat list of instruments.
        Injected logic ensures 'storage_mode' reflects the override.
        Used by Analyzer to know what to analyze.
        """
        results = []
        for name, data in self._instrument_map.items():
            # Create a lightweight copy to avoid mutating the cache
            item = data.copy()

            # Apply Spotlight Logic
            if name in self._overrides:
                item["storage_mode"] = StorageMode.PERSISTENT.value

            results.append(item)
        return results

    @property
    def _raw_to_canonical(self) -> dict[str, str]:
        """
        Accessor for the Distributor's normalization map.
        """
        return self._raw_to_canonical_map
