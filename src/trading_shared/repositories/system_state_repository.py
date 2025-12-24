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
    This includes target sets for services, global flags, and other cross-service data.
    """

    # Define keys as constants to prevent magic strings and ensure consistency
    ANALYZER_TARGETS_KEY = "system:universe:analyzer_targets"

    def __init__(self, redis_client: CustomRedisClient):
        self.redis = redis_client

    async def set_active_universe(self, symbols: List[str]):
        """
        [NEW] Sets the canonical list of active instruments in the trading universe.
        This writes the state to a durable Redis key for polling by consumers.
        
        Args:
            symbols: A list of instrument symbol strings.
        """
        try:
            payload = orjson.dumps(symbols)
            await self.redis.set(UNIVERSE_STATE_KEY, payload, ex=UNIVERSE_STATE_TTL_SECONDS)
            log.debug(f"Set canonical universe state key '{UNIVERSE_STATE_KEY}' with {len(symbols)} symbols.")
        except Exception:
            log.exception(
                f"Failed to set active universe state in Redis key '{UNIVERSE_STATE_KEY}'."
            )
            # Depending on system criticality, you might want to raise this exception.
            # For now, logging is sufficient.

    async def get_active_universe(self) -> List[str]:
        """
        [NEW] Gets the canonical list of active instruments from the trading universe state key.
        This allows services to poll for the current state in a decoupled manner.
        
        Returns:
            A list of instrument symbol strings, or an empty list if the state
            is not set or an error occurs.
        """
        try:
            payload = await self.redis.get(UNIVERSE_STATE_KEY)
            if not payload:
                log.warning(f"Universe state key '{UNIVERSE_STATE_KEY}' not found or is empty.")
                return []
            
            return orjson.loads(payload)
        except Exception:
            log.exception(
                f"Failed to get or parse active universe state from Redis key '{UNIVERSE_STATE_KEY}'."
            )
            return []


    async def publish_analyzer_targets(self, symbols: List[str]):
        """
        Atomically overwrites the set of symbols for the Analyzer service to track.

        Args:
            symbols: A list of instrument names (e.g., ['BTCUSDT', 'ETHUSDT']).
        """
        if not symbols:
            log.warning(
                "Attempted to publish an empty target list for analyzer. Clearing key."
            )
            await self.redis.delete(self.ANALYZER_TARGETS_KEY)
            return

        try:
            # The pipeline ensures the delete and sadd operations are atomic.
            async with await self.redis.pipeline(transaction=True) as pipe:
                pipe.delete(self.ANALYZER_TARGETS_KEY)
                pipe.sadd(self.ANALYZER_TARGETS_KEY, *symbols)
                await pipe.execute()

            log.info(
                f"Published {len(symbols)} symbols to analyzer target set '{self.ANALYZER_TARGETS_KEY}'."
            )

        except Exception as e:
            log.error(f"Failed to publish analyzer target set: {e}")
