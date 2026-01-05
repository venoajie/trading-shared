# src/trading_shared/config/universe_config.py

from typing import List, Dict, Set
from pydantic import BaseModel, Field
from trading_engine_core.enums import MarketType

class HardFilterSettings(BaseModel):
    min_daily_volume: float = Field(default=1_000_000.0)
    blacklist_assets: Set[str] = Field(default_factory=set)
    ignore_stable_pairs: bool = Field(default=True)
    stablecoins: Set[str] = Field(default_factory=set)

class TierSettings(BaseModel):
    definition: str
    ingest_ticks: bool
    store_ohlc: bool
    # Connects to Maintenance service pruning logic
    raw_tick_retention_period: str = Field(default="1 hour")

class ProfileSettings(BaseModel):
    description: str
    min_liquidity_tier: str
    required_exchanges: List[str]
    market_types: List[MarketType]

class UniverseConfig(BaseModel):
    """
    The Single Source of Truth for System Capacity and Filtering.
    Maps to universe.toml v3.0.
    """
    filters: Dict[str, HardFilterSettings]
    tiers: Dict[str, TierSettings]
    profiles: Dict[str, ProfileSettings]