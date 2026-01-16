# tests/unit/shared/test_universe_config.py
"""
Unit tests for the UniverseConfig loader and models.

Tests cover:
- Model validation with valid data
- Error handling for missing files
- Error handling for invalid TOML data
- Proper exception chaining with 'from' clause
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
from pydantic import ValidationError

from trading_shared.config.universe_config import (
    FilterSettings,
    StrategyMappingSettings,
    UniverseConfig,
    UniverseDefinition,
    load_universe_config,
)


class TestFilterSettings:
    """Tests for FilterSettings model."""

    def test_valid_filter_settings(self):
        # Arrange
        data = {
            "min_daily_volume_usd": 100000.0,
            "blacklist_assets": {"USDT", "BUSD"},
            "required_quote_assets": {"USD", "USDT"},
        }

        # Act
        settings = FilterSettings(**data)

        # Assert
        assert settings.min_daily_volume_usd == 100000.0
        assert settings.blacklist_assets == {"USDT", "BUSD"}
        assert settings.required_quote_assets == {"USD", "USDT"}

    def test_missing_required_field_raises_validation_error(self):
        # Arrange
        data = {
            "min_daily_volume_usd": 100000.0,
            # Missing blacklist_assets and required_quote_assets
        }

        # Act & Assert
        with pytest.raises(ValidationError):
            FilterSettings(**data)


class TestUniverseDefinition:
    """Tests for UniverseDefinition model."""

    def test_structural_pair_type(self):
        # Arrange
        data = {
            "type": "structural_pair",
            "materialized_as": "TABLE:tradable_assets",
            "description": "Test universe",
            "required_market_types": ["spot", "futures"],
            "primary_instrument": "BTC-USD",
        }

        # Act
        definition = UniverseDefinition(**data)

        # Assert
        assert definition.type == "structural_pair"
        assert definition.materialized_as == "TABLE:tradable_assets"
        assert definition.required_market_types == ["spot", "futures"]
        assert definition.primary_instrument == "BTC-USD"

    def test_filtered_instruments_type(self):
        # Arrange
        data = {
            "type": "filtered_instruments",
            "materialized_as": "VIEW:v_tradable_spots",
            "description": "Filtered spots",
            "filter_market_type": "spot",
        }

        # Act
        definition = UniverseDefinition(**data)

        # Assert
        assert definition.type == "filtered_instruments"
        assert definition.filter_market_type == "spot"
        assert definition.required_market_types is None


class TestStrategyMappingSettings:
    """Tests for StrategyMappingSettings model."""

    def test_valid_strategy_mapping(self):
        # Arrange
        data = {"consumes_universe": "tradable_spots"}

        # Act
        mapping = StrategyMappingSettings(**data)

        # Assert
        assert mapping.consumes_universe == "tradable_spots"


class TestUniverseConfig:
    """Tests for UniverseConfig model."""

    def test_valid_universe_config(self):
        # Arrange
        data = {
            "filters": {
                "min_daily_volume_usd": 100000.0,
                "blacklist_assets": {"USDT"},
                "required_quote_assets": {"USD"},
            },
            "universe_definitions": {
                "tradable_spots": {
                    "type": "filtered_instruments",
                    "materialized_as": "VIEW:v_tradable_spots",
                    "description": "Test",
                    "filter_market_type": "spot",
                }
            },
            "strategy_mapping": {
                "strategy1": {"consumes_universe": "tradable_spots"}
            },
        }

        # Act
        config = UniverseConfig(**data)

        # Assert
        assert config.filters.min_daily_volume_usd == 100000.0
        assert "tradable_spots" in config.universe_definitions
        assert "strategy1" in config.strategy_mapping


class TestLoadUniverseConfig:
    """Tests for load_universe_config function."""

    def test_load_from_env_path(self):
        # Arrange
        toml_content = """
[filters]
min_daily_volume_usd = 100000.0
blacklist_assets = ["USDT"]
required_quote_assets = ["USD"]

[universe_definitions.tradable_spots]
type = "filtered_instruments"
materialized_as = "VIEW:v_tradable_spots"
description = "Test"
filter_market_type = "spot"

[strategy_mapping.strategy1]
consumes_universe = "tradable_spots"
"""
        mock_file = mock_open(read_data=toml_content.encode())

        with patch.dict(os.environ, {"UNIVERSE_CONFIG_PATH": "/app/config/universe.toml"}):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("builtins.open", mock_file):
                    # Act
                    config = load_universe_config()

                    # Assert
                    assert isinstance(config, UniverseConfig)
                    assert config.filters.min_daily_volume_usd == 100000.0

    def test_fallback_to_local_path(self):
        # Arrange
        toml_content = """
[filters]
min_daily_volume_usd = 50000.0
blacklist_assets = []
required_quote_assets = ["USD"]

[universe_definitions.test]
type = "filtered_instruments"
materialized_as = "TABLE:test"
description = "Test"

[strategy_mapping.test_strategy]
consumes_universe = "test"
"""
        mock_file = mock_open(read_data=toml_content.encode())

        with patch.dict(os.environ, {}, clear=True):
            with patch("pathlib.Path.is_file") as mock_is_file:
                # First call returns False (env path), second returns True (local path)
                mock_is_file.side_effect = [False, True]
                with patch("builtins.open", mock_file):
                    # Act
                    config = load_universe_config()

                    # Assert
                    assert isinstance(config, UniverseConfig)
                    assert config.filters.min_daily_volume_usd == 50000.0

    def test_file_not_found_raises_error(self):
        # Arrange
        with patch.dict(os.environ, {}, clear=True):
            with patch("pathlib.Path.is_file", return_value=False):
                # Act & Assert
                with pytest.raises(FileNotFoundError, match="Universe config NOT FOUND"):
                    load_universe_config()

    def test_invalid_toml_raises_runtime_error_with_chaining(self):
        # Arrange
        invalid_toml = b"invalid toml content [[[["
        mock_file = mock_open(read_data=invalid_toml)

        with patch.dict(os.environ, {"UNIVERSE_CONFIG_PATH": "/app/config/universe.toml"}):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("builtins.open", mock_file):
                    # Act & Assert
                    with pytest.raises(RuntimeError, match="UniverseConfig validation failed") as exc_info:
                        load_universe_config()

                    # Verify exception chaining
                    assert exc_info.value.__cause__ is not None

    def test_validation_error_raises_runtime_error_with_chaining(self):
        # Arrange - Missing required fields
        toml_content = b"""
[filters]
min_daily_volume_usd = 100000.0
"""
        mock_file = mock_open(read_data=toml_content)

        with patch.dict(os.environ, {"UNIVERSE_CONFIG_PATH": "/app/config/universe.toml"}):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("builtins.open", mock_file):
                    # Act & Assert
                    with pytest.raises(RuntimeError, match="UniverseConfig validation failed") as exc_info:
                        load_universe_config()

                    # Verify exception chaining
                    assert exc_info.value.__cause__ is not None
