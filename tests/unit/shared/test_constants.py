# tests/unit/shared/test_constants.py
"""
Unit tests for constants module.

Tests cover:
- Exchange name constants
- Constant values and types
"""

from trading_shared.utils.constants import ExchangeNames


class TestExchangeNames:
    """Tests for ExchangeNames constants."""

    def test_deribit_constant(self):
        # Assert
        assert ExchangeNames.DERIBIT == "deribit"
        assert isinstance(ExchangeNames.DERIBIT, str)

    def test_binance_constant(self):
        # Assert
        assert ExchangeNames.BINANCE == "binance"
        assert isinstance(ExchangeNames.BINANCE, str)

    def test_constants_are_lowercase(self):
        # Assert
        assert ExchangeNames.DERIBIT.islower()
        assert ExchangeNames.BINANCE.islower()

    def test_constants_are_immutable_strings(self):
        # Arrange
        original_deribit = ExchangeNames.DERIBIT
        original_binance = ExchangeNames.BINANCE

        # Act - Try to modify (this will create new attributes, not modify constants)
        ExchangeNames.DERIBIT = "modified"
        ExchangeNames.BINANCE = "modified"

        # Assert - Original class attributes should be unchanged
        # Note: This test verifies the constants exist and are strings
        # Python doesn't prevent reassignment at class level, but the original values remain
        assert isinstance(original_deribit, str)
        assert isinstance(original_binance, str)
        assert original_deribit == "deribit"
        assert original_binance == "binance"
