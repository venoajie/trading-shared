# src/trading_shared/core/models.py


from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .enums import MarketType, StorageMode


class AppBaseModel(BaseModel):
    """Base model for all application data contracts."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )


# --- Canonical Model for Universe State ---


class ActiveLedgerEntry(AppBaseModel):
    """
    The canonical data contract for a single entry in the active trading universe.
    This is published by the Janitor and consumed by all downstream services.
    """

    # Static Instrument Details (from `instruments` table)
    instrument_id: int
    exchange: str
    instrument_name: str
    base_asset: str
    quote_asset: str
    market_type: MarketType

    # Dynamic Routing & Strategy Metadata (Calculated by Janitor)
    storage_mode: StorageMode = StorageMode.UNKNOWN
    # List of strategy profiles that this asset qualifies for.
    matched_profiles: list[str] = Field(default_factory=list)


# --- Configuration Models (Used by shared-config) ---


class MarketDefinition(AppBaseModel):
    """
    Defines the connection and subscription details for a specific market.
    This is the authoritative model.
    """

    market_id: str = Field(..., description="Unique identifier, e.g., 'deribit-main'.")
    exchange: str = Field(..., description="Exchange name, e.g., 'deribit'.")
    market_type: MarketType

    output_stream_name: str = Field(..., description="The Redis stream for this market's data, e.g., 'market:stream:binance:trades'.")

    mode: str = Field(default="live", description="Operational mode: 'live', 'paper', 'backtest'.")
    symbols: list[str] = Field(default_factory=list, description="Specific symbols to subscribe to.")
    ws_channels: list[str] = Field(default_factory=list, description="Raw WebSocket channel names.")
    ws_base_url: str | None = Field(default=None, description="Hydrated WebSocket URL.")
    rest_base_url: str | None = Field(default=None, description="Hydrated REST API URL.")


# --- Data Stream Models ---


class OHLCModel(AppBaseModel):
    """Standard Open-High-Low-Close candle data."""

    exchange: str | None = None
    instrument_name: str | None = None
    resolution: str | None = None
    tick: int = Field(..., description="Unix timestamp in milliseconds.")
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float = 0.0
    trade_count: int = 0
    taker_buy_volume: float = 0.0
    taker_sell_volume: float = 0.0
    open_interest: float = 0.0


class StreamMessage(AppBaseModel):
    """Standard wrapper for incoming WebSocket messages."""

    channel: str
    exchange: str
    timestamp: int
    data: dict[str, Any]


# --- Trading Entity Models ---


class InstrumentModel(AppBaseModel):
    """A validated model for a financial instrument."""

    exchange: str
    instrument_name: str
    market_type: str
    instrument_kind: str
    base_asset: str
    quote_asset: str
    settlement_asset: str
    settlement_period: str | None = None
    tick_size: float | None = None
    contract_size: float | None = None
    expiration_timestamp: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict, description="Raw exchange payload.")


class OrderModel(AppBaseModel):
    """Represents the state of an order in the system."""

    order_id: str
    instrument_name: str
    order_state: str
    direction: str
    price: float
    amount: float
    label: str | None = None
    trade_id: str | None = None
    take_profit: str | None = None
    stop_loss: str | None = None
    timestamp: int
    last_update_timestamp: int
    creation_timestamp: int
    model_config = ConfigDict(extra="allow")


class MarginCalculationResult(AppBaseModel):
    """Output of PME/Risk calculations."""

    initial_margin: float
    maintenance_margin: float
    is_valid: bool
    error_message: str | None = None


# --- Event Sourcing Models (The Immutable Log) ---


class BaseEvent(AppBaseModel):
    """Abstract base for event-sourced activities."""

    pass


class CycleCreatedEvent(BaseEvent):
    strategy_name: str
    instrument_ticker: str
    initial_parameters: dict[str, Any]


class OrderSentEvent(BaseEvent):
    order_id: str
    order_type: Literal["MARKET", "LIMIT", "STOP"]
    side: Literal["BUY", "SELL"]
    quantity: float
    price: float | None = None


class OrderFilledEvent(BaseEvent):
    order_id: str
    fill_price: float
    fill_quantity: float
    commission: float = 0.0
    timestamp: datetime


class CycleStateUpdatedEvent(BaseEvent):
    """
    An event representing an internal state transition of a TradeCycle.
    This makes the application's internal "thinking" process an auditable event.
    """

    previous_status: str
    new_status: str
    reason: str


class CycleClosedEvent(BaseEvent):
    reason: str
    final_pnl: float


# --- Notification Models ---


class TradeNotification(AppBaseModel):
    """A structured model for a trade notification."""

    direction: str
    amount: float
    instrument_name: str
    price: float


class TradeNotificationEvent(AppBaseModel):
    """
    Event published when a private trade execution occurs.
    """

    event_type: str = "TRADE_EXECUTION"
    instrument_name: str
    direction: str
    amount: float
    price: float


class OrderModificationEvent(AppBaseModel):
    """
    Event published when a private order modification occurs.
    """

    event_type: str = "ORDER_MODIFICATION"
    exchange: str
    instrument_name: str
    direction: str
    amount: float
    price: float


class SystemAlert(AppBaseModel):
    """A structured model for a system-level alert."""

    component: str
    event: str
    details: str
    severity: Literal["INFO", "WARNING", "CRITICAL"] = "CRITICAL"


class TakerMetrics(BaseModel):
    """Real-time microstructure metrics."""

    symbol: str
    timestamp: float
    tbsr_5m: float = Field(default=1.0)
    net_delta_1m: float = Field(default=0.0)
    taker_buy_vol_5m: float = 0.0
    taker_sell_vol_5m: float = 0.0
    aggression_score: float = 50.0


class MarketContext(BaseModel):
    """The 6-Layer Context Grid."""

    regime: str = "NEUTRAL"
    liquidity_tier: str = "TIER_2"
    session_name: str = "UNKNOWN"
    is_weekend: bool = False
    is_low_liquidity_hour: bool = False
    pump_phase: str = "UNKNOWN"
    whale_activity: str = "UNKNOWN"
    sentiment_score: float = 0.5


class SignalEvent(BaseModel):
    timestamp: float
    strategy_name: str
    symbol: str
    exchange: str
    signal_type: str
    strength: float
    metadata: dict[str, Any]


class CorrelationMatrix(BaseModel):
    """Statistical relationship snapshot."""

    reference_symbol: str = "BTC"
    correlation_1h: float = 0.0
    correlation_24h: float = 0.0
    beta: float = 1.0
    is_significant: bool = False
    t_score: float = 0.0


class EnhancedSignalEvent(BaseModel):
    """
    Signal Event enriched with Context, Metrics, and Visual Data.
    Acts as the 'Heavy' payload for Decision and Notification services.
    """

    timestamp: float
    strategy_name: str
    symbol: str
    exchange: str
    signal_type: str
    strength: float

    # Enriched Payload
    metrics: TakerMetrics | None = None
    context: MarketContext | None = None

    # Statistical Context
    correlation: CorrelationMatrix | None = None

    # Visual Context (Snapshot of recent price action)
    candles: list[OHLCModel] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)

    # Benchmark candle data.
    # It is optional because signals for BTC itself or system alerts won't have it.
    benchmark_candles: list[OHLCModel] | None = None
