# tests/unit/shared/test_healthcheck.py
"""
Unit tests for DeadManSwitch healthcheck mechanism.

Tests cover:
- Heartbeat loop functionality
- Start and stop operations
- Health check verification
- Redis interaction
- Error handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trading_shared.utils.healthcheck import DeadManSwitch


class TestDeadManSwitch:
    """Tests for DeadManSwitch class."""

    @pytest.fixture
    def mock_redis_client(self):
        """Provides a mocked Redis client."""
        mock_client = MagicMock()
        mock_client.setex = AsyncMock()
        mock_client.delete = AsyncMock()
        mock_client.exists = AsyncMock(return_value=1)
        return mock_client

    @pytest.mark.asyncio
    async def test_initialization(self, mock_redis_client):
        # Arrange & Act
        switch = DeadManSwitch(
            redis_client=mock_redis_client,
            service_name="test_service",
            heartbeat_interval=5,
            heartbeat_ttl=15,
        )

        # Assert
        assert switch.service_name == "test_service"
        assert switch.heartbeat_interval == 5
        assert switch.heartbeat_ttl == 15
        assert switch.heartbeat_key == "healthcheck:test_service:heartbeat"
        assert not switch._running

    @pytest.mark.asyncio
    async def test_start_begins_heartbeat_loop(self, mock_redis_client):
        # Arrange
        switch = DeadManSwitch(
            redis_client=mock_redis_client,
            service_name="test_service",
            heartbeat_interval=0.1,
            heartbeat_ttl=1,
        )

        # Act
        await switch.start()
        await asyncio.sleep(0.25)  # Allow at least 2 heartbeats

        # Assert
        assert switch._running
        assert mock_redis_client.setex.await_count >= 2

        # Cleanup
        await switch.stop()

    @pytest.mark.asyncio
    async def test_start_when_already_running_logs_warning(self, mock_redis_client):
        # Arrange
        switch = DeadManSwitch(
            redis_client=mock_redis_client,
            service_name="test_service",
        )

        with patch("trading_shared.utils.healthcheck.log") as mock_log:
            # Act
            await switch.start()
            await switch.start()  # Second call

            # Assert
            mock_log.warning.assert_called_once()
            assert "already running" in mock_log.warning.call_args[0][0].lower()

            # Cleanup
            await switch.stop()

    @pytest.mark.asyncio
    async def test_stop_ends_heartbeat_loop(self, mock_redis_client):
        # Arrange
        switch = DeadManSwitch(
            redis_client=mock_redis_client,
            service_name="test_service",
            heartbeat_interval=0.1,
        )

        # Act
        await switch.start()
        await asyncio.sleep(0.15)
        await switch.stop()

        # Assert
        assert not switch._running
        mock_redis_client.delete.assert_awaited_once_with("healthcheck:test_service:heartbeat")

    @pytest.mark.asyncio
    async def test_stop_when_not_running_does_nothing(self, mock_redis_client):
        # Arrange
        switch = DeadManSwitch(
            redis_client=mock_redis_client,
            service_name="test_service",
        )

        # Act
        await switch.stop()

        # Assert
        mock_redis_client.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_heartbeat_sends_correct_data(self, mock_redis_client):
        # Arrange
        switch = DeadManSwitch(
            redis_client=mock_redis_client,
            service_name="test_service",
            heartbeat_interval=0.1,
            heartbeat_ttl=30,
        )

        # Act
        await switch.start()
        await asyncio.sleep(0.15)

        # Assert
        mock_redis_client.setex.assert_awaited()
        call_args = mock_redis_client.setex.call_args
        assert call_args[0][0] == "healthcheck:test_service:heartbeat"
        assert call_args[0][1] == 30  # TTL
        # Timestamp should be ISO format string
        assert isinstance(call_args[0][2], str)

        # Cleanup
        await switch.stop()

    @pytest.mark.asyncio
    async def test_heartbeat_handles_redis_errors(self, mock_redis_client):
        # Arrange
        mock_redis_client.setex = AsyncMock(side_effect=Exception("Redis error"))
        switch = DeadManSwitch(
            redis_client=mock_redis_client,
            service_name="test_service",
            heartbeat_interval=0.1,
        )

        with patch("trading_shared.utils.healthcheck.log") as mock_log:
            # Act
            await switch.start()
            await asyncio.sleep(0.15)

            # Assert - Should log error but continue running
            assert switch._running
            mock_log.error.assert_called()

            # Cleanup
            await switch.stop()

    @pytest.mark.asyncio
    async def test_check_health_returns_true_when_key_exists(self, mock_redis_client):
        # Arrange
        mock_redis_client.exists = AsyncMock(return_value=1)
        switch = DeadManSwitch(
            redis_client=mock_redis_client,
            service_name="test_service",
        )

        # Act
        result = await switch.check_health()

        # Assert
        assert result is True
        mock_redis_client.exists.assert_awaited_once_with("healthcheck:test_service:heartbeat")

    @pytest.mark.asyncio
    async def test_check_health_returns_false_when_key_missing(self, mock_redis_client):
        # Arrange
        mock_redis_client.exists = AsyncMock(return_value=0)
        switch = DeadManSwitch(
            redis_client=mock_redis_client,
            service_name="test_service",
        )

        # Act
        result = await switch.check_health()

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_check_health_returns_false_on_exception(self, mock_redis_client):
        # Arrange
        mock_redis_client.exists = AsyncMock(side_effect=Exception("Connection failed"))
        switch = DeadManSwitch(
            redis_client=mock_redis_client,
            service_name="test_service",
        )

        with patch("trading_shared.utils.healthcheck.log"):
            # Act
            result = await switch.check_health()

            # Assert
            assert result is False

    @pytest.mark.asyncio
    async def test_stop_handles_delete_errors_gracefully(self, mock_redis_client):
        # Arrange
        mock_redis_client.delete = AsyncMock(side_effect=Exception("Delete failed"))
        switch = DeadManSwitch(
            redis_client=mock_redis_client,
            service_name="test_service",
            heartbeat_interval=0.1,
        )

        with patch("trading_shared.utils.healthcheck.log") as mock_log:
            # Act
            await switch.start()
            await asyncio.sleep(0.05)
            await switch.stop()

            # Assert - Should log error but complete stop
            assert not switch._running
            mock_log.error.assert_called()
