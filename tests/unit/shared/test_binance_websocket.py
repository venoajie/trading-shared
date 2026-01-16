# tests/unit/shared/test_binance_websocket.py

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from trading_engine_core.models import MarketDefinition

from trading_shared.exchanges.websockets.binance import BinanceWsClient


class TestBinanceWsClient:
    """Tests for BinanceWsClient class."""

    @pytest.fixture
    def market_definition(self):
        """Provides a mock MarketDefinition."""
        return MarketDefinition(
            market_id="binance_spot",
            exchange="binance",
            market_type="spot",
            ws_base_url="wss://stream.binance.com:9443",
        )

    @pytest.fixture
    def mock_repos(self):
        """Provides mocked repository instances."""
        return {
            "market_data_repo": MagicMock(),
            "instrument_repo": MagicMock(),
            "system_state_repo": MagicMock(),
        }

    @pytest.fixture
    def mock_settings(self):
        """Provides mock ExchangeSettings."""
        mock_settings = MagicMock()
        return mock_settings

    def test_initialization(self, market_definition, mock_repos, mock_settings):
        # Arrange & Act
        client = BinanceWsClient(
            market_definition=market_definition,
            market_data_repo=mock_repos["market_data_repo"],
            instrument_repo=mock_repos["instrument_repo"],
            system_state_repo=mock_repos["system_state_repo"],
            universe_state_key="test:universe",
            settings=mock_settings,
            shard_id=0,
            total_shards=2,
        )

        # Assert
        assert client.exchange_name == "binance"
        assert client.shard_id == 0
        assert client.total_shards == 2
        assert client.shard_num_for_log == 1

    @pytest.mark.asyncio
    async def test_get_channels_from_universe_filters_by_exchange(self, market_definition, mock_repos, mock_settings):
        # Arrange
        client = BinanceWsClient(
            market_definition=market_definition,
            market_data_repo=mock_repos["market_data_repo"],
            instrument_repo=mock_repos["instrument_repo"],
            system_state_repo=mock_repos["system_state_repo"],
            universe_state_key="test:universe",
            settings=mock_settings,
            shard_id=0,
            total_shards=1,
        )

        universe = [
            {"symbol": "BTC-USDT", "exchange": "binance", "market_type": "spot"},
            {"symbol": "ETH-USDT", "exchange": "binance", "market_type": "spot"},
            {"symbol": "BTC-PERPETUAL", "exchange": "deribit", "market_type": "futures"},
        ]

        # Act
        channels = await client._get_channels_from_universe(universe)

        # Assert
        assert len(channels) == 2
        assert "btcusdt@trade" in channels
        assert "ethusdt@trade" in channels

    @pytest.mark.asyncio
    async def test_get_channels_from_universe_sharding(self, market_definition, mock_repos, mock_settings):
        # Arrange
        client = BinanceWsClient(
            market_definition=market_definition,
            market_data_repo=mock_repos["market_data_repo"],
            instrument_repo=mock_repos["instrument_repo"],
            system_state_repo=mock_repos["system_state_repo"],
            universe_state_key="test:universe",
            settings=mock_settings,
            shard_id=0,
            total_shards=2,
        )

        universe = [
            {"symbol": "BTC-USDT", "exchange": "binance", "market_type": "spot"},
            {"symbol": "ETH-USDT", "exchange": "binance", "market_type": "spot"},
            {"symbol": "ADA-USDT", "exchange": "binance", "market_type": "spot"},
            {"symbol": "DOT-USDT", "exchange": "binance", "market_type": "spot"},
        ]

        # Act
        channels = await client._get_channels_from_universe(universe)

        # Assert - Should only get half the symbols (shard 0 of 2)
        assert len(channels) == 2

    @pytest.mark.asyncio
    async def test_get_channels_normalizes_symbol_format(self, market_definition, mock_repos, mock_settings):
        # Arrange
        client = BinanceWsClient(
            market_definition=market_definition,
            market_data_repo=mock_repos["market_data_repo"],
            instrument_repo=mock_repos["instrument_repo"],
            system_state_repo=mock_repos["system_state_repo"],
            universe_state_key="test:universe",
            settings=mock_settings,
            shard_id=0,
            total_shards=1,
        )

        universe = [
            {"symbol": "BTC-USDT", "exchange": "binance", "market_type": "spot"},
        ]

        # Act
        channels = await client._get_channels_from_universe(universe)

        # Assert - Dashes should be removed and lowercase
        assert "btcusdt@trade" in channels

    @pytest.mark.asyncio
    async def test_get_channels_handles_instrument_name_field(self, market_definition, mock_repos, mock_settings):
        # Arrange
        client = BinanceWsClient(
            market_definition=market_definition,
            market_data_repo=mock_repos["market_data_repo"],
            instrument_repo=mock_repos["instrument_repo"],
            system_state_repo=mock_repos["system_state_repo"],
            universe_state_key="test:universe",
            settings=mock_settings,
            shard_id=0,
            total_shards=1,
        )

        universe = [
            {"instrument_name": "BTC-USDT", "exchange": "binance", "market_type": "spot"},
        ]

        # Act
        channels = await client._get_channels_from_universe(universe)

        # Assert
        assert "btcusdt@trade" in channels

    @pytest.mark.asyncio
    async def test_get_channels_filters_non_spot_markets(self, market_definition, mock_repos, mock_settings):
        # Arrange
        client = BinanceWsClient(
            market_definition=market_definition,
            market_data_repo=mock_repos["market_data_repo"],
            instrument_repo=mock_repos["instrument_repo"],
            system_state_repo=mock_repos["system_state_repo"],
            universe_state_key="test:universe",
            settings=mock_settings,
            shard_id=0,
            total_shards=1,
        )

        universe = [
            {"symbol": "BTC-USDT", "exchange": "binance", "market_type": "spot"},
            {"symbol": "ETH-USDT", "exchange": "binance", "market_type": "futures"},
        ]

        # Act
        channels = await client._get_channels_from_universe(universe)

        # Assert - Only spot should be included
        assert len(channels) == 1
        assert "btcusdt@trade" in channels

    @pytest.mark.asyncio
    async def test_close_sets_running_flag(self, market_definition, mock_repos, mock_settings):
        # Arrange
        client = BinanceWsClient(
            market_definition=market_definition,
            market_data_repo=mock_repos["market_data_repo"],
            instrument_repo=mock_repos["instrument_repo"],
            system_state_repo=mock_repos["system_state_repo"],
            universe_state_key="test:universe",
            settings=mock_settings,
            shard_id=0,
            total_shards=1,
        )
        client._is_running.set()

        # Act
        await client.close()

        # Assert
        assert not client._is_running.is_set()

    @pytest.mark.asyncio
    async def test_close_closes_websocket_connection(self, market_definition, mock_repos, mock_settings):
        # Arrange
        client = BinanceWsClient(
            market_definition=market_definition,
            market_data_repo=mock_repos["market_data_repo"],
            instrument_repo=mock_repos["instrument_repo"],
            system_state_repo=mock_repos["system_state_repo"],
            universe_state_key="test:universe",
            settings=mock_settings,
            shard_id=0,
            total_shards=1,
        )

        mock_ws = AsyncMock()
        client._ws = mock_ws

        # Act
        await client.close()

        # Assert
        mock_ws.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_channels_handles_empty_universe(self, market_definition, mock_repos, mock_settings):
        # Arrange
        client = BinanceWsClient(
            market_definition=market_definition,
            market_data_repo=mock_repos["market_data_repo"],
            instrument_repo=mock_repos["instrument_repo"],
            system_state_repo=mock_repos["system_state_repo"],
            universe_state_key="test:universe",
            settings=mock_settings,
            shard_id=0,
            total_shards=1,
        )

        # Act
        channels = await client._get_channels_from_universe([])

        # Assert
        assert len(channels) == 0

    @pytest.mark.asyncio
    async def test_get_channels_handles_missing_fields(self, market_definition, mock_repos, mock_settings):
        # Arrange
        client = BinanceWsClient(
            market_definition=market_definition,
            market_data_repo=mock_repos["market_data_repo"],
            instrument_repo=mock_repos["instrument_repo"],
            system_state_repo=mock_repos["system_state_repo"],
            universe_state_key="test:universe",
            settings=mock_settings,
            shard_id=0,
            total_shards=1,
        )

        universe = [
            {"exchange": "binance"},  # Missing symbol
            {"symbol": "BTC-USDT"},  # Missing exchange
            {"symbol": "ETH-USDT", "exchange": "binance", "market_type": "spot"},  # Valid
        ]

        # Act
        channels = await client._get_channels_from_universe(universe)

        # Assert - Should only process valid entry
        assert len(channels) == 1
