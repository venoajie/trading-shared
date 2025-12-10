# src/trading_shared/repositories/ohlc_queue_repository.py

# --- Built Ins ---
from typing import Any

# --- Installed ---
import orjson
from loguru import logger as log

# --- Shared Library Imports ---
from trading_shared.clients.redis_client import CustomRedisClient


class OhlcWorkQueueRepository:
    """
    Manages interaction with the Redis-based work queue for OHLC backfilling.
    This class encapsulates domain-specific logic, using a generic Redis client.
    """

    _WORK_QUEUE_KEY = "queue:ohlc_work"
    _FAILED_QUEUE_KEY = "dlq:ohlc_work"

    def __init__(self, redis_client: CustomRedisClient):
        self._redis = redis_client

    async def clear_queue(self):
        """Clears the primary work queue."""
        await self._redis.delete(self._WORK_QUEUE_KEY)
        log.info(f"Cleared Redis queue: {self._WORK_QUEUE_KEY}")

    async def enqueue_work(
        self,
        work_item: dict[str, Any],
    ):
        """Adds a new work item to the queue."""
        await self._redis.lpush(self._WORK_QUEUE_KEY, orjson.dumps(work_item))

    async def enqueue_failed_work(
        self,
        work_item: dict[str, Any],
    ):
        """Moves a failed work item to the Dead Letter Queue."""
        try:
            await self._redis.lpush(self._FAILED_QUEUE_KEY, orjson.dumps(work_item))
            log.error(f"Moved failed OHLC work item to DLQ: {work_item}")
        except Exception as e:
            log.critical(
                f"CRITICAL: Failed to enqueue to DLQ. Item lost: {work_item}. Error: {e}"
            )

    async def dequeue_work(self) -> dict[str, Any] | None:
        """Blocks and waits for a work item from the queue."""
        try:
            result = await self._redis.brpop(self._WORK_QUEUE_KEY, timeout=5)
            if result:
                return orjson.loads(result[1])
            return None
        except ConnectionError:
            log.warning("Redis connection issue during dequeue, returning None.")
            return None
        except Exception as e:
            log.error(f"Unexpected error during OHLC work dequeue: {e}")
            return None

    async def get_queue_size(self) -> int:
        """Returns the current number of items in the work queue."""
        try:
            return await self._redis.llen(self._WORK_QUEUE_KEY)
        except ConnectionError:
            log.error("Failed to get OHLC work queue size due to connection error.")
            return 0
