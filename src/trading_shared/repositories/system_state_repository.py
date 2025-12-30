# src/trading_shared/repositories/system_state_repository.py

# --- Built Ins ---
from typing import List, Any

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

        Args:
            key: The specific Redis key to write to.
            universe_data: A list of dictionary objects representing the universe.
            ttl_seconds: The time-to-live for the Redis key.
        """
        try:
            # Serialized to a JSON string (bytes) before setting.
            payload = orjson.dumps(universe_data)
            await self.redis.set(key, payload, ex=ttl_seconds)
            log.debug(
                f"Set universe state for key '{key}' with {len(universe_data)} instruments."
            )
        except Exception:
            log.exception(
                f"Failed to set universe state. "
                f"Attempted to write to key '{key}' with data of type '{type(universe_data).__name__}'."
            )

    async def get_active_universe(self, key: str) -> List[Any]:
        """
        Gets the canonical trading universe from a specified Redis key.

        Returns:
            A list of dictionary objects, or an empty list on failure.
        """
        try:
            payload = await self.redis.get(key)
            if not payload:
                log.warning(f"Universe state key '{key}' not found or is empty.")
                return []
            return orjson.loads(payload)
        except Exception:
            log.exception(f"Failed to get or parse universe state from key '{key}'.")
            return []
