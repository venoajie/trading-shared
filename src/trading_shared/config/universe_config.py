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


class StorageTierSettings(BaseModel):
    storage_mode: str
    buffer_window_minutes: int | None = None
    description: str


class StrategyProfileSettings(BaseModel):
    description: str
    required_storage_tier: str


class UniverseConfig(BaseModel):
    filters: FilterSettings
    storage_tiers: dict[str, StorageTierSettings]
    strategy_profiles: dict[str, StrategyProfileSettings]


# --- LOADER ---


def load_universe_config() -> UniverseConfig:
    # (Loader function remains the same, it's robust)
    config_path_str = os.getenv("UNIVERSE_CONFIG_PATH", "/app/config/universe.toml")
    path = Path(config_path_str)
    if not path.is_file():
        path = Path("config/universe.toml")  # Local dev fallback
    if not path.is_file():
        raise FileNotFoundError(f"Universe config NOT FOUND. Tried: {config_path_str} and {path.absolute()}")

    try:
        with open(path, "rb") as f:
            config_data = tomli.load(f)
        return UniverseConfig.model_validate(config_data)
    except Exception as e:
        raise RuntimeError(f"UniverseConfig validation failed for {path.absolute()}: {e}")
