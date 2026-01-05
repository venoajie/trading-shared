# src/trading_shared/config/universe_config.py

import os
from pathlib import Path
from typing import List, Dict, Set, Optional
import tomli
from pydantic import BaseModel, Field
from trading_engine_core.enums import MarketType

# --- MODELS ---

class HardFilterSettings(BaseModel):
    min_ingestion_volume: float = Field(default=100_000.0)
    blacklist_assets: Set[str] = Field(default_factory=set)
    ignore_stable_pairs: bool = Field(default=True)
    stablecoins: Set[str] = Field(default_factory=set)

class TierSettings(BaseModel):
    name: str = Field(default="UNKNOWN")
    definition: str
    store_ohlc: bool
    retention_ohlc: str
    raw_tick_retention: str

class WhitelistSettings(BaseModel):
    permanent_assets: Set[str] = Field(default_factory=set)

class ProfileSettings(BaseModel):
    description: str
    min_liquidity_tier: str
    required_exchanges: List[str]
    market_types: List[MarketType]

class UniverseConfig(BaseModel):
    filters: Dict[str, HardFilterSettings]
    tiers: Dict[str, TierSettings]
    whitelist: WhitelistSettings
    profiles: Dict[str, ProfileSettings]

# --- LOADER ---

def load_universe_config() -> UniverseConfig:
    config_path_str = os.getenv("UNIVERSE_CONFIG_PATH")
    if not config_path_str:
        config_path_str = "/app/config/universe.toml"
    
    config_path = Path(config_path_str)
    
    # Fallback for local testing
    if not config_path.is_file():
        local_fallback = Path("config/universe.toml")
        if local_fallback.is_file():
            config_path = local_fallback

    if not config_path.is_file():
        raise FileNotFoundError(f"Universe config not found at {config_path}")

    try:
        with open(config_path, "rb") as f:
            config_data = tomli.load(f)
        return UniverseConfig.model_validate(config_data)
    except Exception as e:
        raise RuntimeError(f"Failed to load universe config: {e}")