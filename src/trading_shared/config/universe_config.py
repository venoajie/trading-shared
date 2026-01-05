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
    # 1. Check Env Var
    config_path_str = os.getenv("UNIVERSE_CONFIG_PATH")
    
    # 2. Check hardcoded container default
    if not config_path_str:
        config_path_str = "/app/config/universe.toml"
    
    path = Path(config_path_str)
    
    # 3. Last Resort: Local relative path for dev
    if not path.is_file():
        path = Path("config/universe.toml")

    if not path.is_file():
        raise FileNotFoundError(
            f"Universe config NOT FOUND. Tried: {config_path_str} and {path.absolute()}"
        )

    try:
        with open(path, "rb") as f:
            config_data = tomli.load(f)
        return UniverseConfig.model_validate(config_data)
    except Exception as e:
        # Wrap Pydantic validation errors with better context
        raise RuntimeError(f"UniverseConfig validation failed: {e}")