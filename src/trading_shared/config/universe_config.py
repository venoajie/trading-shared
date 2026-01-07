# src/trading_shared/config/universe_config.py

import os
from pathlib import Path

import tomli
from pydantic import BaseModel

# --- MODELS ---


class FilterSettings(BaseModel):
    min_daily_volume_usd: float
    blacklist_assets: set[str]
    required_quote_assets: set[str]


class UniverseDefinition(BaseModel):
    """
    Defines the blueprint for a single universe.
    Consumed by the Janitor's UniverseMaterializer.
    """

    type: str  # e.g., "structural_pair" or "filtered_instruments"
    materialized_as: str  # e.g., "TABLE:tradable_assets" or "VIEW:v_tradable_spots"
    description: str

    # Fields for 'structural_pair' type
    required_market_types: list[str] | None = None
    primary_instrument: str | None = None

    # Fields for 'filtered_instruments' type
    filter_market_type: str | None = None


class StrategyMappingSettings(BaseModel):
    consumes_universe: str


class UniverseConfig(BaseModel):
    filters: FilterSettings
    universe_definitions: dict[str, UniverseDefinition]
    strategy_mapping: dict[str, StrategyMappingSettings]


# --- LOADER ---
def load_universe_config() -> UniverseConfig:
    """
    Loads and validates the universe.toml configuration file.
    """
    config_path_str = os.getenv("UNIVERSE_CONFIG_PATH", "/app/config/universe.toml")
    path = Path(config_path_str)

    if not path.is_file():
        # Fallback for local development
        path = Path("config/universe.toml")

    if not path.is_file():
        raise FileNotFoundError(f"Universe config NOT FOUND. Tried: {config_path_str} and {path.absolute()}")

    try:
        with open(path, "rb") as f:
            config_data = tomli.load(f)
        return UniverseConfig.model_validate(config_data)
    except Exception as e:
        raise RuntimeError(f"UniverseConfig validation failed for {path.absolute()}: {e}")
