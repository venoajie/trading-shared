# src/shared_exchange_clients/public/client_map.py

from trading_shared.exchanges.public.deribit import DeribitPublicClient
from trading_shared.exchanges.public.binance import BinancePublicClient

CLIENT_MAP = {
    "deribit": DeribitPublicClient,
    "binance": BinancePublicClient,
}
