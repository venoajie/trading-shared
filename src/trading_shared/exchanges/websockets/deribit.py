# src/trading_shared/exchanges/websockets/deribit.py

# --- Built Ins ---
import asyncio
import time
from collections.abc import AsyncGenerator

# --- Installed ---
import orjson
import websockets
from loguru import logger as log

from ...config.models import ExchangeSettings

# --- Local Application Imports ---
from ...core.models import MarketDefinition, StreamMessage
from ...repositories.instrument_repository import InstrumentRepository
from ...repositories.market_data_repository import MarketDataRepository
from ...repositories.system_state_repository import SystemStateRepository
from .base import AbstractWsClient


class DeribitWsClient(AbstractWsClient):
    """
    A dual-purpose, self-managing WebSocket client for Deribit.
    Updated with sequential Authentication -> Subscription logic.
    """

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

        # Fixed IDs for reliable state tracking
        self.AUTH_ID = 9929
        self.SUB_ID = 1001

        if self.subscription_scope == "private" and (not settings.client_id or not settings.client_secret):
            raise ValueError("Deribit private scope requires client_id and client_secret.")

    async def _send_rpc_payload(self, method: str, params: dict, req_id: int):
        """Internal helper to send a raw RPC message with a specific ID."""
        if not self._ws:
            return
        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        await self._ws.send(orjson.dumps(msg))

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """
        Manages the connection lifecycle with strict sequential logic:
        Connect -> Auth -> Wait -> Subscribe -> Stream.
        """
        try:
            async with websockets.connect(self.ws_connection_url, ping_interval=30) as ws:
                self._ws = ws
                log.success(f"[{self.exchange_name}][{self.subscription_scope}] WebSocket connection established.")

                # --- PHASE 1: AUTHENTICATION ---
                if self.subscription_scope == "private":
                    log.info(f"[{self.exchange_name}] Attempting Authentication...")
                    auth_params = {
                        "grant_type": "client_credentials",
                        "client_id": self.settings.client_id,
                        "client_secret": self.settings.client_secret.get_secret_value(),
                    }
                    await self._send_rpc_payload("public/auth", auth_params, self.AUTH_ID)
                else:
                    # If public, skip straight to subscription logic (not implemented for this fix)
                    pass

                # --- PHASE 2: EVENT LOOP ---
                is_authenticated = False
                is_subscribed = False

                async for message in ws:
                    try:
                        data = orjson.loads(message)

                        # 1. Handle Errors
                        if "error" in data:
                            err = data["error"]
                            log.error(f"[{self.exchange_name}] RPC ERROR (ID: {data.get('id')}): {err.get('message')} ({err.get('code')})")
                            # If Auth failed, we can't proceed.
                            if data.get("id") == self.AUTH_ID:
                                log.critical("Authentication failed. Closing connection.")
                                return

                        # 2. Handle RPC Results (Auth / Sub Confirmations)
                        elif "result" in data:
                            req_id = data.get("id")
                            
                            if req_id == self.AUTH_ID:
                                log.success(f"[{self.exchange_name}] Authentication SUCCESS.")
                                is_authenticated = True
                                
                                # Immediately Subscribe after Auth success
                                channels = ["user.changes.any.any.raw"]
                                log.info(f"[{self.exchange_name}] Subscribing to: {channels}")
                                await self._send_rpc_payload("private/subscribe", {"channels": channels}, self.SUB_ID)

                            elif req_id == self.SUB_ID:
                                log.success(f"[{self.exchange_name}] Subscription CONFIRMED: {data['result']}")
                                is_subscribed = True

                        # 3. Handle Subscription Data (The Payload)
                        elif data.get("method") == "subscription":
                            params = data.get("params", {})
                            channel = params.get("channel")
                            payload = params.get("data")
                            
                            if channel and payload:
                                # log.debug(f"[{self.exchange_name}] Event on {channel}")
                                yield StreamMessage(
                                    exchange=self.exchange_name,
                                    channel=channel,
                                    timestamp=int(time.time() * 1000),
                                    data=data, # Send full envelope
                                )

                        # 4. Handle Heartbeats
                        elif data.get("method") == "heartbeat":
                             if data.get("params", {}).get("type") == "test_request":
                                await self._send_rpc_payload("public/test", {}, 0)

                    except Exception as e:
                        log.error(f"[{self.exchange_name}] Parsing error: {e}")

        finally:
            self._ws = None
            log.warning(f"[{self.exchange_name}][{self.subscription_scope}] Connection closed.")
            
    async def _process_message_batch(self):
        """Inner loop to consume messages and write them to the Redis stream."""
        try:
            async for message in self.connect():
                await self.market_data_repo.add_messages_to_stream(self.stream_name, [message])
        except asyncio.CancelledError:
            pass  # Normal shutdown

    async def process_messages(self):
        """The main supervisor loop that manages the connection lifecycle."""
        self._is_running.set()
        reconnect_attempts = 0
        subscription_task = None

        if self.subscription_scope == "public":
            subscription_task = asyncio.create_task(self._maintain_subscriptions())
        else:
            self._reconnect_event.set()

        while self._is_running.is_set():
            try:
                await self._reconnect_event.wait()
                self._reconnect_event.clear()

                batch_task = asyncio.create_task(self._process_message_batch())
                await batch_task  # Awaits until the connection is lost.

                reconnect_attempts = 0
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception(f"[{self.exchange_name}] Supervisor error.")

            if self._is_running.is_set():
                reconnect_attempts += 1
                delay = min(2**reconnect_attempts, 60)
                log.info(f"[{self.exchange_name}] Reconnecting in {delay}s...")
                await asyncio.sleep(delay)
                self._reconnect_event.set()

        if subscription_task:
            subscription_task.cancel()
        log.info(f"[{self.exchange_name}][{self.subscription_scope}] Supervisor loop has shut down.")

    async def _get_channels_from_universe(self, universe: list[dict[str, any]]) -> set[str]:
        # Required implementation for abstract base class, but unused in private mode
        return set()
    
    async def close(self):
        """Initiates a graceful shutdown."""
        log.warning(f"[{self.exchange_name}][{self.subscription_scope}] Closing client...")
        self._is_running.clear()
        self._reconnect_event.set()
        if self._ws:
            await self._ws.close()
