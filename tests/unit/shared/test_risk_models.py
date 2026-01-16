# tests/unit/shared/test_risk_models.py

import pytest
from pydantic import ValidationError

from trading_shared.risk.models import (
    MarginCalculationResult,
    PMEGeneralCurrency,
    PMEParams,
    PMEParamsCurrency,
)


class TestPMEParamsCurrency:
    """Tests for PMEParamsCurrency model."""

    def test_valid_initialization(self):
        # Arrange
        data = {
            "price_range": 0.1,
            "volatility_range_up": 0.2,
            "volatility_range_down": 0.15,
            "min_volatility_for_shock_up": 0.05,
            "short_term_vega_power": 1.5,
            "long_term_vega_power": 2.0,
            "extended_table_factor": 1.2,
            "delta_total_liquid_shock_threshold": 0.3,
            "max_delta_shock": 0.5,
        }

        # Act
        params = PMEParamsCurrency(**data)

        # Assert
        assert params.price_range == 0.1
        assert params.volatility_range_up == 0.2
        assert params.max_delta_shock == 0.5

    def test_missing_required_field_raises_error(self):
        # Arrange
        data = {
            "price_range": 0.1,
            # Missing other required fields
        }

        # Act & Assert
        with pytest.raises(ValidationError):
            PMEParamsCurrency(**data)


class TestPMEGeneralCurrency:
    """Tests for PMEGeneralCurrency model."""

    def test_valid_initialization_with_alias(self):
        # Arrange
        data = {
            "min_expiry_delta_shock": 0.1,
            "annualised_%_move_risk": 0.25,
        }

        # Act
        params = PMEGeneralCurrency(**data)

        # Assert
        assert params.min_expiry_delta_shock == 0.1
        assert params.annualised_move_risk == 0.25

    def test_futures_contingency_optional(self):
        # Arrange
        data = {
            "min_expiry_delta_shock": 0.1,
            "annualised_%_move_risk": 0.25,
            "futures_contingency": 0.006,
        }

        # Act
        params = PMEGeneralCurrency(**data)

        # Assert
        assert params.futures_contingency == 0.006

    def test_futures_contingency_defaults_to_none(self):
        # Arrange
        data = {
            "min_expiry_delta_shock": 0.1,
            "annualised_%_move_risk": 0.25,
        }

        # Act
        params = PMEGeneralCurrency(**data)

        # Assert
        assert params.futures_contingency is None


class TestPMEParams:
    """Tests for PMEParams model."""

    def test_valid_initialization(self):
        # Arrange
        data = {
            "BTC_USD": {
                "price_range": 0.1,
                "volatility_range_up": 0.2,
                "volatility_range_down": 0.15,
                "min_volatility_for_shock_up": 0.05,
                "short_term_vega_power": 1.5,
                "long_term_vega_power": 2.0,
                "extended_table_factor": 1.2,
                "delta_total_liquid_shock_threshold": 0.3,
                "max_delta_shock": 0.5,
            },
            "ETH_USD": {
                "price_range": 0.12,
                "volatility_range_up": 0.22,
                "volatility_range_down": 0.17,
                "min_volatility_for_shock_up": 0.06,
                "short_term_vega_power": 1.6,
                "long_term_vega_power": 2.1,
                "extended_table_factor": 1.3,
                "delta_total_liquid_shock_threshold": 0.35,
                "max_delta_shock": 0.55,
            },
            "currencies": [{"name": "BTC"}, {"name": "ETH"}],
        }

        # Act
        params = PMEParams(**data)

        # Assert
        assert params.btc_usd.price_range == 0.1
        assert params.eth_usd.price_range == 0.12
        assert len(params.currencies) == 2

    def test_restructure_from_api_format(self):
        # Arrange
        api_data = {
            "general": {
                "currency_pairs": {
                    "BTC_USD": {
                        "price_range": 0.1,
                        "volatility_range_up": 0.2,
                        "volatility_range_down": 0.15,
                        "min_volatility_for_shock_up": 0.05,
                        "short_term_vega_power": 1.5,
                        "long_term_vega_power": 2.0,
                        "extended_table_factor": 1.2,
                        "delta_total_liquid_shock_threshold": 0.3,
                        "max_delta_shock": 0.5,
                    },
                    "ETH_USD": {
                        "price_range": 0.12,
                        "volatility_range_up": 0.22,
                        "volatility_range_down": 0.17,
                        "min_volatility_for_shock_up": 0.06,
                        "short_term_vega_power": 1.6,
                        "long_term_vega_power": 2.1,
                        "extended_table_factor": 1.3,
                        "delta_total_liquid_shock_threshold": 0.35,
                        "max_delta_shock": 0.55,
                    },
                },
                "currencies": [{"name": "BTC"}],
            }
        }

        # Act
        params = PMEParams(**api_data)

        # Assert
        assert params.btc_usd.price_range == 0.1
        assert params.eth_usd.price_range == 0.12
        assert len(params.currencies) == 1

    def test_futures_contingency_rate_default(self):
        # Arrange
        data = {
            "BTC_USD": {
                "price_range": 0.1,
                "volatility_range_up": 0.2,
                "volatility_range_down": 0.15,
                "min_volatility_for_shock_up": 0.05,
                "short_term_vega_power": 1.5,
                "long_term_vega_power": 2.0,
                "extended_table_factor": 1.2,
                "delta_total_liquid_shock_threshold": 0.3,
                "max_delta_shock": 0.5,
            },
            "ETH_USD": {
                "price_range": 0.12,
                "volatility_range_up": 0.22,
                "volatility_range_down": 0.17,
                "min_volatility_for_shock_up": 0.06,
                "short_term_vega_power": 1.6,
                "long_term_vega_power": 2.1,
                "extended_table_factor": 1.3,
                "delta_total_liquid_shock_threshold": 0.35,
                "max_delta_shock": 0.55,
            },
            "currencies": [],
        }

        # Act
        params = PMEParams(**data)

        # Assert
        assert params.futures_contingency_rate == 0.006


class TestMarginCalculationResult:
    """Tests for MarginCalculationResult model."""

    def test_valid_result(self):
        # Arrange
        data = {
            "initial_margin": 1000.0,
            "maintenance_margin": 500.0,
            "worst_case_pnl": -200.0,
            "futures_contingency": 50.0,
            "is_valid": True,
        }

        # Act
        result = MarginCalculationResult(**data)

        # Assert
        assert result.initial_margin == 1000.0
        assert result.maintenance_margin == 500.0
        assert result.worst_case_pnl == -200.0
        assert result.futures_contingency == 50.0
        assert result.is_valid is True
        assert result.error_message is None

    def test_invalid_result_with_error(self):
        # Arrange
        data = {
            "initial_margin": 0.0,
            "maintenance_margin": 0.0,
            "is_valid": False,
            "error_message": "API call failed",
        }

        # Act
        result = MarginCalculationResult(**data)

        # Assert
        assert result.is_valid is False
        assert result.error_message == "API call failed"

    def test_optional_fields_default_to_zero_or_none(self):
        # Arrange
        data = {
            "initial_margin": 1000.0,
            "maintenance_margin": 500.0,
            "is_valid": True,
        }

        # Act
        result = MarginCalculationResult(**data)

        # Assert
        assert result.worst_case_pnl == 0.0
        assert result.futures_contingency == 0.0
        assert result.error_message is None
