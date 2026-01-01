# tests/trading_shared/repositories/test_ohlc_repository.py

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock

from trading_shared.repositories.ohlc_repository import OhlcRepository


@pytest.fixture
def mock_postgres_client():
    """Provides a mock PostgresClient instance."""
    client = MagicMock()
    client.fetch = AsyncMock(return_value=[])
    client.fetchrow = AsyncMock(return_value=None)
    client.execute = AsyncMock()
    return client


@pytest.fixture
def ohlc_repo(mock_postgres_client):
    """Provides an OhlcRepository with a mocked dependency."""
    return OhlcRepository(mock_postgres_client)


@pytest.mark.asyncio
class TestOhlcRepository:

    @pytest.mark.parametrize(
        "res_str, expected_td",
        [
            ("1", timedelta(minutes=1)),
            ("15", timedelta(minutes=15)),
            ("1H", timedelta(hours=1)),
            ("4H", timedelta(hours=4)),
            ("1D", timedelta(days=1)),
            ("1W", timedelta(weeks=1)),
            ("5 minute", timedelta(minutes=5)),
            ("2 hour", timedelta(hours=2)),
        ],
    )
    def test_parse_resolution_to_timedelta(self, ohlc_repo, res_str, expected_td):
        # Act
        result = ohlc_repo._parse_resolution_to_timedelta(res_str)
        # Assert
        assert result == expected_td

    def test_parse_resolution_invalid_format_raises_error(self, ohlc_repo):
        # Act & Assert
        with pytest.raises(ValueError, match="Unknown resolution format: 1M"):
            ohlc_repo._parse_resolution_to_timedelta("1M")

    async def test_fetch_latest_timestamp_calls_db_correctly(
        self, ohlc_repo, mock_postgres_client
    ):
        # Arrange
        exchange = "binance"
        instrument = "BTCUSDT"
        res_td = timedelta(minutes=1)
        expected_query = "SELECT MAX(tick) AS latest_tick FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3"

        # Act
        await ohlc_repo.fetch_latest_timestamp(exchange, instrument, res_td)

        # Assert
        mock_postgres_client.fetchrow.assert_awaited_once_with(
            expected_query, exchange, instrument, res_td
        )

    async def test_fetch_for_instrument_calls_db_correctly(
        self, ohlc_repo, mock_postgres_client
    ):
        # Arrange
        exchange = "binance"
        instrument = "BTCUSDT"
        res_str = "1H"
        limit = 100
        expected_td = timedelta(hours=1)
        expected_query = "SELECT * FROM ohlc WHERE exchange = $1 AND instrument_name = $2 AND resolution = $3 ORDER BY tick DESC LIMIT $4"

        # Act
        await ohlc_repo.fetch_for_instrument(exchange, instrument, res_str, limit)

        # Assert
        mock_postgres_client.fetch.assert_awaited_once_with(
            expected_query, exchange, instrument, expected_td, limit
        )

    async def test_bulk_upsert_prepares_records_and_calls_db(
        self, ohlc_repo, mock_postgres_client
    ):
        # Arrange
        now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        candles = [
            {
                "exchange": "binance",
                "instrument_name": "BTCUSDT",
                "resolution": "1",
                "tick": now_ts,
                "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100.0,
                "open_interest": 50.0
            }
        ]
        
        expected_record_tuple = (
            "binance", "BTCUSDT", timedelta(minutes=1),
            datetime.fromtimestamp(now_ts / 1000, tz=timezone.utc),
            1.0, 2.0, 0.5, 1.5, 100.0, 50.0
        )
        expected_query = "SELECT bulk_upsert_ohlc($1::ohlc_upsert_type[])"

        # Act
        await ohlc_repo.bulk_upsert(candles)

        # Assert
        mock_postgres_client.execute.assert_awaited_once_with(
            expected_query, [expected_record_tuple]
        )

    async def test_bulk_upsert_does_nothing_if_no_candles(
        self, ohlc_repo, mock_postgres_client
    ):
        # Arrange
        candles = []

        # Act
        await ohlc_repo.bulk_upsert(candles)

        # Assert
        mock_postgres_client.execute.assert_not_called()
