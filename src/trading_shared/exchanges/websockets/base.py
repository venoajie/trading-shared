# src/trading_shared/exchanges/websockets/base.py

# --- Built Ins ---
import asyncio
from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Set
import random

# --- Installed ---
from loguru import logger as log

# --- Local Application Imports ---
from ...repositories.market_data_repository import MarketDataRepository
from trading_engine_core.models import StreamMessage, MarketDefinition

class AbstractWsClient(ABC):
    """Abstract base class for exchange-specific WebSocket clients."""

    def __init__(
        self,
        market_definition: MarketDefinition,
        market_data_repo: MarketDataRepository,
        stream_name: str,
        shard_id: int = 0,
        total_shards: int = 1,
    ):
        """
        The constructor only accepts dependencies that are
        guaranteed to be used by ALL implementations. Exchange-specific
        dependencies are handled by the subclass constructors.
        """
        self.market_def = market_definition
        self.exchange_name = self.market_def.exchange
        self.market_data_repo = market_data_repo
        self.stream_name = stream_name
        self.shard_id = shard_id
        self.total_shards = total_shards

        if not stream_name:
            raise ValueError(f"[{self.exchange_name}] 'stream_name' must be provided.")

        self._active_channels: Set[str] = set()
        self._is_running = asyncio.Event()

    async def _maintain_subscriptions(self, poll_interval_s: int = 30):
        if not hasattr(self, 'system_state_repo') or not self.system_state_repo or not self.universe_state_key:
            log.warning(f"[{self.market_def.market_id}] Dynamic subscriptions disabled (missing config).")
            return

        log.info(f"[{self.market_def.market_id}] Starting subscription manager (Shard {self.shard_id + 1}/{self.total_shards}).")

        async def _update():
            try:
                universe = await self.system_state_repo.get_active_universe(self.universe_state_key)
                needed_channels = self._get_channels_from_universe(universe)

                if needed_channels != self._active_channels:
                    to_add = needed_channels - self._active_channels
                    to_remove = self._active_channels - needed_channels

                    if to_remove:
                        await self._send_unsubscribe(list(to_remove))
                    if to_add:
                        await self._send_subscribe(list(to_add))

                    self._active_channels = needed_channels
                    log.info(f"[{self.market_def.market_id}] Subscription state updated: {len(self._active_channels)} channels active.")
            except Exception as e:
                log.error(f"[{self.market_def.market_id}] Error during subscription update: {e}")

        await _update()

        while self._is_running.is_set():
            try:
                jitter = random.uniform(-0.1 * poll_interval_s, 0.1 * poll_interval_s)
                await asyncio.sleep(poll_interval_s + jitter)
                await _update()
            except asyncio.CancelledError:
                break

    @abstractmethod
    def _get_channels_from_universe(self, universe: List[str]) -> Set[str]:
        """Maps canonical universe symbols to exchange-specific channel names for this shard."""
        pass

    @abstractmethod
    async def _send_subscribe(self, channels: List[str]):
        pass

    @abstractmethod
    async def _send_unsubscribe(self, channels: List[str]):
        pass

    @abstractmethod
    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        yield

    @abstractmethod
    async def process_messages(self):
        pass

    @abstractmethod
    async def close(self):
        pass