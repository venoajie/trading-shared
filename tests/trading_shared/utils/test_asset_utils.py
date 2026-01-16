# tests/trading_shared/utils/test_asset_utils.py
"""Unit tests for asset_utils module."""

from trading_shared.utils.asset_utils import normalize_base_asset


class TestNormalizeBaseAsset:
    """Tests for normalize_base_asset function."""

    def test_removes_1000_prefix(self):
        assert normalize_base_asset("1000SHIB") == "SHIB"
        assert normalize_base_asset("1000PEPE") == "PEPE"

    def test_removes_10000_prefix(self):
        assert normalize_base_asset("10000FLOKI") == "FLOKI"

    def test_removes_100000_prefix(self):
        assert normalize_base_asset("100000DOGE") == "DOGE"

    def test_removes_1000000_prefix(self):
        assert normalize_base_asset("1000000XYZ") == "XYZ"

    def test_removes_up_suffix(self):
        assert normalize_base_asset("ADAUP") == "ADA"
        assert normalize_base_asset("BTCUP") == "BTC"

    def test_removes_down_suffix(self):
        assert normalize_base_asset("ADADOWN") == "ADA"
        assert normalize_base_asset("ETHDOWN") == "ETH"

    def test_no_modification_for_standard_asset(self):
        assert normalize_base_asset("BTC") == "BTC"
        assert normalize_base_asset("ETH") == "ETH"
        assert normalize_base_asset("USDT") == "USDT"

    def test_case_insensitive_normalization(self):
        assert normalize_base_asset("btc") == "BTC"
        assert normalize_base_asset("1000shib") == "SHIB"
        assert normalize_base_asset("adaup") == "ADA"

    def test_prefix_takes_precedence_over_suffix(self):
        result = normalize_base_asset("1000SHIBUP")
        assert result == "SHIB"

    def test_empty_string(self):
        assert normalize_base_asset("") == ""

    def test_only_prefix_no_asset_name(self):
        assert normalize_base_asset("1000") == ""

    def test_only_suffix_no_asset_name(self):
        assert normalize_base_asset("UP") == ""
        assert normalize_base_asset("DOWN") == ""

    def test_multiple_prefixes_only_first_removed(self):
        result = normalize_base_asset("10001000SHIB")
        assert result == "1000SHIB"

    def test_asset_containing_up_or_down_in_middle(self):
        assert normalize_base_asset("UPDOG") == "UPDOG"
        assert normalize_base_asset("DOWNTOWN") == "DOWNTOWN"
        assert normalize_base_asset("SETUP") == "SET"
