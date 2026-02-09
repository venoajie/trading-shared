# src/trading_shared/trading_shared/cache/universe_cache.py

from typing import Any

import orjson
from loguru import logger as log

from trading_shared.clients.redis_client import CustomRedisClient
from trading_shared.core.enums import StorageMode


class UniverseCache:
    """
    A unified, multi-layered cache for the active trading universe.

    Layers:
    1. Base Layer: The static universe definition (from Janitor/Config).
    2. Spotlight Layer: Dynamic overrides (promotions) from Strategist/Receiver.
    """

    def __init__(self, redis_client: CustomRedisClient, universe_key: str):
        self._redis = redis_client
        self.universe_key = universe_key
        # Matches the key used in binance_movers.py
        self.override_key = "system:map:strategist:overrides"

        # Local Memory Caches
        self._instrument_map: dict[str, dict] = {}
        self._overrides: dict[str, Any] = {}  # Now stores the parsed payload
        self._raw_to_canonical_map: dict[str, str] = {}

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
                        key = item.get("instrument_name") or item.get("symbol")
                        if key:
                            new_map[key] = item
                elif isinstance(raw_universe, dict):
                    new_map = raw_universe

            # 2. Load Spotlight Overrides (Dynamic Layer)
            # The Receiver pushes RAW JSON payloads here
            overrides_data = await self._redis.hgetall(self.override_key)
            new_overrides = {}

            if overrides_data:
                for k, v in overrides_data.items():
                    try:
                        symbol = k.decode()
                        payload = orjson.loads(v)  # Decode the mover context
                        new_overrides[symbol] = payload
                    except Exception:
                        pass

            # Atomic Assignment
            self._instrument_map = new_map
            self._overrides = new_overrides

            # 3. Rebuild O(1) Lookup Map for Distributor
            self._rebuild_canonical_map()

        except Exception as e:
            log.error(f"UniverseCache refresh failed: {e}")

    def _rebuild_canonical_map(self):
        """Rebuilds map used by Distributor for symbol normalization."""
        mapping = {}
        # 1. Add Base Universe
        for name in self._instrument_map:
            raw = name.replace("-", "").replace("_", "").upper()
            mapping[raw] = name

        # 2. Add Spotlights (Ensure Distributor can route data for new movers)
        for name in self._overrides:
            raw = name.replace("-", "").replace("_", "").upper()
            if raw not in mapping:
                mapping[raw] = name

        self._raw_to_canonical_map = mapping

    async def get_storage_mode(self, instrument_name: str) -> StorageMode:
        """
        Determines storage mode.
        """
        # If it's in the base map, respect its config
        if instrument_name in self._instrument_map:
            base_mode = self._instrument_map[instrument_name].get("storage_mode")
            # If it's ALSO a mover, we might upgrade it, but usually we stick to base
            if instrument_name in self._overrides:
                return StorageMode.PERSISTENT
            return StorageMode(base_mode or StorageMode.EPHEMERAL.value)

        # If it's ONLY in overrides (a temporary mover), keep it EPHEMERAL
        # to avoid polluting the database with transient assets.
        if instrument_name in self._overrides:
            return StorageMode.EPHEMERAL

        return StorageMode.EPHEMERAL

    def get_all_instruments(self) -> list[dict]:
        """
        Returns flat list for Analyzer loops.
        Merges Base Config with Spotlight Overrides (Additive).
        """
        # 1. Start with Base Universe
        # We use a dict keyed by symbol to handle merges
        merged_map = {k: v.copy() for k, v in self._instrument_map.items()}

        # 2. Merge Spotlights
        for symbol, mover_payload in self._overrides.items():
            if symbol in merged_map:
                # EXISTING ASSET: Enrich with mover context
                merged_map[symbol]["is_mover"] = True
                merged_map[symbol]["mover_context"] = mover_payload
                merged_map[symbol]["storage_mode"] = StorageMode.PERSISTENT.value
            else:
                # NEW ASSET: Create transient definition
                # We need to parse base/quote for the system to work
                parts = symbol.split("-")
                base = parts[0] if len(parts) > 1 else symbol
                quote = parts[1] if len(parts) > 1 else "USDT"

                merged_map[symbol] = {
                    "instrument_name": symbol,
                    "symbol": symbol,
                    "exchange": "binance",  # Assumption: Movers are currently Binance only
                    "market_type": "spot",
                    "base_asset": base,
                    "quote_asset": quote,
                    "is_mover": True,
                    "mover_context": mover_payload,  # Crucial: Pass the metadata!
                    "storage_mode": StorageMode.EPHEMERAL.value,
                }

        return list(merged_map.values())

    @property
    def _raw_to_canonical(self) -> dict[str, str]:
        """Accessor for Distributor stream_processor."""
        return self._raw_to_canonical_map
