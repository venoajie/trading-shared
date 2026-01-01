# src/trading_shared/repositories/system_state_repository.py

# --- Built Ins ---
from typing import List, Any, Optional

# --- Installed ---
import orjson
from loguru import logger as log

# --- Shared Library Imports ---
from trading_shared.clients.redis_client import CustomRedisClient


class SystemStateRepository:
    """Manages the reading and writing of system-level state in Redis."""

    def __init__(self, redis_client: CustomRedisClient):
        self.redis = redis_client

    async def set_active_universe(
        self, key: str, universe_data: List[Any], ttl_seconds: int
    ):
        """
        Sets the canonical trading universe state.
        """
        try:
            # Serialized to a JSON string (bytes) before setting.
            payload = orjson.dumps(universe_data)
            await self.redis.set(key, payload, ex=ttl_seconds)
            # --- HOTFIX APPLIED ---
            # The line below was removed as self.redis is a wrapper without a direct .connection_pool attribute.
            # This prevents a runtime error if logging is enabled at a higher level.
            # log.debug(
            #     f"Set universe state for key '{key}' with {len(universe_data)} instruments. "
            #     f"(Redis DB: {self.redis.connection_pool.connection_kwargs.get('db', 'unknown')})"
            # )
        except Exception:
            log.exception(
                f"Failed to set universe state. "
                f"Attempted to write to key '{key}' with data of type '{type(universe_data).__name__}'."
            )

    async def get_active_universe(self, key: str) -> List[Any]:
        """
        Gets the canonical trading universe from a specified Redis key.
        Returns: A list of dictionary objects, or an empty list on failure.
        """
        try:
            payload = await self.redis.get(key)
            if not payload:
                # --- HOTFIX APPLIED ---
                # The line causing the crash has been removed. The log message is preserved without the problematic attribute access.
                # db_index = self.redis.connection_pool.connection_kwargs.get('db', 'unknown')
                log.warning(
                    f"Universe state key '{key}' not found or is empty in Redis. "
                    "Analyzer may be isolated from Strategist."
                )
                return []
            return orjson.loads(payload)
        except Exception as e:
            # Differentiate between connection errors, missing keys, and parsing errors
            if "WRONGTYPE" in str(e):
                log.error(
                    f"Data Type Collision on key '{key}'. Expected STRING, found other."
                )
            else:
                log.exception(
                    f"Failed to get or parse universe state from key '{key}'."
                )
            return []
