# src/trading_shared/config/universe_config.py

from pydantic import BaseModel, Field
from trading_engine_core.enums import MarketType


class HardFilterSettings(BaseModel):
    min_ingestion_volume: float = Field(default=100_000.0)
    blacklist_assets: set[str] = Field(default_factory=set)
    ignore_stable_pairs: bool = Field(default=True)
    stablecoins: set[str] = Field(default_factory=set)


class TierSettings(BaseModel):
    name: str
    definition: str
    store_ohlc: bool
    retention_ohlc: str
    raw_tick_retention: str


class WhitelistSettings(BaseModel):
    permanent_assets: set[str] = Field(default_factory=set)


class ProfileSettings(BaseModel):
    description: str
    min_liquidity_tier: str
    required_exchanges: list[str]
    market_types: list[MarketType]


class UniverseConfig(BaseModel):
    filters: dict[str, HardFilterSettings]
    tiers: dict[str, TierSettings]
    whitelist: WhitelistSettings
    profiles: dict[str, ProfileSettings]
