# tests/trading_shared/exchanges/test_transformers.py

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
        raw_instrument = {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.01"}],
        }
        result = transform_binance_instrument_to_canonical(raw_instrument, "spot")
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
        raw_instrument = {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "marginAsset": "USDT",
            "contractType": "PERPETUAL",
            "contractSize": 1,
            "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.1"}],
        }
        result = transform_binance_instrument_to_canonical(raw_instrument, "linear_futures")
        assert result is not None
        assert result["market_type"] == "linear_futures"
        assert result["instrument_kind"] == "perpetual"
        assert result["settlement_asset"] == "USDT"
        assert result["contract_size"] == 1

    def test_transforms_linear_futures_dated(self):
        raw_instrument = {
            "symbol": "BTCUSDT_230630",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "marginAsset": "USDT",
            "contractType": "CURRENT_QUARTER",
            "deliveryDate": 1688083200000,
            "filters": [],
        }
        result = transform_binance_instrument_to_canonical(raw_instrument, "linear_futures")
        assert result is not None
        assert result["instrument_kind"] == "future"
        assert result["expiration_timestamp"] is not None

    def test_transforms_inverse_futures(self):
        raw_instrument = {
            "symbol": "BTCUSD_PERP",
            "baseAsset": "BTC",
            "quoteAsset": "USD",
            "marginAsset": "BTC",
            "contractType": "PERPETUAL",
            "filters": [],
        }
        result = transform_binance_instrument_to_canonical(raw_instrument, "inverse_futures")
        assert result is not None
        assert result["market_type"] == "inverse_futures"
        assert result["settlement_asset"] == "BTC"

    def test_returns_none_when_settlement_asset_missing(self):
        raw_instrument = {
            "symbol": "INVALID",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "filters": [],
        }
        with patch("trading_shared.exchanges.transformers.log"):
            result = transform_binance_instrument_to_canonical(raw_instrument, "linear_futures")
            assert result is None

    def test_handles_missing_tick_size(self):
        raw_instrument = {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "filters": [],
        }
        result = transform_binance_instrument_to_canonical(raw_instrument, "spot")
        assert result is not None
        assert result["tick_size"] is None

    def test_handles_expiration_timestamp_conversion(self):
        delivery_timestamp = 1688083200000
        raw_instrument = {
            "symbol": "BTCUSDT_230630",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "marginAsset": "USDT",
            "contractType": "CURRENT_QUARTER",
            "deliveryDate": delivery_timestamp,
            "filters": [],
        }
        result = transform_binance_instrument_to_canonical(raw_instrument, "linear_futures")
        assert result is not None
        assert result["expiration_timestamp"] is not None
        datetime.fromisoformat(result["expiration_timestamp"])

    def test_includes_raw_data(self):
        raw_instrument = {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "filters": [],
            "extra_field": "extra_value",
        }
        result = transform_binance_instrument_to_canonical(raw_instrument, "spot")
        assert result is not None
        assert result["data"] == raw_instrument
        assert result["data"]["extra_field"] == "extra_value"


class TestTransformDeribitInstrumentToCanonical:
    """Tests for transform_deribit_instrument_to_canonical function."""

    def test_transforms_perpetual_future(self):
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
        result = transform_deribit_instrument_to_canonical(raw_instrument)
        assert result["exchange"] == "deribit"
        assert result["instrument_name"] == "BTC-PERPETUAL"
        assert result["instrument_kind"] == "perpetual"
        assert result["base_asset"] == "BTC"
        assert result["settlement_asset"] == "BTC"
        assert result["market_type"] == "inverse_futures"

    def test_transforms_dated_future(self):
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
        result = transform_deribit_instrument_to_canonical(raw_instrument)
        assert result["instrument_kind"] == "future"
        assert result["expiration_timestamp"] is not None

    def test_transforms_option(self):
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
        result = transform_deribit_instrument_to_canonical(raw_instrument)
        assert result["instrument_kind"] == "option"
        assert result["market_type"] == "inverse_options"

    def test_handles_missing_settlement_currency(self):
        raw_instrument = {
            "instrument_name": "BTC-PERPETUAL",
            "kind": "future",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "tick_size": 0.5,
            "contract_size": 10,
            "instrument_type": "reversed",
        }
        result = transform_deribit_instrument_to_canonical(raw_instrument)
        assert result["settlement_asset"] == "BTC"

    def test_handles_unknown_kind(self):
        raw_instrument = {
            "instrument_name": "UNKNOWN-INSTRUMENT",
            "kind": "unknown_kind",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            "instrument_type": "linear",
        }
        result = transform_deribit_instrument_to_canonical(raw_instrument)
        assert result["instrument_kind"] == "unknown"

    def test_handles_missing_expiration_timestamp(self):
        raw_instrument = {
            "instrument_name": "BTC-PERPETUAL",
            "kind": "future",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            "instrument_type": "reversed",
        }
        result = transform_deribit_instrument_to_canonical(raw_instrument)
        assert result["expiration_timestamp"] is None

    def test_includes_raw_data(self):
        raw_instrument = {
            "instrument_name": "BTC-PERPETUAL",
            "kind": "future",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            "instrument_type": "reversed",
            "extra_field": "extra_value",
        }
        result = transform_deribit_instrument_to_canonical(raw_instrument)
        assert result["data"] == raw_instrument
        assert result["data"]["extra_field"] == "extra_value"

    def test_expiration_timestamp_conversion(self):
        expiration_ms = 1688083200000
        raw_instrument = {
            "instrument_name": "BTC-30JUN23",
            "kind": "future",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "settlement_currency": "BTC",
            "expiration_timestamp": expiration_ms,
            "instrument_type": "reversed",
        }
        result = transform_deribit_instrument_to_canonical(raw_instrument)
        assert result["expiration_timestamp"] is not None
        parsed_dt = datetime.fromisoformat(result["expiration_timestamp"])
        assert parsed_dt.tzinfo == timezone.utc
