# src/trading_shared/config/universe_config.py


from pydantic import BaseModel, Field
from trading_engine_core.enums import MarketType


class InclusionRules(BaseModel):
    required_quote_assets: set[str] = Field(default_factory=set)
    required_exchanges: set[str] = Field(default_factory=set)


class ConstructionRules(BaseModel):
    # The dictionary key is now strictly typed to the MarketType Enum.
    # Pydantic will handle the validation automatically.
    required_market_types: dict[MarketType, bool] = Field(default_factory=dict)


class UniverseConfig(BaseModel):
    """
    A canonical model for defining the instrument trading universe.
    This provides a single, typed source of truth for all filtering and selection logic.
    """

    static_asset_blacklist: set[str] = Field(default_factory=set)
    inclusion_rules: InclusionRules = Field(default_factory=InclusionRules)
    construction_rules: ConstructionRules = Field(default_factory=ConstructionRules)
