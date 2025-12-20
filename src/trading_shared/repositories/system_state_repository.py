# src/shared/trading_shared/repositories/system_state_repository.py

from typing import List
from loguru import logger as log
from trading_shared.clients.redis_client import CustomRedisClient

class SystemStateRepository:
    """
    Manages the reading and writing of system-level state and coordination keys in Redis.
    This includes target sets for services, global flags, and other cross-service data.
    """
    
    # Define keys as constants to prevent magic strings and ensure consistency
    ANALYZER_TARGETS_KEY = "system:universe:analyzer_targets"

    def __init__(self, redis_client: CustomRedisClient):
        self.redis = redis_client

    async def publish_analyzer_targets(self, symbols: List[str]):
        """
        Atomically overwrites the set of symbols for the Analyzer service to track.

        Args:
            symbols: A list of instrument names (e.g., ['BTCUSDT', 'ETHUSDT']).
        """
        if not symbols:
            log.warning("Attempted to publish an empty target list for analyzer. Clearing key.")
            await self.redis.delete(self.ANALYZER_TARGETS_KEY)
            return

        try:
            # The pipeline ensures the delete and sadd operations are atomic.
            async with await self.redis.pipeline(transaction=True) as pipe:
                pipe.delete(self.ANALYZER_TARGETS_KEY)
                pipe.sadd(self.ANALYZER_TARGETS_KEY, *symbols)
                await pipe.execute()
            
            log.info(f"Published {len(symbols)} symbols to analyzer target set '{self.ANALYZER_TARGETS_KEY}'.")
        
        except Exception as e:
            log.error(f"Failed to publish analyzer target set: {e}")