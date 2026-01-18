# tests/trading_shared/cache/test_universe_cache.py

import asyncio
from unittest.mock import AsyncMock, MagicMock

import orjson
import pytest

from trading_shared.cache.universe_cache import UniverseCache
from trading_shared.core.models import StorageMode


class TestUniverseCache:
    """Tests for UniverseCache class."""

    @pytest.fixture
    def mock_redis_client(self):
        mock_client = MagicMock()
        mock_client.get = AsyncMock()
        return mock_client

    @pytest.fixture
    def sample_universe_data(self):
        return [
            {
                "instrument_name": "BTC-USDT",
                "exchange": "binance",
                "market_type": "spot",
            },
            {
                "instrument_name": "ETH-USDT",
                "exchange": "binance",
                "market_type": "spot",
            },
            {
                "symbol": "BTC-PERPETUAL",
                "exchange": "deribit",
                "market_type": "inverse_futures",
            },
        ]

    @pytest.mark.asyncio
    async def test_initialization(self, mock_redis_client):
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        assert cache._universe_key == "test:universe:key"
        assert len(cache._raw_to_canonical) == 0
        assert len(cache._storage_cache) == 0
        assert len(cache._instrument_list) == 0

    @pytest.mark.asyncio
    async def test_refresh_loads_data_from_redis(self, mock_redis_client, sample_universe_data):
        mock_redis_client.get = AsyncMock(return_value=orjson.dumps(sample_universe_data))
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        await cache.refresh()
        mock_redis_client.get.assert_awaited_once_with("test:universe:key")
        assert len(cache._instrument_list) == 3
        assert len(cache._raw_to_canonical) > 0

    @pytest.mark.asyncio
    async def test_get_canonical_name_normalizes_symbol(self, mock_redis_client, sample_universe_data):
        mock_redis_client.get = AsyncMock(return_value=orjson.dumps(sample_universe_data))
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        await cache.refresh()
        result1 = cache.get_canonical_name("BTCUSDT")
        result2 = cache.get_canonical_name("BTC-USDT")
        result3 = cache.get_canonical_name("btc_usdt")
        assert result1 == "BTC-USDT"
        assert result2 == "BTC-USDT"
        assert result3 == "BTC-USDT"

    @pytest.mark.asyncio
    async def test_get_canonical_name_returns_none_for_unknown_symbol(self, mock_redis_client, sample_universe_data):
        mock_redis_client.get = AsyncMock(return_value=orjson.dumps(sample_universe_data))
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        await cache.refresh()
        result = cache.get_canonical_name("UNKNOWN-SYMBOL")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_canonical_name_handles_empty_string(self, mock_redis_client):
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        result = cache.get_canonical_name("")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_canonical_name_handles_none(self, mock_redis_client):
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        result = cache.get_canonical_name(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_instruments_returns_list(self, mock_redis_client, sample_universe_data):
        mock_redis_client.get = AsyncMock(return_value=orjson.dumps(sample_universe_data))
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        await cache.refresh()
        instruments = cache.get_all_instruments()
        assert isinstance(instruments, list)
        assert len(instruments) == 3
        assert instruments[0]["instrument_name"] == "BTC-USDT"

    @pytest.mark.asyncio
    async def test_get_storage_mode_returns_persistent_by_default(self, mock_redis_client, sample_universe_data):
        mock_redis_client.get = AsyncMock(return_value=orjson.dumps(sample_universe_data))
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        await cache.refresh()
        mode = await cache.get_storage_mode("BTC-USDT")
        assert mode == StorageMode.PERSISTENT

    @pytest.mark.asyncio
    async def test_get_storage_mode_returns_persistent_for_unknown_instrument(self, mock_redis_client):
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        mode = await cache.get_storage_mode("UNKNOWN")
        assert mode == StorageMode.PERSISTENT

    @pytest.mark.asyncio
    async def test_refresh_handles_empty_redis_key(self, mock_redis_client):
        mock_redis_client.get = AsyncMock(return_value=None)
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        await cache.refresh()
        assert len(cache._instrument_list) == 0
        assert len(cache._raw_to_canonical) == 0

    @pytest.mark.asyncio
    async def test_refresh_handles_invalid_json(self, mock_redis_client):
        mock_redis_client.get = AsyncMock(return_value=b"invalid json")
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        await cache.refresh()
        assert len(cache._instrument_list) == 0

    @pytest.mark.asyncio
    async def test_refresh_skips_entries_without_name_or_exchange(self, mock_redis_client):
        invalid_data = [
            {"instrument_name": "BTC-USDT"},
            {"exchange": "binance"},
            {"instrument_name": "ETH-USDT", "exchange": "binance"},
        ]
        mock_redis_client.get = AsyncMock(return_value=orjson.dumps(invalid_data))
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        await cache.refresh()
        assert len(cache._instrument_list) == 1
        assert cache._instrument_list[0]["instrument_name"] == "ETH-USDT"

    @pytest.mark.asyncio
    async def test_refresh_normalizes_symbol_field_to_instrument_name(self, mock_redis_client):
        data = [
            {"symbol": "BTC-PERPETUAL", "exchange": "deribit"},
        ]
        mock_redis_client.get = AsyncMock(return_value=orjson.dumps(data))
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        await cache.refresh()
        assert cache._instrument_list[0]["instrument_name"] == "BTC-PERPETUAL"

    @pytest.mark.asyncio
    async def test_refresh_creates_identity_mapping(self, mock_redis_client, sample_universe_data):
        mock_redis_client.get = AsyncMock(return_value=orjson.dumps(sample_universe_data))
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        await cache.refresh()
        assert cache.get_canonical_name("BTC-USDT") == "BTC-USDT"

    @pytest.mark.asyncio
    async def test_concurrent_access_is_thread_safe(self, mock_redis_client, sample_universe_data):
        mock_redis_client.get = AsyncMock(return_value=orjson.dumps(sample_universe_data))
        cache = UniverseCache(mock_redis_client, "test:universe:key")
        await cache.refresh()
        tasks = [
            cache.get_storage_mode("BTC-USDT"),
            cache.get_storage_mode("ETH-USDT"),
            cache.get_storage_mode("BTC-PERPETUAL"),
        ]
        results = await asyncio.gather(*tasks)
        assert all(mode == StorageMode.PERSISTENT for mode in results)
