# tests/trading_shared/clients/test_postgres_client.py

import asyncio
from unittest.mock import MagicMock, AsyncMock

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

    # Configure the pool to return the mock connection via its async context manager
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    return mock_pool


@pytest.mark.asyncio
class TestPostgresClient:
    """Unit tests for the PostgresClient."""

    async def test_ensure_pool_is_ready_creates_pool_if_none(
        self, postgres_settings, mocker, mock_asyncpg_pool
    ):
        # Arrange
        mock_create_pool = mocker.patch(
            "asyncpg.create_pool",
            new_callable=AsyncMock,
            return_value=mock_asyncpg_pool,
        )
        client = PostgresClient(postgres_settings)

        # Act
        pool = await client.ensure_pool_is_ready()

        # Assert
        mock_create_pool.assert_awaited_once()
        assert pool is not None
        assert pool == mock_asyncpg_pool

    async def test_ensure_pool_is_ready_returns_existing_pool(
        self, postgres_settings, mocker, mock_asyncpg_pool
    ):
        # Arrange
        mocker.patch(
            "asyncpg.create_pool",
            new_callable=AsyncMock,
            return_value=mock_asyncpg_pool,
        )
        client = PostgresClient(postgres_settings)
        await client.ensure_pool_is_ready()  # First call creates the pool
        mock_create_pool_again = mocker.patch("asyncpg.create_pool")

        # Act
        pool = await client.ensure_pool_is_ready()  # Second call should not recreate

        # Assert
        mock_create_pool_again.assert_not_called()
        assert pool == mock_asyncpg_pool

    async def test_close_closes_and_clears_pool(
        self, postgres_settings, mocker, mock_asyncpg_pool
    ):
        # Arrange
        mock_asyncpg_pool.close = AsyncMock()
        mocker.patch(
            "asyncpg.create_pool",
            new_callable=AsyncMock,
            return_value=mock_asyncpg_pool,
        )
        client = PostgresClient(postgres_settings)
        await client.ensure_pool_is_ready()

        # Act
        await client.close()

        # Assert
        mock_asyncpg_pool.close.assert_awaited_once()
        assert client._pool is None

    async def test_fetch_executes_correctly(
        self, postgres_settings, mocker, mock_asyncpg_pool
    ):
        # Arrange
        mocker.patch(
            "asyncpg.create_pool",
            new_callable=AsyncMock,
            return_value=mock_asyncpg_pool,
        )
        client = PostgresClient(postgres_settings)
        query = "SELECT * FROM test WHERE id = $1"
        params = (1,)

        # Act
        result = await client.fetch(query, *params)

        # Assert
        mock_conn = mock_asyncpg_pool.acquire.return_value.__aenter__.return_value
        mock_conn.fetch.assert_awaited_once_with(query, *params)
        assert result == [{"id": 1}]

    async def test_execute_resiliently_retries_on_connection_error(
        self, postgres_settings, mocker, mock_asyncpg_pool
    ):
        # Arrange
        # Simulate failure on first attempt, success on second
        mocker.patch(
            "asyncpg.create_pool",
            new_callable=AsyncMock,
            side_effect=[asyncpg.PostgresConnectionError, mock_asyncpg_pool],
        )
        mocker.patch("asyncio.sleep", AsyncMock())
        client = PostgresClient(postgres_settings)

        # Act
        result = await client.fetch("SELECT 1")

        # Assert
        assert (
            client._pool.acquire.call_count == 1
        )  # The successful pool was acquired once
        assert result == [{"id": 1}]
        assert asyncio.sleep.call_count == 1

    async def test_execute_resiliently_fails_after_max_retries(
        self, postgres_settings, mocker
    ):
        # Arrange
        mocker.patch(
            "asyncpg.create_pool",
            new_callable=AsyncMock,
            side_effect=asyncpg.PostgresConnectionError,
        )
        mocker.patch("asyncio.sleep", AsyncMock())
        client = PostgresClient(postgres_settings)

        # Act & Assert
        with pytest.raises(ConnectionError, match="failed after 2 attempts"):
            await client.fetch("SELECT 1")

        assert mocker.patch("asyncpg.create_pool").call_count == 2
        assert asyncio.sleep.call_count == 1

    async def test_execute_parses_result_string(
        self, postgres_settings, mocker, mock_asyncpg_pool
    ):
        # Arrange
        mocker.patch(
            "asyncpg.create_pool",
            new_callable=AsyncMock,
            return_value=mock_asyncpg_pool,
        )
        client = PostgresClient(postgres_settings)
        mock_conn = mock_asyncpg_pool.acquire.return_value.__aenter__.return_value
        mock_conn.execute.return_value = "CUSTOM_COMMAND 123"

        # Act
        result = await client.execute("CUSTOM_COMMAND")

        # Assert
        assert result == 123

    async def test_execute_handles_no_count_in_result(
        self, postgres_settings, mocker, mock_asyncpg_pool
    ):
        # Arrange
        mocker.patch(
            "asyncpg.create_pool",
            new_callable=AsyncMock,
            return_value=mock_asyncpg_pool,
        )
        client = PostgresClient(postgres_settings)
        mock_conn = mock_asyncpg_pool.acquire.return_value.__aenter__.return_value
        mock_conn.execute.return_value = "OK"

        # Act
        result = await client.execute("VACUUM")

        # Assert
        assert result == 0
