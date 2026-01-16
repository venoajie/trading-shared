# tests/trading_shared/utils/test_constants.py

from trading_shared.utils.constants import ExchangeNames


class TestExchangeNames:
    """Tests for ExchangeNames constants."""

    def test_deribit_constant(self):
        assert ExchangeNames.DERIBIT == "deribit"
        assert isinstance(ExchangeNames.DERIBIT, str)

    def test_binance_constant(self):
        assert ExchangeNames.BINANCE == "binance"
        assert isinstance(ExchangeNames.BINANCE, str)

    def test_constants_are_lowercase(self):
        assert ExchangeNames.DERIBIT.islower()
        assert ExchangeNames.BINANCE.islower()

    def test_constants_are_immutable_strings(self):
        original_deribit = ExchangeNames.DERIBIT
        original_binance = ExchangeNames.BINANCE
        ExchangeNames.DERIBIT = "modified"
        ExchangeNames.BINANCE = "modified"
        assert isinstance(original_deribit, str)
        assert isinstance(original_binance, str)
        assert original_deribit == "deribit"
        assert original_binance == "binance"
