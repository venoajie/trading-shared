# src\trading_shared\risk\models.py

# --- Built Ins  ---
from pydantic import BaseModel, Field, model_validator
from typing import Dict, Any, List, Optional


class PMEParamsCurrency(BaseModel):
    price_range: float
    volatility_range_up: float
    volatility_range_down: float
    min_volatility_for_shock_up: float
    short_term_vega_power: float
    long_term_vega_power: float
    extended_table_factor: float
    delta_total_liquid_shock_threshold: float
    max_delta_shock: float


class PMEGeneralCurrency(BaseModel):
    min_expiry_delta_shock: float = Field(alias="min_expiry_delta_shock")
    annualised_move_risk: float = Field(alias="annualised_%_move_risk")
    futures_contingency: Optional[float] = None


class PMEParams(BaseModel):
    btc_usd: PMEParamsCurrency = Field(alias="BTC_USD")
    eth_usd: PMEParamsCurrency = Field(alias="ETH_USD")
    currencies: List[Dict[str, Any]]
    futures_contingency_rate: float = 0.006

    @model_validator(mode="before")
    @classmethod
    def restructure_from_api(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "general" in data and isinstance(data["general"], dict):
            general_data = data["general"]
            restructured = {}
            if "currency_pairs" in general_data:
                restructured.update(general_data["currency_pairs"])
            if "currencies" in general_data:
                restructured["currencies"] = general_data["currencies"]
            return restructured
        return data


class MarginCalculationResult(BaseModel):
    initial_margin: float
    maintenance_margin: float
    worst_case_pnl: Optional[float] = 0.0
    futures_contingency: Optional[float] = 0.0
    is_valid: bool
    error_message: Optional[str] = None
