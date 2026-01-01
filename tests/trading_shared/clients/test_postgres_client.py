# tests/trading_shared/clients/test_postgres_client.py

import asyncio
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
from pydantic import SecretStr

from trading_shared.clients.postgres_client import PostgresClient
from trading_shared.config.models import PostgresSettings


@pytest.fixture
def postgres_settings():
    """Provides a default PostgresSettings instance for tests."""
    return PostgresSettings(
        user="test",
        password=SecretStr("test"),
        host="localhost",
        port=5432,
        db="testdb",
        max_retries=2,
        initial_retry_delay_s=0.01,
    )


@pytest.fixture
def mock_asyncpg_pool(mocker):
    """Mocks the asyncpg.Pool object."""
    mock_pool = MagicMock(spec=asyncpg.Pool)
    mock_pool._closed = False
    mock_conn = MagicMock(spec=asyncpg.Connection)
    mock_conn.fetch = AsyncMock(return_value=[{"id": 1}])
    mock_conn.fetchrow = AsyncMock(return_value={"id": 1})
    mock_conn.fetchval = AsyncMock(return_value=1)
    mock_conn.execute = AsyncMock(return_value="INSERT 1")

    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    return mock_pool


@pytest.mark.asyncio
class TestPostgresClient:
    """Unit tests for the PostgresClient."""

    async def test_ensure_pool_is_ready_creates_pool_if_none(self, postgres_settings, mocker, mock_asyncpg_pool):
        # Arrange
        mocker.patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_asyncpg_pool)
        client = PostgresClient(postgres_settings)

        # Act
        pool = await client.ensure_pool_is_ready()

        # Assert
        asyncpg.create_pool.assert_awaited_once()
        assert pool is not None
        assert pool == mock_asyncpg_pool

    async def test_ensure_pool_is_ready_returns_existing_pool(self, postgres_settings, mocker, mock_asyncpg_pool):
        # Arrange
        mocker.patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_asyncpg_pool)
        client = PostgresClient(postgres_settings)
        await client.ensure_pool_is_ready()
        asyncpg.create_pool.reset_mock()

        # Act
        pool = await client.ensure_pool_is_ready()

        # Assert
        asyncpg.create_pool.assert_not_called()
        assert pool == mock_asyncpg_pool

    async def test_close_closes_and_clears_pool(self, postgres_settings, mocker, mock_asyncpg_pool):
        # Arrange
        mock_asyncpg_pool.close = AsyncMock()
        mocker.patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_asyncpg_pool)
        client = PostgresClient(postgres_settings)
        await client.ensure_pool_is_ready()

        # Act
        await client.close()

        # Assert
        mock_asyncpg_pool.close.assert_awaited_once()
        assert client._pool is None

    async def test_fetch_executes_correctly(self, postgres_settings, mocker, mock_asyncpg_pool):
        # Arrange
        mocker.patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_asyncpg_pool)
        client = PostgresClient(postgres_settings)
        query = "SELECT * FROM test WHERE id = $1"
        params = (1,)

        # Act
        result = await client.fetch(query, *params)

        # Assert
        mock_conn = mock_asyncpg_pool.acquire.return_value.__aenter__.return_value
        mock_conn.fetch.assert_awaited_once_with(query, *params)
        assert result == [{"id": 1}]

    async def test_execute_resiliently_retries_on_connection_error(self, postgres_settings, mocker, mock_asyncpg_pool):
        # Arrange
        # FIX: Instantiate the exception to prevent IndexError during logging.
        mock_error = asyncpg.PostgresConnectionError("Mock DB Connection Error")
        mock_ensure_pool = mocker.patch.object(
            PostgresClient,
            "ensure_pool_is_ready",
            new_callable=AsyncMock,
            side_effect=[mock_error, mock_asyncpg_pool],
        )
        mocker.patch("asyncio.sleep", new_callable=AsyncMock)
        client = PostgresClient(postgres_settings)

        # Act
        result = await client.fetch("SELECT 1")

        # Assert
        assert mock_ensure_pool.await_count == 2
        assert mock_asyncpg_pool.acquire.call_count == 1
        assert asyncio.sleep.call_count == 1
        assert result == [{"id": 1}]

    async def test_execute_resiliently_fails_after_max_retries(self, postgres_settings, mocker):
        # Arrange
        # FIX: Instantiate the exception.
        mock_error = asyncpg.PostgresConnectionError("Mock DB Connection Error")
        mock_ensure_pool = mocker.patch.object(
            PostgresClient,
            "ensure_pool_is_ready",
            new_callable=AsyncMock,
            side_effect=mock_error,
        )
        mocker.patch("asyncio.sleep", new_callable=AsyncMock)
        client = PostgresClient(postgres_settings)

        # Act & Assert
        expected_error_msg = "Failed to execute Postgres command 'fetch_SELECT' after retries."
        with pytest.raises(ConnectionError, match=expected_error_msg):
            await client.fetch("SELECT 1")

        assert mock_ensure_pool.await_count == 2
        assert asyncio.sleep.call_count == 1

    async def test_execute_parses_result_string(self, postgres_settings, mocker, mock_asyncpg_pool):
        # Arrange
        mocker.patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_asyncpg_pool)
        client = PostgresClient(postgres_settings)
        mock_conn = mock_asyncpg_pool.acquire.return_value.__aenter__.return_value
        mock_conn.execute.return_value = "CUSTOM_COMMAND 123"

        # Act
        result = await client.execute("CUSTOM_COMMAND")

        # Assert
        assert result == 123

    async def test_execute_handles_no_count_in_result(self, postgres_settings, mocker, mock_asyncpg_pool):
        # Arrange
        mocker.patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_asyncpg_pool)
        client = PostgresClient(postgres_settings)
        mock_conn = mock_asyncpg_pool.acquire.return_value.__aenter__.return_value
        mock_conn.execute.return_value = "OK"

        # Act
        result = await client.execute("VACUUM")

        # Assert
        assert result == 0
