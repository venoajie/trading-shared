# src/trading_shared/repositories/system_state_repository.py

# --- Built Ins ---
from typing import Any

# --- Installed ---
import orjson
from loguru import logger as log

# --- Shared Library Imports ---
from trading_shared.clients.redis_client import CustomRedisClient


class SystemStateRepository:
    """Manages the reading and writing of system-level state in Redis."""

    def __init__(self, redis_client: CustomRedisClient):
        self.redis = redis_client

    async def set_active_universe(self, key: str, universe_data: list[Any], ttl_seconds: int):
        """
        Sets the canonical trading universe state.
        """
        try:
            # Serialized to a JSON string (bytes) before setting.
            payload = orjson.dumps(universe_data)
            await self.redis.set(key, payload, ex=ttl_seconds)

        except Exception:
            log.exception(f"Failed to set universe state. Attempted to write to key '{key}' with data of type '{type(universe_data).__name__}'.")

    async def set_active_ledger(self, key: str, ledger_data: list[Any], ttl_seconds: int):
        """
        Sets the canonical instrument ledger state. This is an alias for
        set_active_universe to provide semantic clarity.
        """
        log.info(f"Publishing active ledger with {len(ledger_data)} instruments to Redis key '{key}'.")
        # This method simply calls the existing, tested method.
        await self.set_active_universe(key, ledger_data, ttl_seconds)

    async def get_active_universe(self, key: str) -> list[Any]:
        """
        Gets the canonical trading universe from a specified Redis key.
        Returns: A list of dictionary objects, or an empty list on failure.
        """
        try:
            payload = await self.redis.get(key)
            if not payload:
                log.warning(f"Universe state key '{key}' not found or is empty in Redis.")
                return []
            return orjson.loads(payload)
        except Exception as e:
            if "WRONGTYPE" in str(e):
                log.error(f"Data Type Collision on key '{key}'. Expected STRING, found other.")
            else:
                log.exception(f"Failed to get or parse universe state from key '{key}'.")
            return []
