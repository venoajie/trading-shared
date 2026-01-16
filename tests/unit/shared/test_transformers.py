# tests/unit/shared/test_transformers.py
"""
Unit tests for exchange transformers.

Tests cover:
- Binance instrument transformation
- Deribit instrument transformation
- Edge cases and error handling
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from trading_shared.exchanges.transformers import (
    transform_binance_instrument_to_canonical,
    transform_deribit_instrument_to_canonical,
)


class TestTransformBinanceInstrumentToCanonical:
    """Tests for transform_binance_instrument_to_canonical function."""

    def test_transforms_spot_instrument(self):
        # Arrange
        raw_instrument = {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"}
            ],
        }

        # Act
        result = transform_binance_instrument_to_canonical(raw_instrument, "spot")

        # Assert
        assert result is not None
        assert result["exchange"] == "binance"
        assert result["instrument_name"] == "BTCUSDT"
        assert result["market_type"] == "spot"
        assert result["instrument_kind"] == "spot"
        assert result["base_asset"] == "BTC"
        assert result["quote_asset"] == "USDT"
        assert result["settlement_asset"] == "USDT"
        assert result["tick_size"] == 0.01

    def test_transforms_linear_futures_perpetual(self):
        # Arrange
        raw_instrument = {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "marginAsset": "USDT",
            "contractType": "PERPETUAL",
            "contractSize": 1,
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.1"}
            ],
        }

        # Act
        result = transform_binance_instrument_to_canonical(raw_instrument, "linear_futures")

        # Assert
        assert result is not None
        assert result["market_type"] == "linear_futures"
        assert result["instrument_kind"] == "perpetual"
        assert result["settlement_asset"] == "USDT"
        assert result["contract_size"] == 1

    def test_transforms_linear_futures_dated(self):
        # Arrange
        raw_instrument = {
            "symbol": "BTCUSDT_230630",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "marginAsset": "USDT",
            "contractType": "CURRENT_QUARTER",
            "deliveryDate": 1688083200000,  # 2023-06-30
            "filters": [],
        }

        # Act
        result = transform_binance_instrument_to_canonical(raw_instrument, "linear_futures")

        # Assert
        assert result is not None
        assert result["instrument_kind"] == "future"
        assert result["expiration_timestamp"] is not None

    def test_transforms_inverse_futures(self):
        # Arrange
        raw_instrument = {
            "symbol": "BTCUSD_PERP",
            "baseAsset": "BTC",
            "quoteAsset": "USD",
            "marginAsset": "BTC",
            "contractType": "PERPETUAL",
            "filters": [],
        }

        # Act
        result = transform_binance_instrument_to_canonical(raw_instrument, "inverse_futures")

        # Assert
        assert result is not None
        assert result["market_type"] == "inverse_futures"
        assert result["settlement_asset"] == "BTC"

    def test_returns_none_when_settlement_asset_missing(self):
        # Arrange
        raw_instrument = {
            "symbol": "INVALID",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            # Missing marginAsset for futures
            "filters": [],
        }

        with patch("trading_shared.exchanges.transformers.log"):
            # Act
            result = transform_binance_instrument_to_canonical(raw_instrument, "linear_futures")

            # Assert
            assert result is None

    def test_handles_missing_tick_size(self):
        # Arrange
        raw_instrument = {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "filters": [],  # No PRICE_FILTER
        }

        # Act
        result = transform_binance_instrument_to_canonical(raw_instrument, "spot")

        # Assert
        assert result is not None
        assert result["tick_size"] is None

    def test_handles_expiration_timestamp_conversion(self):
        # Arrange
        delivery_timestamp = 1688083200000  # 2023-06-30 00:00:00 UTC
        raw_instrument = {
            "symbol": "BTCUSDT_230630",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "marginAsset": "USDT",
            "contractType": "CURRENT_QUARTER",
            "deliveryDate": delivery_timestamp,
            "filters": [],
        }

        # Act
        result = transform_binance_instrument_to_canonical(raw_instrument, "linear_futures")

        # Assert
        assert result is not None
        assert result["expiration_timestamp"] is not None
        # Verify it's a valid ISO format timestamp
        datetime.fromisoformat(result["expiration_timestamp"])

    def test_includes_raw_data(self):
        # Arrange
        raw_instrument = {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "filters": [],
            "extra_field": "extra_value",
        }

        # Act
        result = transform_binance_instrument_to_canonical(raw_instrument, "spot")

        # Assert
        assert result is not None
        assert result["data"] == raw_instrument
        assert result["data"]["extra_field"] == "extra_value"


class TestTransformDeribitInstrumentToCanonical:
    """Tests for transform_deribit_instrument_to_canonical function."""

    def test_transforms_perpetual_future(self):
        # Arrange
        raw_instrument = {
            "instrument_name": "BTC-PERPETUAL",
            "kind": "future",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            "settlement_period": "perpetual",
            "tick_size": 0.5,
            "contract_size": 10,
            "instrument_type": "reversed",
        }

        # Act
        result = transform_deribit_instrument_to_canonical(raw_instrument)

        # Assert
        assert result["exchange"] == "deribit"
        assert result["instrument_name"] == "BTC-PERPETUAL"
        assert result["instrument_kind"] == "perpetual"
        assert result["base_asset"] == "BTC"
        assert result["settlement_asset"] == "BTC"
        assert result["market_type"] == "inverse_futures"

    def test_transforms_dated_future(self):
        # Arrange
        raw_instrument = {
            "instrument_name": "BTC-30JUN23",
            "kind": "future",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            "expiration_timestamp": 1688083200000,
            "tick_size": 0.5,
            "contract_size": 10,
            "instrument_type": "reversed",
        }

        # Act
        result = transform_deribit_instrument_to_canonical(raw_instrument)

        # Assert
        assert result["instrument_kind"] == "future"
        assert result["expiration_timestamp"] is not None

    def test_transforms_option(self):
        # Arrange
        raw_instrument = {
            "instrument_name": "BTC-30JUN23-30000-C",
            "kind": "option",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            "expiration_timestamp": 1688083200000,
            "tick_size": 0.0001,
            "contract_size": 1,
            "instrument_type": "reversed",
        }

        # Act
        result = transform_deribit_instrument_to_canonical(raw_instrument)

        # Assert
        assert result["instrument_kind"] == "option"
        assert result["market_type"] == "inverse_options"

    def test_handles_missing_settlement_currency(self):
        # Arrange
        raw_instrument = {
            "instrument_name": "BTC-PERPETUAL",
            "kind": "future",
            "base_currency": "BTC",
            "quote_currency": "USD",
            # settlement_currency is missing
            "tick_size": 0.5,
            "contract_size": 10,
            "instrument_type": "reversed",
        }

        # Act
        result = transform_deribit_instrument_to_canonical(raw_instrument)

        # Assert
        assert result["settlement_asset"] == "BTC"  # Falls back to base_currency

    def test_handles_unknown_kind(self):
        # Arrange
        raw_instrument = {
            "instrument_name": "UNKNOWN-INSTRUMENT",
            "kind": "unknown_kind",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            "instrument_type": "linear",
        }

        # Act
        result = transform_deribit_instrument_to_canonical(raw_instrument)

        # Assert
        assert result["instrument_kind"] == "unknown"

    def test_handles_missing_expiration_timestamp(self):
        # Arrange
        raw_instrument = {
            "instrument_name": "BTC-PERPETUAL",
            "kind": "future",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            # No expiration_timestamp
            "instrument_type": "reversed",
        }

        # Act
        result = transform_deribit_instrument_to_canonical(raw_instrument)

        # Assert
        assert result["expiration_timestamp"] is None

    def test_includes_raw_data(self):
        # Arrange
        raw_instrument = {
            "instrument_name": "BTC-PERPETUAL",
            "kind": "future",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            "instrument_type": "reversed",
            "extra_field": "extra_value",
        }

        # Act
        result = transform_deribit_instrument_to_canonical(raw_instrument)

        # Assert
        assert result["data"] == raw_instrument
        assert result["data"]["extra_field"] == "extra_value"

    def test_expiration_timestamp_conversion(self):
        # Arrange
        expiration_ms = 1688083200000  # 2023-06-30 00:00:00 UTC
        raw_instrument = {
            "instrument_name": "BTC-30JUN23",
            "kind": "future",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            "expiration_timestamp": expiration_ms,
            "instrument_type": "reversed",
        }

        # Act
        result = transform_deribit_instrument_to_canonical(raw_instrument)

        # Assert
        assert result["expiration_timestamp"] is not None
        # Verify it's a valid ISO format timestamp
        parsed_dt = datetime.fromisoformat(result["expiration_timestamp"])
        assert parsed_dt.tzinfo == timezone.utc
