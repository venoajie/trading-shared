# src/trading_shared/exchanges/websockets/binance.py

# --- Built Ins ---
import asyncio
from collections.abc import AsyncGenerator
from typing import Set, Dict, Any

# --- Installed ---
import orjson
import websockets
from loguru import logger as log

# --- Shared Library Imports ---
from trading_engine_core.models import MarketDefinition, StreamMessage

# --- Local Application Imports ---
from ...config.models import ExchangeSettings
from ...repositories.instrument_repository import InstrumentRepository
from ...repositories.market_data_repository import MarketDataRepository
from ...repositories.system_state_repository import SystemStateRepository
from .base import AbstractWsClient


class BinanceWsClient(AbstractWsClient):
    """A self-managing, sharded WebSocket client for Binance public trade data."""

    def __init__(
        self,
        market_definition: MarketDefinition,
        market_data_repo: MarketDataRepository,
        instrument_repo: InstrumentRepository,
        system_state_repo: SystemStateRepository,
        universe_state_key: str,
        settings: ExchangeSettings,
        shard_id: int,
        total_shards: int,
    ):
        super().__init__(
            market_definition,
            market_data_repo,
            shard_id=shard_id,
            total_shards=total_shards,
        )
        self.instrument_repo = instrument_repo
        self.system_state_repo = system_state_repo
        self.universe_state_key = universe_state_key
        self.settings = settings
        self.ws_connection_url = self.market_def.ws_base_url
        self._ws: websockets.WebSocketClientProtocol | None = None
        self.shard_num_for_log = self.shard_id + 1

        # Maps Raw (Exchange) Symbol -> Canonical (System) Symbol
        self._symbol_map: Dict[str, str] = {}

    async def _get_channels_from_universe(self, universe: list[dict[str, Any]]) -> Set[str]:
        """
        Parses the Flat Ledger (Janitor v4.2) to extract symbols for this client's specific shard.
        Matches based on 'exchange' and 'market_type'.
        """
        my_targets = set()
        temp_map = {}

        # Determine strict or loose matching based on MarketDefinition
        target_exchange = self.exchange_name.lower()
        target_type = self.market_def.market_type.lower() if self.market_def.market_type else None

        for entry in universe:
            # 1. Filter by Exchange
            entry_exchange = entry.get("exchange", "").lower()
            if entry_exchange != target_exchange:
                continue

            # 2. Filter by Market Type (if applicable)
            # This ensures the Spot client doesn't try to subscribe to Futures symbols and vice versa.
            entry_type = entry.get("market_type", "").lower()
            if target_type and target_type not in entry_type and entry_type not in target_type:
                # Loose match: "SPOT" matches "spot"
                continue

            # 3. Extract Symbol
            # Janitor v4.2 output uses 'symbol' alias for instrument_name
            symbol = entry.get("symbol") or entry.get("instrument_name")
            if not symbol:
                continue

            my_targets.add(symbol)

            # 4. Map Raw -> Canonical
            # Binance Raw often excludes hyphens (BTCUSDT vs BTC-USDT)
            # We assume the universe contains the Canonical ID (BTC-USDT)
            raw_symbol = symbol.replace("-", "").upper()
            temp_map[raw_symbol] = symbol

        # Update the instance map for Ticker Cache lookups
        self._symbol_map.update(temp_map)

        # 5. Apply Sharding
        # Deterministic sharding based on sorted symbol list
        sorted_targets = sorted(list(my_targets))
        sharded_targets = {sym for i, sym in enumerate(sorted_targets) if i % self.total_shards == self.shard_id}

        # 6. Generate Channel Names
        channels = set()
        for canonical in sharded_targets:
            raw = canonical.replace("-", "").lower()
            channels.add(f"{raw}@trade")
            channels.add(f"{raw}@ticker")

        return channels

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """
        Manages a single, finite connection based on the current
        active channels. Exits upon disconnection and provides detailed 404 logging.
        """
        if not self._active_channels:
            log.warning(f"[{self.market_def.market_id}] No channels to connect to (Universe Empty or Filter Mismatch).")
            return

        sorted_channels = sorted(self._active_channels)
        # Binance URL limit safety (though 1024 chars is usually the limit, shards handle this)
        url_path = "/stream?streams=" + "/".join(sorted_channels)
        full_url = self.ws_connection_url + url_path

        try:
            async with websockets.connect(full_url, ping_interval=180) as ws:
                self._ws = ws
                log.success(f"[{self.market_def.market_id}_{self.shard_num_for_log}] Connected with {len(sorted_channels)} channels.")

                async for message in ws:
                    try:
                        data = orjson.loads(message)
                        payload = data.get("data")
                        stream = data.get("stream")

                        if payload and stream:
                            # 1. Routing: Trade Stream
                            if "trade" in stream:
                                yield StreamMessage(
                                    exchange=self.exchange_name,
                                    channel=stream,
                                    timestamp=payload.get("T"),
                                    data=payload,
                                )

                            # 2. Routing: Ticker Stream (for 24h Volume Cache)
                            if "ticker" in stream:
                                raw_symbol = payload.get("s")
                                if raw_symbol:
                                    canonical_symbol = self._symbol_map.get(raw_symbol, raw_symbol)
                                    await self.market_data_repo.cache_ticker(canonical_symbol, payload)

                    except (orjson.JSONDecodeError, KeyError, TypeError):
                        log.warning("Failed to decode or parse Binance message.")

        except websockets.exceptions.InvalidStatus as e:
            if e.response.status_code == 404:
                log.critical(f"[{self.market_def.market_id}_{self.shard_num_for_log}] 404 REJECTION. One or more symbols in this shard are invalid. ")
            raise e
        except Exception as e:
            log.error(f"[{self.market_def.market_id}] Connection Error: {e}")
            raise e
        finally:
            self._ws = None
            log.warning(f"[{self.market_def.market_id}] WebSocket connection closed.")

    async def _process_message_batch(self):
        """Inner loop to consume from the generator and write to Redis."""
        try:
            async for message in self.connect():
                await self.market_data_repo.add_messages_to_stream(self.stream_name, [message])
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception(f"[{self.market_def.market_id}] Unhandled error in message batch processor.")

    async def process_messages(self):
        """
        The main supervisor loop that manages dynamic subscriptions and the connection lifecycle.
        """
        self._is_running.set()
        reconnect_attempts = 0
        subscription_task = asyncio.create_task(self._maintain_subscriptions())

        while self._is_running.is_set():
            try:
                await self._reconnect_event.wait()
                self._reconnect_event.clear()

                batch_task = asyncio.create_task(self._process_message_batch())
                await batch_task

                reconnect_attempts = 0
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception(f"[{self.market_def.market_id}] Supervisor error.")

            if self._is_running.is_set():
                reconnect_attempts += 1
                delay = min(2**reconnect_attempts, 60)
                log.info(f"[{self.market_def.market_id}] Reconnecting in {delay}s...")
                await asyncio.sleep(delay)
                self._reconnect_event.set()

        subscription_task.cancel()
        log.info(f"[{self.market_def.market_id}] Supervisor loop has shut down.")

    async def close(self):
        log.warning(f"[{self.market_def.market_id}] Closing client...")
        self._is_running.clear()
        self._reconnect_event.set()
        if self._ws:
            await self._ws.close()
