# tests/trading_shared/repositories/test_system_state_repository.py

from unittest.mock import AsyncMock, MagicMock

import orjson
import pytest

from trading_shared.repositories.system_state_repository import SystemStateRepository


@pytest.fixture
def mock_redis_client():
    """Provides a mock CustomRedisClient instance."""
    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock()
    return client


@pytest.fixture
def system_state_repo(mock_redis_client):
    """Provides a SystemStateRepository with a mocked dependency."""
    return SystemStateRepository(mock_redis_client)


@pytest.mark.asyncio
class TestSystemStateRepository:
    async def test_set_active_universe_serializes_and_calls_redis(
        self, system_state_repo, mock_redis_client
    ):
        # Arrange
        key = "system:state:test:universe"
        universe_data = [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]
        ttl = 300
        expected_payload = orjson.dumps(universe_data)

        # Act
        await system_state_repo.set_active_universe(key, universe_data, ttl)

        # Assert
        mock_redis_client.set.assert_awaited_once_with(key, expected_payload, ex=ttl)

    async def test_get_active_universe_deserializes_correctly(
        self, system_state_repo, mock_redis_client
    ):
        # Arrange
        key = "system:state:test:universe"
        expected_universe = [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]
        payload = orjson.dumps(expected_universe)
        mock_redis_client.get.return_value = payload

        # Act
        result = await system_state_repo.get_active_universe(key)

        # Assert
        mock_redis_client.get.assert_awaited_once_with(key)
        assert result == expected_universe

    async def test_get_active_universe_returns_empty_list_if_key_not_found(
        self, system_state_repo, mock_redis_client
    ):
        # Arrange
        key = "system:state:test:universe"
        mock_redis_client.get.return_value = None  # Key does not exist

        # Act
        result = await system_state_repo.get_active_universe(key)

        # Assert
        assert result == []

    async def test_get_active_universe_returns_empty_list_on_json_error(
        self, system_state_repo, mock_redis_client
    ):
        # Arrange
        key = "system:state:test:universe"
        invalid_payload = b"not-valid-json"
        mock_redis_client.get.return_value = invalid_payload

        # Act
        result = await system_state_repo.get_active_universe(key)

        # Assert
        assert result == []
