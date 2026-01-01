# src/trading_shared/repositories/stream_processor_repository.py

# --- Built Ins ---
from datetime import datetime, timezone
from typing import Any

import orjson
import redis.asyncio as aioredis

# --- Installed  ---
from loguru import logger as log

# --- Shared Library Imports ---
from trading_shared.clients.redis_client import CustomRedisClient


def _safe_decode(value: bytes) -> str | bytes:
    """Attempts to decode a byte string as UTF-8, returning raw bytes on failure."""
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value


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
    ) -> list:
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
        message_ids: list[str],
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
        return await self._redis.xautoclaim_stale_messages(stream_name, group_name, consumer_name, min_idle_time_ms, count)

    async def publish_state_change(
        self,
        channel_name: str,
    ):
        """Publishes a generic state change notification to a specified channel."""
        await self._redis.publish(channel_name, "{}")

    async def move_to_dlq(
        self,
        stream_name: str,
        failed_messages: list[dict[str, Any]],
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
        log.warning(f"Moving failed message {message_id} from '{source_stream}' to DLQ '{dlq_stream}'")

        # Perform safe decoding
        safely_decoded_payload = {_safe_decode(k): _safe_decode(v) for k, v in message_data.items()}

        failed_message_payload = {
            "original_message_id": message_id,
            "original_stream": source_stream,
            "error": error,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "payload": safely_decoded_payload,
        }

        async def command(pool: aioredis.Redis):
            pipe = pool.pipeline()
            pipe.xadd(dlq_stream, {"payload": orjson.dumps(failed_message_payload)})
            pipe.xack(source_stream, source_group, message_id)
            await pipe.execute()

        # Call the public method, not the private one.
        await self._redis.execute_resiliently(command, "move_to_dlq_and_ack")

    async def enqueue_malformed_trade(self, trade_data: dict):
        """Pushes a trade that failed processing to a dead-letter queue."""
        dlq_key = "dlq:malformed_trades"
        log.critical(f"Moving malformed trade to DLQ '{dlq_key}': {trade_data}")
        await self._redis.lpush(dlq_key, orjson.dumps(trade_data))
