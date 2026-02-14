# src/trading_shared/exchanges/websockets/deribit.py

import asyncio
import time
from collections.abc import AsyncGenerator

import orjson
import websockets
from loguru import logger as log

from ...config.models import ExchangeSettings
from ...core.models import MarketDefinition, StreamMessage
from ...repositories.instrument_repository import InstrumentRepository
from ...repositories.market_data_repository import MarketDataRepository
from ...repositories.system_state_repository import SystemStateRepository
from .base import AbstractWsClient

class DeribitWsClient(AbstractWsClient):
    """A dual-purpose, self-managing WebSocket client for Deribit."""

    def __init__(
        self,
        market_definition: MarketDefinition,
        market_data_repo: MarketDataRepository,
        instrument_repo: InstrumentRepository,
        settings: ExchangeSettings,
        subscription_scope: str = "public",
        system_state_repo: SystemStateRepository | None = None,
        universe_state_key: str | None = None,
    ):
        super().__init__(market_definition, market_data_repo, shard_id=0, total_shards=1)
        self.instrument_repo = instrument_repo
        self.settings = settings
        self.subscription_scope = subscription_scope.lower()
        self.system_state_repo = system_state_repo
        self.universe_state_key = universe_state_key
        self.ws_connection_url = self.market_def.ws_base_url
        self._ws: websockets.WebSocketClientProtocol | None = None

        if self.subscription_scope == "private" and (not settings.client_id or not settings.client_secret):
            raise ValueError("Deribit private scope requires client_id and client_secret.")

    async def _get_channels_from_universe(self, universe: list[dict[str, any]]) -> set[str]:
        """Maps universe symbols to channels (Used for public scope)."""
        my_targets = set()
        for asset_pair in universe:
            if asset_pair.get("exchange_spot") == self.exchange_name:
                if symbol := asset_pair.get("spot_symbol"):
                    my_targets.add(symbol)
            if asset_pair.get("exchange_perp") == self.exchange_name:
                if symbol := asset_pair.get("perp_symbol"):
                    my_targets.add(symbol)

        sharded_targets = {symbol for i, symbol in enumerate(sorted(my_targets)) if i % self.total_shards == self.shard_id}
        
        channels = set()
        for symbol in sharded_targets:
            s_lower = symbol.lower()
            channels.add(f"trades.{s_lower}.100ms")
            channels.add(f"ticker.{s_lower}.100ms")
        return channels

    async def _send_rpc(self, method: str, params: dict):
        """Safely sends a JSON-RPC formatted request with verbose logging."""
        if not self._ws:
            log.error(f"[{self.exchange_name}] Cannot send RPC '{method}': WebSocket not connected.")
            return
        try:
            rpc_id = int(time.time() * 1000)
            msg = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "method": method,
                "params": params,
            }
            # Mask secrets in logs
            log_params = {k: ("***" if "secret" in k.lower() else v) for k, v in params.items()}
            log.debug(f"[{self.exchange_name}] Sending RPC Request: ID={rpc_id}, Method={method}, Params={log_params}")
            
            await self._ws.send(orjson.dumps(msg))
        except websockets.exceptions.ConnectionClosed:
            log.warning(f"[{self.exchange_name}] Failed to send RPC: Connection closed.")

    async def _handle_subscriptions(self):
        """Authenticates (if private) and subscribes to channels."""
        if self.subscription_scope == "private":
            log.info(f"[{self.exchange_name}] Initiating private authentication...")
            auth_params = {
                "grant_type": "client_credentials",
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret.get_secret_value(),
            }
            await self._send_rpc("public/auth", auth_params)
            
            # Subscribing to consolidated private channel
            private_channels = ["user.changes.any.any.raw"]
            log.info(f"[{self.exchange_name}] Requesting private subscription: {private_channels}")
            await self._send_subscribe(private_channels)

        elif self.subscription_scope == "public" and self._active_channels:
            log.info(f"[{self.exchange_name}] Subscribing to {len(self._active_channels)} public channels.")
            await self._send_subscribe(list(self._active_channels))

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """Manages connection and yields validated messages with internal routing logic."""
        log.info(f"[{self.exchange_name}] Connecting to {self.ws_connection_url}...")
        try:
            async with websockets.connect(self.ws_connection_url, ping_interval=30) as ws:
                self._ws = ws
                log.success(f"[{self.exchange_name}][{self.subscription_scope}] WebSocket connection established.")
                
                await self._handle_subscriptions()

                async for message in ws:
                    try:
                        data = orjson.loads(message)
                        
                        # Handle RPC Heartbeats / Responses
                        if "result" in data:
                            log.debug(f"[{self.exchange_name}] RPC Response received: {data.get('id')}")
                            continue

                        # Extract notification data
                        params = data.get("params", {})
                        channel = params.get("channel")
                        payload = params.get("data")

                        if not (payload and channel):
                            if "heartbeat" not in str(message):
                                log.trace(f"[{self.exchange_name}] Non-data message: {message}")
                            continue

                        # --- ROUTING LOGIC ---
                        
                        # 1. Private Account Events (user.changes.*)
                        if self.subscription_scope == "private":
                            log.debug(f"[{self.exchange_name}] Private event received on channel: {channel}")
                            yield StreamMessage(
                                exchange=self.exchange_name,
                                channel=channel,
                                timestamp=int(time.time() * 1000),
                                data=payload,
                            )
                        
                        # 2. Public Trade Events
                        elif "trades" in channel:
                            for trade in payload:
                                yield StreamMessage(
                                    exchange=self.exchange_name,
                                    channel=channel,
                                    timestamp=trade.get("timestamp"),
                                    data=trade,
                                )

                        # 3. Public Ticker Updates (Direct Cache)
                        elif "ticker" in channel:
                            symbol = payload.get("instrument_name")
                            if symbol:
                                await self.market_data_repo.cache_ticker(self.exchange_name, symbol, payload)

                    except Exception as e:
                        log.error(f"[{self.exchange_name}] Message processing error: {e} | Raw: {message[:200]}")

        finally:
            self._ws = None
            log.warning(f"[{self.exchange_name}][{self.subscription_scope}] WebSocket connection closed.")

    async def _send_subscribe(self, channels: list[str]):
        method = f"{self.subscription_scope}/subscribe"
        await self._send_rpc(method, {"channels": channels})

    async def _send_unsubscribe(self, channels: list[str]):
        method = f"{self.subscription_scope}/unsubscribe"
        await self._send_rpc(method, {"channels": channels})

    async def _process_message_batch(self):
        """Consumes messages from connect() and writes to Redis stream."""
        async for message in self.connect():
            # Private events are high-value; we log the ingestion
            if self.subscription_scope == "private":
                log.info(f"[{self.exchange_name}] Ingesting private event to {self.stream_name}")
            
            await self.market_data_repo.add_messages_to_stream(
                self.stream_name, 
                [message],
                maxlen=5000 if self.subscription_scope == "private" else 10000
            )

    async def process_messages(self):
        """The main supervisor loop."""
        self._is_running.set()
        reconnect_attempts = 0
        subscription_task = None

        if self.subscription_scope == "public":
            subscription_task = asyncio.create_task(self._maintain_subscriptions())
        else:
            # For private receiver, we trigger the first connection immediately
            self._reconnect_event.set()

        while self._is_running.is_set():
            try:
                await self._reconnect_event.wait()
                self._reconnect_event.clear()

                log.info(f"[{self.exchange_name}] Starting message processor task...")
                await self._process_message_batch()

                reconnect_attempts = 0 # Reset on successful connection closure
            except asyncio.CancelledError:
                log.info(f"[{self.exchange_name}] Process messages task cancelled.")
                break
            except Exception as e:
                log.exception(f"[{self.exchange_name}] Critical Supervisor error: {e}")

            if self._is_running.is_set():
                reconnect_attempts += 1
                delay = min(2**reconnect_attempts, 60)
                log.info(f"[{self.exchange_name}] Reconnecting in {delay}s (Attempt {reconnect_attempts})...")
                await asyncio.sleep(delay)
                self._reconnect_event.set()

        if subscription_task:
            subscription_task.cancel()

    async def close(self):
        log.warning(f"[{self.exchange_name}][{self.subscription_scope}] Closing client...")
        self._is_running.clear()
        self._reconnect_event.set()
        if self._ws:
            await self._ws.close()