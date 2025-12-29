# src/trading_shared/exchanges/public/client_map.py

from typing import Dict, List
from loguru import logger as log

from trading_shared.config.models import ExchangeSettings
from trading_shared.exchanges.public.base import PublicClient
from trading_shared.exchanges.public.deribit import DeribitPublicClient
from trading_shared.exchanges.public.binance import BinancePublicClient

# The CLIENT_MAP remains the central registry of available clients.
CLIENT_MAP: Dict[str, type[PublicClient]] = {
    "deribit": DeribitPublicClient,
    "binance": BinancePublicClient,
}

def get_all_public_clients(
    exchange_configs: Dict[str, ExchangeSettings]
) -> List[PublicClient]:
    """
    Instantiates all public exchange clients based on the provided configuration.

    Args:
        exchange_configs: A dictionary where keys are exchange names (e.g., 'deribit')
                          and values are ExchangeSettings objects.

    Returns:
        A list of initialized public client instances.
    """
    clients = []
    for name, settings in exchange_configs.items():
        client_class = CLIENT_MAP.get(name.lower())
        if client_class:
            try:
                clients.append(client_class(settings=settings))
                log.debug(f"Successfully instantiated public client for '{name}'.")
            except Exception as e:
                log.error(f"Failed to instantiate public client for '{name}': {e}")
        else:
            log.warning(f"No public client implementation found for exchange: '{name}'. Skipping.")
    return clients