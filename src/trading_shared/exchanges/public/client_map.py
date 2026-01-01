# src/trading_shared/exchanges/public/client_map.py

# --- Installed ---

import aiohttp
from loguru import logger as log

# --- Shared Library Imports ---
from trading_shared.config.models import ExchangeSettings

from .base import PublicClient
from .binance import BinancePublicClient
from .deribit import DeribitPublicClient

# --- Client Mapping ---
CLIENT_MAP = {
    "deribit": DeribitPublicClient,
    "binance": BinancePublicClient,
}


def get_all_public_clients(
    configs: dict[str, ExchangeSettings], http_session: aiohttp.ClientSession
) -> list[PublicClient]:
    """
    Factory function to instantiate all configured public exchange clients.
    """
    clients = []
    for exchange_name, settings in configs.items():
        ClientClass = CLIENT_MAP.get(exchange_name)
        if not ClientClass:
            log.warning(f"No public client class found for exchange: {exchange_name}")
            continue
        try:
            # Pass the http_session and exchange_name to the client constructor.
            client = ClientClass(
                settings=settings,
                http_session=http_session,
                exchange_name=exchange_name,
            )
            clients.append(client)
        except Exception as e:
            log.error(f"Failed to instantiate public client for '{exchange_name}': {e}")
    return clients
