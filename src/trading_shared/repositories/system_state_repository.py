# src/shared/trading_shared/repositories/system_state_repository.py

# --- Built Ins ---
from typing import List

# --- Installed ---
import orjson
from loguru import logger as log

# --- Shared Library Imports ---
from trading_shared.clients.redis_client import CustomRedisClient

# Define the single source of truth for the universe state key.
UNIVERSE_STATE_KEY = "system:universe:active_set"
UNIVERSE_STATE_TTL_SECONDS = 300  # 5 minutes


class SystemStateRepository:
    """
    Manages the reading and writing of system-level state and coordination keys in Redis.
    This includes the canonical active universe set for all services.
    """

    def __init__(self, redis_client: CustomRedisClient):
        self.redis = redis_client

    async def set_active_universe(self, symbols: List[str]):
        """
        Sets the canonical list of active instruments in the trading universe.
        This writes the state to a durable Redis key for polling by consumers.

        Args:
            symbols: A list of instrument symbol strings.
        """
        try:
            payload = orjson.dumps(symbols)
            await self.redis.set(
                UNIVERSE_STATE_KEY, payload, ex=UNIVERSE_STATE_TTL_SECONDS
            )
            log.debug(
                f"Set canonical universe state key '{UNIVERSE_STATE_KEY}' with {len(symbols)} symbols."
            )
        except Exception:
            log.exception(
                f"Failed to set active universe state in Redis key '{UNIVERSE_STATE_KEY}'."
            )

    async def get_active_universe(self) -> List[str]:
        """
        Gets the canonical list of active instruments from the trading universe state key.
        This allows services to poll for the current state in a decoupled manner.

        Returns:
            A list of instrument symbol strings, or an empty list if the state
            is not set or an error occurs.
        """
        try:
            payload = await self.redis.get(UNIVERSE_STATE_KEY)
            if not payload:
                log.warning(
                    f"Universe state key '{UNIVERSE_STATE_KEY}' not found or is empty."
                )
                return []

            return orjson.loads(payload)
        except Exception:
            log.exception(
                f"Failed to get or parse active universe state from Redis key '{UNIVERSE_STATE_KEY}'."
            )
            return []
