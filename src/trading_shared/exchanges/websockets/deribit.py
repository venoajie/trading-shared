
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
    """A dual-purpose WebSocket client with maximum debug transparency."""

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

    async def _send_rpc(self, method: str, params: dict):
        """Sends JSON-RPC and logs the raw output."""
        if not self._ws:
            log.error(f"[{self.exchange_name}] RPC FAILED: No WebSocket connection for method '{method}'")
            return
        
        rpc_id = int(time.time() * 1000)
        msg = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": method,
            "params": params,
        }
        
        # Security: Mask sensitive credentials in logs
        safe_params = {k: ("***" if "secret" in k.lower() else v) for k, v in params.items()}
        raw_payload = orjson.dumps(msg)
        
        log.info(f"[{self.exchange_name}] >>> RPC SEND | ID: {rpc_id} | Method: {method} | Params: {safe_params}")
        await self._ws.send(raw_payload)

    async def _handle_subscriptions(self):
        """Executes Auth and Subscription with verbose state logging."""
        if self.subscription_scope == "private":
            log.info(f"[{self.exchange_name}] Step 1: Authenticating client '{self.settings.client_id}'")
            auth_params = {
                "grant_type": "client_credentials",
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret.get_secret_value(),
            }
            await self._send_rpc("public/auth", auth_params)
            
            # We wait briefly for auth to process before subscribing
            await asyncio.sleep(0.5) 
            
            log.info(f"[{self.exchange_name}] Step 2: Subscribing to private account stream.")
            await self._send_subscribe(["user.changes.any.any.raw"])

        elif self.subscription_scope == "public" and self._active_channels:
            log.info(f"[{self.exchange_name}] Subscribing to {len(self._active_channels)} public channels.")
            await self._send_subscribe(list(self._active_channels))

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """The core ingestion loop with full packet inspection."""
        log.info(f"[{self.exchange_name}] Attempting connection to: {self.ws_connection_url}")
        
        try:
            async with websockets.connect(self.ws_connection_url, ping_interval=30) as ws:
                self._ws = ws
                log.success(f"[{self.exchange_name}] TCP/TLS Connection Established.")
                
                await self._handle_subscriptions()

                async for raw_message in ws:
                    # LOG EVERY PACKET
                    log.debug(f"[{self.exchange_name}] <<< RAW RECV: {raw_message}")
                    
                    try:
                        data = orjson.loads(raw_message)

                        # Handle Heartbeats (Silent)
                        if "method" in data and data["method"] == "heartbeat":
                            log.trace(f"[{self.exchange_name}] Heartbeat received.")
                            continue

                        # Handle RPC Responses (Auth/Sub results)
                        if "result" in data:
                            log.success(f"[{self.exchange_name}] RPC OK | ID: {data.get('id')} | Result: {data.get('result')}")
                            continue
                        
                        if "error" in data:
                            log.error(f"[{self.exchange_name}] RPC ERROR | ID: {data.get('id')} | Details: {data.get('error')}")
                            continue

                        # Extract Notification Data
                        params = data.get("params", {})
                        channel = params.get("channel")
                        payload = params.get("data")

                        if payload and channel:
                            log.info(f"[{self.exchange_name}] Data Event on '{channel}'")
                            
                            if self.subscription_scope == "private":
                                # Detailed payload logging for private events to see Order/Trade details
                                log.info(f"[{self.exchange_name}] PRIVATE_PAYLOAD: {payload}")
                                
                                yield StreamMessage(
                                    exchange=self.exchange_name,
                                    channel=channel,
                                    timestamp=int(time.time() * 1000),
                                    data=payload,
                                )
                            
                            elif "trades" in channel:
                                for trade in payload:
                                    yield StreamMessage(
                                        exchange=self.exchange_name,
                                        channel=channel,
                                        timestamp=trade.get("timestamp"),
                                        data=trade,
                                    )

                            elif "ticker" in channel:
                                symbol = payload.get("instrument_name")
                                if symbol:
                                    await self.market_data_repo.cache_ticker(self.exchange_name, symbol, payload)

                    except Exception as e:
                        log.error(f"[{self.exchange_name}] Failed to process packet: {e}")

        finally:
            self._ws = None
            log.warning(f"[{self.exchange_name}] WebSocket closed/dropped.")

    async def _send_subscribe(self, channels: list[str]):
        method = f"{self.subscription_scope}/subscribe"
        await self._send_rpc(method, {"channels": channels})

    async def _send_unsubscribe(self, channels: list[str]):
        method = f"{self.subscription_scope}/unsubscribe"
        await self._send_rpc(method, {"channels": channels})

    async def _process_message_batch(self):
        """Inner loop to pipe validated StreamMessages to Redis."""
        async for message in self.connect():
            # Final verification before Redis write
            log.debug(f"[{self.exchange_name}] Writing event to Redis stream: {self.stream_name}")
            await self.market_data_repo.add_messages_to_stream(self.stream_name, [message])

    async def process_messages(self):
        """Main supervisor loop managing reconnection."""
        self._is_running.set()
        reconnect_attempts = 0

        # Note: private receiver does not use dynamic universe subscriptions
        if self.subscription_scope == "public":
            asyncio.create_task(self._maintain_subscriptions())
        else:
            self._reconnect_event.set()

        while self._is_running.is_set():
            try:
                await self._reconnect_event.wait()
                self._reconnect_event.clear()

                log.info(f"[{self.exchange_name}] Starting Ingestion Task...")
                await self._process_message_batch()

                reconnect_attempts = 0
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.exception(f"[{self.exchange_name}] Supervisor Loop Exception: {e}")

            if self._is_running.is_set():
                reconnect_attempts += 1
                delay = min(2**reconnect_attempts, 60)
                log.info(f"[{self.exchange_name}] Reconnecting in {delay}s...")
                await asyncio.sleep(delay)
                self._reconnect_event.set()

    async def close(self):
        self._is_running.clear()
        self._reconnect_event.set()
        if self._ws:
            await self._ws.close()