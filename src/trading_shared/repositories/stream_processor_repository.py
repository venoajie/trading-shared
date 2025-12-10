# src/trading_shared/repositories/stream_processor_repository.py

# --- Built Ins ---
from typing import List, Dict, Any
from datetime import datetime, timezone

# --- Installed  ---
from loguru import logger as log
import orjson
import redis.asyncio as aioredis

# --- Shared Library Imports ---
from trading_shared.clients.redis_client import CustomRedisClient


class StreamProcessorRepository:
    """
    Manages the consumption and lifecycle of messages from a Redis stream consumer group.
    """

    def __init__(self, redis_client: CustomRedisClient):
        self._redis = redis_client

    async def ensure_consumer_group(
        self,
        stream_name: str,
        group_name: str,
    ):
        """Ensures a consumer group exists for a given stream."""
        await self._redis.ensure_consumer_group(stream_name, group_name)

    async def read_messages(
        self,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        count: int = 250,
        block: int = 2000,
    ) -> List:
        """Reads a batch of messages from a consumer group."""
        return await self._redis.read_stream_messages(
            stream_name=stream_name,
            group_name=group_name,
            consumer_name=consumer_name,
            count=count,
            block=block,
        )

    async def acknowledge_messages(
        self,
        stream_name: str,
        group_name: str,
        message_ids: List[str],
    ):
        """Acknowledges one or more messages in a consumer group."""
        if not message_ids:
            return
        await self._redis.acknowledge_message(stream_name, group_name, *message_ids)

    async def claim_stale_messages(
        self,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        min_idle_time_ms: int,
        count: int = 100,
    ) -> tuple[bytes, list]:
        """Claims stale pending messages from other consumers."""
        return await self._redis.xautoclaim_stale_messages(
            stream_name, group_name, consumer_name, min_idle_time_ms, count
        )

    async def publish_state_change(
        self,
        channel_name: str,
    ):
        """Publishes a generic state change notification to a specified channel."""
        await self._redis.publish(channel_name, "{}")

    async def move_to_dlq(
        self,
        stream_name: str,
        failed_messages: List[Dict[str, Any]],
    ):
        """Moves a list of failed messages to the DLQ stream."""
        await self._redis.xadd_to_dlq(stream_name, failed_messages)

    def parse_stream_message(
        self,
        message_data: dict[bytes, bytes],
    ) -> dict:
        """Helper method to parse raw stream message data."""
        return self._redis.parse_stream_message(message_data)

    async def move_message_to_dlq_and_ack(
        self,
        source_stream: str,
        source_group: str,
        message_id: str,
        message_data: dict,
        error: str,
    ):
        """
        Atomically moves a single failed message's contents to a DLQ stream
        and ACKs the original message to prevent reprocessing.
        """
        dlq_stream = f"dlq:{source_stream}"
        log.warning(
            f"Moving failed message {message_id} from '{source_stream}' to DLQ '{dlq_stream}'"
        )
        failed_message_payload = {
            "original_message_id": message_id,
            "original_stream": source_stream,
            "error": error,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                k.decode("utf-8"): v.decode("utf-8") for k, v in message_data.items()
            },
        }

        async def command(pool: aioredis.Redis):
            pipe = pool.pipeline()
            pipe.xadd(dlq_stream, {"payload": orjson.dumps(failed_message_payload)})
            pipe.xack(source_stream, source_group, message_id)
            await pipe.execute()

        # Accessing the "private" _execute_resiliently is a pragmatic choice here
        # to ensure this critical operation has the same resilience as direct client calls.
        await self._redis._execute_resiliently(command, "move_to_dlq_and_ack")

    async def enqueue_malformed_trade(self, trade_data: Dict):
        """Pushes a trade that failed processing to a dead-letter queue."""
        dlq_key = "dlq:malformed_trades"
        log.critical(f"Moving malformed trade to DLQ '{dlq_key}': {trade_data}")
        await self._redis.lpush(dlq_key, orjson.dumps(trade_data))
