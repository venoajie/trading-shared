# src/trading_shared/exchanges/websockets/binance.py

# --- Built Ins ---
import asyncio
from collections.abc import AsyncGenerator

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
        self._symbol_map: dict[str, str] = {}

    async def _get_channels_from_universe(self, universe: list[dict[str, any]]) -> set[str]:
        """
        Parses the rich universe object to extract symbols for this client's specific shard.
        Populates self._symbol_map to ensure Ticker Cache uses Canonical names.
        """
        my_targets = set()
        temp_map = {}

        for asset_pair in universe:
            # Check both spot and perp exchanges to match this client's market definition
            if asset_pair.get("exchange_spot") == self.exchange_name:
                if symbol := asset_pair.get("spot_symbol"):
                    my_targets.add(symbol)
                    # Binance Raw often strips hyphens. We assume standard convention or lookup.
                    # Ideally, Janitor provides the 'raw_symbol' in the ledger.
                    # Assuming standard Binance format (remove '-') for now.
                    raw_symbol = symbol.replace("-", "").upper()
                    temp_map[raw_symbol] = symbol

            if asset_pair.get("exchange_perp") == self.exchange_name:
                if symbol := asset_pair.get("perp_symbol"):
                    my_targets.add(symbol)
                    raw_symbol = symbol.replace("-", "").upper()
                    temp_map[raw_symbol] = symbol

        # Update the instance map
        self._symbol_map.update(temp_map)

        sharded_targets = {symbol for i, symbol in enumerate(sorted(my_targets)) if i % self.total_shards == self.shard_id}

        # Convert canonical targets back to raw for channel subscription
        channels = set()
        for canonical in sharded_targets:
            # Reverse lookup or re-derive raw
            raw = canonical.replace("-", "").lower()
            channels.add(f"{raw}@trade")
            channels.add(f"{raw}@ticker")  # Ensure we subscribe to ticker if needed, or rely on trade stream data if it contains price

        # Optimization: If we only rely on @trade for trades, we still need @ticker for the 24h volume?
        # The prompt implies we need 24h volume. @trade does not provide 24h volume.
        # We MUST subscribe to @ticker or @miniTicker to populate the cache used by DataFacade.
        return channels

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """
        Manages a single, finite connection based on the current
        active channels. Exits upon disconnection and provides detailed 404 logging.
        """
        if not self._active_channels:
            log.warning(f"[{self.market_def.market_id}] No channels to connect to.")
            return

        sorted_channels = sorted(self._active_channels)
        url_path = "/stream?streams=" + "/".join(sorted_channels)
        full_url = self.ws_connection_url + url_path

        try:
            async with websockets.connect(full_url, ping_interval=180) as ws:
                self._ws = ws
                log.success(f"[{self.market_def.market_id}_{self.shard_num_for_log}] Shard Connected.")

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
                            # Binance payload 's' is the RAW symbol (e.g. BTCUSDT)
                            if "ticker" in stream:
                                raw_symbol = payload.get("s")
                                if raw_symbol:
                                    # Normalize to Canonical before Caching
                                    canonical_symbol = self._symbol_map.get(raw_symbol, raw_symbol)
                                    await self.market_data_repo.cache_ticker(canonical_symbol, payload)

                    except (orjson.JSONDecodeError, KeyError, TypeError):
                        log.warning("Failed to decode or parse Binance message.")

        except websockets.exceptions.InvalidStatus as e:
            if e.response.status_code == 404:
                log.critical(
                    f"[{self.market_def.market_id}_{self.shard_num_for_log}] 404 REJECTION. "
                    f"One or more symbols in this shard are invalid. "
                    f"Channels in this shard: {sorted_channels}"
                )
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
            pass  # Normal shutdown
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
                await batch_task  # Awaits until the connection is lost.

                reconnect_attempts = 0  # Reset attempts on clean disconnect
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception(f"[{self.market_def.market_id}] Supervisor error.")

            if self._is_running.is_set():
                reconnect_attempts += 1
                delay = min(2**reconnect_attempts, 60)
                log.info(f"[{self.market_def.market_id}] Reconnecting in {delay}s...")
                await asyncio.sleep(delay)
                self._reconnect_event.set()  # Trigger an immediate reconnect attempt

        subscription_task.cancel()
        log.info(f"[{self.market_def.market_id}] Supervisor loop has shut down.")

    async def close(self):
        log.warning(f"[{self.market_def.market_id}] Closing client...")
        self._is_running.clear()
        self._reconnect_event.set()  # Unblock the main loop so it can exit
        if self._ws:
            await self._ws.close()
