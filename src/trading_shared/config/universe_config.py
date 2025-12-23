# src/trading_shared/config/universe_config.py

from pydantic import BaseModel, Field
from typing import List, Dict, Set

class InclusionRules(BaseModel):
    required_quote_assets: Set[str] = Field(default_factory=set)
    required_exchanges: Set[str] = Field(default_factory=set)

class ConstructionRules(BaseModel):
    required_market_types: Dict[str, bool] = Field(default_factory=dict)

class UniverseConfig(BaseModel):
    """
    A canonical model for defining the instrument trading universe.
    This provides a single, typed source of truth for all filtering and selection logic.
    """
    static_asset_blacklist: Set[str] = Field(default_factory=set)
    inclusion_rules: InclusionRules = Field(default_factory=InclusionRules)
    construction_rules: ConstructionRules = Field(default_factory=ConstructionRules)