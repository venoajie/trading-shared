# src/trading_shared/exchanges/trading/binance_constants.py

from enum import Enum


class BinanceMarketType(Enum):
    """
    Enumeration for Binance market types to avoid magic strings.
    """

    SPOT = "spot"
    FUTURES_USD_M = "linear_futures"  # Also known as USDⓈ-M Futures
    FUTURES_COIN_M = "inverse_futures"  # Also known as COIN-M Futures
