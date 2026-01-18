# tests/unit/shared/test_mappers.py
"""
Unit tests for exchange mappers.

Tests cover:
- Deribit market type mapping
- Binance market type mapping
- Edge cases and unknown types
"""

from trading_shared.core.enums import MarketType
from trading_shared.exchanges.mappers import get_canonical_market_type


class TestGetCanonicalMarketTypeDeribit:
    """Tests for get_canonical_market_type with Deribit exchange."""

    def test_deribit_inverse_futures(self):
        # Arrange
        raw_instrument = {
            "kind": "future",
            "instrument_type": "reversed",
        }

        # Act
        result = get_canonical_market_type("deribit", raw_instrument)

        # Assert
        assert result == MarketType.INVERSE_FUTURES

    def test_deribit_inverse_futures_combo(self):
        # Arrange
        raw_instrument = {
            "kind": "future_combo",
            "instrument_type": "reversed",
        }

        # Act
        result = get_canonical_market_type("deribit", raw_instrument)

        # Assert
        assert result == MarketType.INVERSE_FUTURES_COMBO

    def test_deribit_inverse_options(self):
        # Arrange
        raw_instrument = {
            "kind": "option",
            "instrument_type": "reversed",
        }

        # Act
        result = get_canonical_market_type("deribit", raw_instrument)

        # Assert
        assert result == MarketType.INVERSE_OPTIONS

    def test_deribit_inverse_options_combo(self):
        # Arrange
        raw_instrument = {
            "kind": "option_combo",
            "instrument_type": "reversed",
        }

        # Act
        result = get_canonical_market_type("deribit", raw_instrument)

        # Assert
        assert result == MarketType.INVERSE_OPTIONS_COMBO

    def test_deribit_linear_futures(self):
        # Arrange
        raw_instrument = {
            "kind": "future",
            "instrument_type": "linear",
        }

        # Act
        result = get_canonical_market_type("deribit", raw_instrument)

        # Assert
        assert result == MarketType.LINEAR_FUTURES

    def test_deribit_linear_futures_combo(self):
        # Arrange
        raw_instrument = {
            "kind": "future_combo",
            "instrument_type": "linear",
        }

        # Act
        result = get_canonical_market_type("deribit", raw_instrument)

        # Assert
        assert result == MarketType.LINEAR_FUTURES_COMBO

    def test_deribit_linear_options(self):
        # Arrange
        raw_instrument = {
            "kind": "option",
            "instrument_type": "linear",
        }

        # Act
        result = get_canonical_market_type("deribit", raw_instrument)

        # Assert
        assert result == MarketType.LINEAR_OPTIONS

    def test_deribit_linear_options_combo(self):
        # Arrange
        raw_instrument = {
            "kind": "option_combo",
            "instrument_type": "linear",
        }

        # Act
        result = get_canonical_market_type("deribit", raw_instrument)

        # Assert
        assert result == MarketType.LINEAR_OPTIONS_COMBO

    def test_deribit_spot(self):
        # Arrange
        raw_instrument = {
            "kind": "spot",
            "instrument_type": "linear",
        }

        # Act
        result = get_canonical_market_type("deribit", raw_instrument)

        # Assert
        assert result == MarketType.SPOT

    def test_deribit_unknown_type(self):
        # Arrange
        raw_instrument = {
            "kind": "unknown_kind",
            "instrument_type": "unknown_type",
        }

        # Act
        result = get_canonical_market_type("deribit", raw_instrument)

        # Assert
        assert result == MarketType.UNKNOWN


class TestGetCanonicalMarketTypeBinance:
    """Tests for get_canonical_market_type with Binance exchange."""

    def test_binance_spot_with_hint(self):
        # Arrange
        raw_instrument = {"symbol": "BTCUSDT"}

        # Act
        result = get_canonical_market_type("binance", raw_instrument, source_hint="spot")

        # Assert
        assert result == MarketType.SPOT

    def test_binance_linear_futures_with_hint(self):
        # Arrange
        raw_instrument = {"symbol": "BTCUSDT"}

        # Act
        result = get_canonical_market_type("binance", raw_instrument, source_hint="linear_futures")

        # Assert
        assert result == MarketType.LINEAR_FUTURES

    def test_binance_inverse_futures_with_hint(self):
        # Arrange
        raw_instrument = {"symbol": "BTCUSD_PERP"}

        # Act
        result = get_canonical_market_type("binance", raw_instrument, source_hint="inverse_futures")

        # Assert
        assert result == MarketType.INVERSE_FUTURES

    def test_binance_without_hint_returns_unknown(self):
        # Arrange
        raw_instrument = {"symbol": "BTCUSDT"}

        # Act
        result = get_canonical_market_type("binance", raw_instrument)

        # Assert
        assert result == MarketType.UNKNOWN

    def test_binance_with_invalid_hint_returns_unknown(self):
        # Arrange
        raw_instrument = {"symbol": "BTCUSDT"}

        # Act
        result = get_canonical_market_type("binance", raw_instrument, source_hint="invalid_hint")

        # Assert
        assert result == MarketType.UNKNOWN


class TestGetCanonicalMarketTypeEdgeCases:
    """Tests for edge cases in get_canonical_market_type."""

    def test_unknown_exchange_returns_unknown(self):
        # Arrange
        raw_instrument = {"kind": "future", "instrument_type": "linear"}

        # Act
        result = get_canonical_market_type("unknown_exchange", raw_instrument)

        # Assert
        assert result == MarketType.UNKNOWN

    def test_empty_instrument_data_returns_unknown(self):
        # Arrange
        raw_instrument = {}

        # Act
        result = get_canonical_market_type("deribit", raw_instrument)

        # Assert
        assert result == MarketType.UNKNOWN

    def test_missing_kind_field_returns_unknown(self):
        # Arrange
        raw_instrument = {"instrument_type": "linear"}

        # Act
        result = get_canonical_market_type("deribit", raw_instrument)

        # Assert
        assert result == MarketType.UNKNOWN

    def test_missing_instrument_type_field_returns_unknown(self):
        # Arrange
        raw_instrument = {"kind": "future"}

        # Act
        result = get_canonical_market_type("deribit", raw_instrument)

        # Assert
        assert result == MarketType.UNKNOWN

    def test_case_sensitivity_in_exchange_name(self):
        # Arrange
        raw_instrument = {"symbol": "BTCUSDT"}

        # Act
        result = get_canonical_market_type("BINANCE", raw_instrument, source_hint="spot")

        # Assert - Should return UNKNOWN as exchange name is case-sensitive
        assert result == MarketType.UNKNOWN
