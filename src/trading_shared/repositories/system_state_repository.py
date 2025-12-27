# src/shared/trading_shared/repositories/system_state_repository.py

# --- Built Ins ---
from typing import List

# --- Installed ---
import orjson
from loguru import logger as log

# --- Shared Library Imports ---
from trading_shared.clients.redis_client import CustomRedisClient


class SystemStateRepository:
    """Manages the reading and writing of system-level state in Redis."""

    def __init__(self, redis_client: CustomRedisClient):
        self.redis = redis_client

    async def set_active_universe(self, key: str, symbols: List[str], ttl_seconds: int):
        """
        Sets the canonical list of active instruments in the trading universe.

        Args:
            key: The specific Redis key to write to.
            symbols: A list of instrument symbol strings.
            ttl_seconds: The time-to-live for the Redis key.
        """
        try:
            payload = orjson.dumps(symbols)
            await self.redis.set(key, payload, ex=ttl_seconds)
            log.debug(
                f"Set universe state for key '{key}' with {len(symbols)} symbols."
            )
        except Exception:
            log.exception(f"Failed to set active universe state for key '{key}'.")

    async def get_active_universe(self, key: str) -> List[str]:
        """
        Gets the canonical list of active instruments from a specified Redis key.

        Args:
            key: The specific Redis key to read from.

        Returns:
            A list of instrument symbols, or an empty list on failure.
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
