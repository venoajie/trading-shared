# tests/trading_shared/utils/test_identity.py
"""Unit tests for identity management utilities."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trading_shared.utils.identity import (
    TRADING_IDENTITY_NAMESPACE,
    get_account_uuid,
    provision_identity,
)


class TestGetAccountUuid:
    """Tests for get_account_uuid function."""

    def test_generates_consistent_uuid_for_same_account(self):
        account_id = "deribit-148510"
        uuid1 = get_account_uuid(account_id)
        uuid2 = get_account_uuid(account_id)
        assert uuid1 == uuid2
        assert isinstance(uuid1, uuid.UUID)

    def test_generates_different_uuids_for_different_accounts(self):
        account_id1 = "deribit-148510"
        account_id2 = "binance-12345"
        uuid1 = get_account_uuid(account_id1)
        uuid2 = get_account_uuid(account_id2)
        assert uuid1 != uuid2

    def test_uses_correct_namespace(self):
        account_id = "test-account"
        result = get_account_uuid(account_id)
        expected = uuid.uuid5(TRADING_IDENTITY_NAMESPACE, account_id)
        assert result == expected

    def test_handles_empty_string(self):
        account_id = ""
        result = get_account_uuid(account_id)
        assert isinstance(result, uuid.UUID)


class TestProvisionIdentity:
    """Tests for provision_identity function."""

    @pytest.mark.asyncio
    async def test_successful_provisioning(self):
        mock_pool = MagicMock()
        mock_connection = MagicMock()
        mock_cursor = MagicMock()

        mock_pool.acquire.return_value.__enter__ = MagicMock(return_value=mock_connection)
        mock_pool.acquire.return_value.__exit__ = MagicMock(return_value=None)
        mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=None)

        account_id = "deribit-148510"

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = None
            await provision_identity(mock_pool, account_id)
            mock_to_thread.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_provisioning_with_correct_uuid(self):
        mock_pool = MagicMock()
        account_id = "test-account-123"
        expected_uuid = get_account_uuid(account_id)

        captured_args = {}

        def capture_args(pool, sql, user_uuid, email, pw, analytics_uuid):
            captured_args["user_uuid"] = user_uuid
            captured_args["analytics_uuid"] = analytics_uuid

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.side_effect = lambda func, *args: func(*args)

            with patch("trading_shared.utils.identity._execute_provision_sql", side_effect=capture_args):
                await provision_identity(mock_pool, account_id)
                assert captured_args["user_uuid"] == expected_uuid
                assert isinstance(captured_args["analytics_uuid"], uuid.UUID)

    @pytest.mark.asyncio
    async def test_provisioning_failure_raises_exception(self):
        mock_pool = MagicMock()
        account_id = "failing-account"

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.side_effect = Exception("Database connection failed")

            with pytest.raises(Exception, match="Database connection failed"):
                await provision_identity(mock_pool, account_id)

    @pytest.mark.asyncio
    async def test_analytics_uuid_is_deterministic(self):
        mock_pool = MagicMock()
        account_id = "test-account"

        captured_analytics_uuids = []

        def capture_analytics_uuid(pool, sql, user_uuid, email, pw, analytics_uuid):
            captured_analytics_uuids.append(analytics_uuid)

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.side_effect = lambda func, *args: func(*args)

            with patch("trading_shared.utils.identity._execute_provision_sql", side_effect=capture_analytics_uuid):
                await provision_identity(mock_pool, account_id)
                await provision_identity(mock_pool, account_id)
                assert len(captured_analytics_uuids) == 2
                assert captured_analytics_uuids[0] == captured_analytics_uuids[1]
