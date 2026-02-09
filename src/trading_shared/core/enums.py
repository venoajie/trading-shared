# src/trading_shared/core/enums.py

from enum import Enum


class MarketType(str, Enum):
    """
    The canonical, internal representation of all market types.
    This is the Single Source of Truth for the entire system.
    """

    SYSTEM_EVENT = "system_event"

    SPOT = "spot"
    SPOT_TICKER_24H = "spot_ticker_24h"

    LINEAR_FUTURES = "linear_futures"
    LINEAR_FUTURES_COMBO = "linear_futures_combo"
    LINEAR_OPTIONS = "linear_options"
    LINEAR_OPTIONS_COMBO = "linear_options_combo"
    INVERSE_FUTURES = "inverse_futures"
    INVERSE_FUTURES_COMBO = "inverse_futures_combo"
    INVERSE_OPTIONS = "inverse_options"
    INVERSE_OPTIONS_COMBO = "inverse_options_combo"
    UNKNOWN = "unknown"


class StorageMode(str, Enum):
    """Defines the authoritative storage backend for an asset's market data."""

    PERSISTENT = "POSTGRES"
    EPHEMERAL = "REDIS_BUFFER"
    UNKNOWN = "UNKNOWN"


class MoverPeriod(str, Enum):
    # Actionable (Strategist Triggers)
    M5 = "MINUTE_5"
    M15 = "MINUTE_15"

    # Contextual (Trend Filters)
    H2 = "HOUR_2"
    D1 = "DAY_1"
    W1 = "WEEK_1"
    MN1 = "MONTH_1"


class MoverNoticeType(str, Enum):
    PRICE_CHANGE = "PRICE_CHANGE"  # Rapid moves (Pump/Dump)
    VOLUME_PRICE = "VOLUME_PRICE"  # High Vol + Price Move (The best signal)
    BREAKTHROUGH = "PRICE_BREAKTHROUGH"  # Crossing daily/weekly highs/lows
    FLUCTUATION = "PRICE_FLUCTUATION"  # Volatility detection (Rise Again/Drop Back)


# Derived from the logs
MOVER_EVENT_MAP = {
    # --- PRICE CHANGE (The "Pump" Detector) ---
    # Trigger: Price moves X% in Y minutes
    "UP_1": {"desc": "Rapid Rise (Level 1)", "weight": 10},
    "UP_2": {"desc": "Rapid Rise (Level 2)", "weight": 20},
    "UP_3": {"desc": "Rapid Rise (Level 3)", "weight": 30},  # e.g. CHESS +16%
    "DOWN_1": {"desc": "Rapid Drop (Level 1)", "weight": -10},
    "DOWN_2": {"desc": "Rapid Drop (Level 2)", "weight": -20},
    "DOWN_3": {"desc": "Rapid Drop (Level 3)", "weight": -30},
    # --- VOLUME PRICE (The "Whale" Detector) ---
    # Trigger: High Volume + Price Move
    "HIGH_VOLUME_RISE_1": {"desc": "Volumetric Buy (L1)", "weight": 15},
    "HIGH_VOLUME_RISE_2": {"desc": "Volumetric Buy (L2)", "weight": 25},
    "HIGH_VOLUME_RISE_3": {"desc": "Volumetric Buy (L3)", "weight": 40},  # The strongest signal
    "HIGH_VOLUME_DROP_1": {"desc": "Volumetric Sell (L1)", "weight": -15},
    "HIGH_VOLUME_DROP_2": {"desc": "Volumetric Sell (L2)", "weight": -25},
    "HIGH_VOLUME_DROP_3": {"desc": "Volumetric Sell (L3)", "weight": -40},
    # --- BREAKTHROUGH (The "Level" Detector) ---
    "UP_BREAKTHROUGH": {"desc": "Broke Resistance", "weight": 5},
    "DOWN_BREAKTHROUGH": {"desc": "Broke Support", "weight": -5},
    # --- FLUCTUATION (The "Reversal" Detector) ---
    "RISE_AGAIN": {"desc": "Rebounding", "weight": 5},
    "DROP_BACK": {"desc": "Pullback", "weight": -5},
}
