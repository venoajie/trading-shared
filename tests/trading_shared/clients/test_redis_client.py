# tests/trading_shared/clients/test_redis_client.py

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import redis.asyncio as aioredis
from pydantic import SecretStr
from redis.exceptions import ConnectionError as RedisConnectionError

from trading_shared.clients.redis_client import CustomRedisClient
from trading_shared.config.models import RedisSettings


@pytest.fixture
def redis_settings():
    """Provides a default RedisSettings instance for tests."""
    return RedisSettings(
        url="redis://localhost",
        db=0,
        password=SecretStr("testpass"),
        max_retries=2,
        initial_retry_delay_s=0.01,
    )


@pytest.fixture
def mock_aioredis(mocker):
    """Mocks the redis.asyncio.Redis client object."""
    mock_redis = MagicMock(spec=aioredis.Redis)
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.close = AsyncMock()
    mock_redis.get = AsyncMock(return_value=b'{"key":"value"}')
    mock_redis.set = AsyncMock()
    mock_redis.hgetall = AsyncMock(return_value={b"field": b"value"})
    mock_redis.hset = AsyncMock()
    mock_redis.xack = AsyncMock()
    mock_redis.xreadgroup = AsyncMock(return_value=[(b"test:stream", [(b"123-0", {b"data": b'{"val": 1}'})])])

    mock_pipeline = MagicMock(spec=aioredis.client.Pipeline)
    mock_pipeline.execute = AsyncMock()
    mock_pipeline.xadd = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

    return mock_redis


@pytest.mark.asyncio
class TestCustomRedisClient:
    """Unit tests for the CustomRedisClient."""

    async def test_get_client_creates_instance(self, redis_settings, mocker, mock_aioredis):
        # Arrange
        mock_from_url = mocker.patch("redis.asyncio.from_url", return_value=mock_aioredis)
        client = CustomRedisClient(redis_settings)

        # Act
        redis_conn = await client._get_client()

        # Assert
        mock_from_url.assert_called_once_with(
            "redis://localhost",
            password="testpass",
            db=0,
            socket_connect_timeout=2,
            decode_responses=False,
        )
        mock_aioredis.ping.assert_awaited_once()
        assert redis_conn == mock_aioredis

    # --- START: FIX FOR REDIS RESILIENCY TESTS ---
    async def test_execute_resiliently_retries_on_connection_error(self, redis_settings, mocker, mock_aioredis):
        # Arrange
        mock_from_url = mocker.patch(
            "redis.asyncio.from_url",
            side_effect=[RedisConnectionError, mock_aioredis],
        )
        mocker.patch("asyncio.sleep", new_callable=AsyncMock)
        client = CustomRedisClient(redis_settings)

        # Act
        result = await client.get("some_key")

        # Assert
        assert mock_from_url.call_count == 2
        assert asyncio.sleep.call_count == 1
        assert result == b'{"key":"value"}'

    async def test_execute_resiliently_fails_after_max_retries(self, redis_settings, mocker):
        # Arrange
        mocker.patch("redis.asyncio.from_url", side_effect=RedisConnectionError)
        mocker.patch("asyncio.sleep", new_callable=AsyncMock)
        client = CustomRedisClient(redis_settings)

        # Act & Assert
        # FIX: Assert the correct, more descriptive error message from the client.
        expected_error_msg = "Failed to execute Redis command 'GET some_key' after retries."
        with pytest.raises(ConnectionError, match=expected_error_msg):
            await client.get("some_key")

        assert mocker.patch("redis.asyncio.from_url").call_count == 2
        assert asyncio.sleep.call_count == 1

    # --- END: FIX FOR REDIS RESILIENCY TESTS ---

    async def test_xadd_bulk_chunks_messages(self, redis_settings, mocker, mock_aioredis):
        # Arrange
        mocker.patch("redis.asyncio.from_url", return_value=mock_aioredis)
        client = CustomRedisClient(redis_settings)
        messages = [{"key": i} for i in range(501)]

        # Act
        await client.xadd_bulk("test:stream", messages)

        # Assert
        mock_pipeline = mock_aioredis.pipeline.return_value
        assert mock_pipeline.execute.await_count == 2
        assert mock_pipeline.xadd.call_count == 501

    async def test_xadd_bulk_moves_to_dlq_on_final_failure(self, redis_settings, mocker):
        # Arrange
        mocker.patch("redis.asyncio.from_url", side_effect=RedisConnectionError)
        mocker.patch("asyncio.sleep", new_callable=AsyncMock)
        client = CustomRedisClient(redis_settings)
        mock_xadd_to_dlq = mocker.patch.object(client, "xadd_to_dlq", new_callable=AsyncMock)
        messages = [{"key": 1}]

        # Act & Assert
        with pytest.raises(ConnectionError):
            await client.xadd_bulk("market:stream:test", messages)

        mock_xadd_to_dlq.assert_awaited_once_with("market:stream:test", messages)

    def test_xadd_to_dlq_constructs_correct_name(self, redis_settings, mocker):
        # Arrange
        client = CustomRedisClient(redis_settings)
        mocker.patch.object(client, "execute_resiliently", new_callable=AsyncMock)

        # Act
        asyncio.run(client.xadd_to_dlq("market:stream:binance:trades", [{"key": 1}]))

        # Assert
        call_args = client.execute_resiliently.call_args
        log_message = call_args[0][1]
        assert "deadletter:queue:market:stream" in log_message

    async def test_read_stream_messages_parses_response(self, redis_settings, mocker, mock_aioredis):
        # Arrange
        mocker.patch("redis.asyncio.from_url", return_value=mock_aioredis)
        client = CustomRedisClient(redis_settings)

        # Act
        messages = await client.read_stream_messages("test:stream", "group", "consumer")

        # Assert
        assert messages == [(b"123-0", {b"data": b'{"val": 1}'})]

    async def test_read_stream_messages_handles_empty_response(self, redis_settings, mocker, mock_aioredis):
        # Arrange
        mock_aioredis.xreadgroup = AsyncMock(return_value=[])
        mocker.patch("redis.asyncio.from_url", return_value=mock_aioredis)
        client = CustomRedisClient(redis_settings)

        # Act
        messages = await client.read_stream_messages("test:stream", "group", "consumer")

        # Assert
        assert messages == []
