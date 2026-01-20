# src/trading_shared/trading_shared/cache/universe_cache.py

from typing import Dict, Optional, List, Any
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

    Reliability:
    - Handles List vs Dict input formats robustly.
    - Merges Spotlight overrides dynamically.
    - Thread-safe atomic updates.
    """

    def __init__(self, redis_client: CustomRedisClient, universe_key: str):
        self._redis = redis_client
        self.universe_key = universe_key
        self.override_key = "system:map:strategist:overrides"

        # Local Memory Caches
        self._instrument_map: Dict[str, Dict] = {}
        self._overrides: Dict[str, str] = {}
        self._raw_to_canonical_map: Dict[str, str] = {}

    async def refresh(self):
        """Refreshes standard universe and dynamic spotlight overrides."""
        try:
            # 1. Load Standard Universe (Base Layer)
            data = await self._redis.get(self.universe_key)
            new_map = {}

            if data:
                raw_universe = orjson.loads(data)

                # [SAFETY] Handle List vs Dict ambiguity
                if isinstance(raw_universe, list):
                    for item in raw_universe:
                        # Resilient Key Extraction
                        key = item.get("instrument_name") or item.get("symbol")
                        if key:
                            new_map[key] = item
                elif isinstance(raw_universe, dict):
                    new_map = raw_universe

            # Atomic Assignment (Thread Safety)
            self._instrument_map = new_map

            # 2. Load Spotlight Overrides (Dynamic Layer)
            overrides_data = await self._redis.hgetall(self.override_key)
            if overrides_data:
                self._overrides = {k.decode(): v.decode() for k, v in overrides_data.items()}
            else:
                self._overrides = {}

            # 3. Rebuild O(1) Lookup Map for Distributor
            self._rebuild_canonical_map()

        except Exception as e:
            log.error(f"UniverseCache refresh failed: {e}")

    def _rebuild_canonical_map(self):
        """Rebuilds map used by Distributor for symbol normalization."""
        mapping = {}
        for name in self._instrument_map:
            # Normalization: "BTC-USDT" -> "BTCUSDT"
            # Used by StreamProcessor to match API streams to internal keys
            raw = name.replace("-", "").replace("_", "").upper()
            mapping[raw] = name
        self._raw_to_canonical_map = mapping

    async def get_storage_mode(self, instrument_name: str) -> StorageMode:
        """
        Determines storage mode.
        Priority: Override (Spotlight) > Standard Config > Ephemeral Default
        """
        # 1. Check Spotlight
        if instrument_name in self._overrides:
            return StorageMode.PERSISTENT

        # 2. Check Base Config
        instrument_data = self._instrument_map.get(instrument_name)
        if instrument_data:
            return StorageMode(instrument_data.get("storage_mode", StorageMode.EPHEMERAL.value))

        return StorageMode.EPHEMERAL

    def get_all_instruments(self) -> List[Dict]:
        """
        Returns flat list for Analyzer loops.
        Merges Base Config with Spotlight Overrides.
        """
        results = []
        for name, data in self._instrument_map.items():
            # Lightweight copy
            item = data.copy()

            # [CRITICAL] Apply Spotlight Logic
            # If asset is in overrides, force it to PERSISTENT
            if name in self._overrides:
                item["storage_mode"] = StorageMode.PERSISTENT.value

            results.append(item)

        return results

    @property
    def _raw_to_canonical(self) -> Dict[str, str]:
        """Accessor for Distributor stream_processor."""
        return self._raw_to_canonical_map
