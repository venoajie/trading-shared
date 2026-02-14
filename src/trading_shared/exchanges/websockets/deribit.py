
# src/trading_shared/exchanges/websockets/deribit.py

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any

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
        
        # RPC Tracking: Maps ID -> asyncio.Future
        self._rpc_tracker: dict[int, asyncio.Future] = {}

        if self.subscription_scope == "private" and (not settings.client_id or not settings.client_secret):
            raise ValueError("Deribit private scope requires client_id and client_secret.")

    async def _send_rpc(self, method: str, params: dict) -> Any:
        """
        Sends JSON-RPC and WAITS for the response.
        Enforces Text Frames (UTF-8) to avoid 'bad_request' errors.
        """
        if not self._ws:
            raise ConnectionError(f"[{self.exchange_name}] Cannot send RPC: No active connection.")

        rpc_id = int(time.time() * 1000000) # Microsecond precision for unique IDs
        msg = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": method,
            "params": params,
        }

        # Create a future to wait for the response
        future = asyncio.get_running_loop().create_future()
        self._rpc_tracker[rpc_id] = future

        try:
            # CRITICAL FIX: Convert bytes to string to ensure Text Frame
            payload = orjson.dumps(msg).decode("utf-8")
            
            safe_params = {k: ("***" if "secret" in k.lower() else v) for k, v in params.items()}
            log.info(f"[{self.exchange_name}] >>> RPC REQ | ID: {rpc_id} | Method: {method} | Params: {safe_params}")
            
            await self._ws.send(payload)
            
            # Wait for response with timeout
            return await asyncio.wait_for(future, timeout=10.0)
        except asyncio.TimeoutError:
            log.error(f"[{self.exchange_name}] RPC TIMEOUT | ID: {rpc_id} | Method: {method}")
            raise
        finally:
            self._rpc_tracker.pop(rpc_id, None)

    async def _handle_subscriptions(self):
        """Sequential Auth -> Subscribe flow with strict response checking."""
        try:
            if self.subscription_scope == "private":
                log.info(f"[{self.exchange_name}] Initiating Authentication...")
                auth_params = {
                    "grant_type": "client_credentials",
                    "client_id": self.settings.client_id,
                    "client_secret": self.settings.client_secret.get_secret_value(),
                }
                
                auth_result = await self._send_rpc("public/auth", auth_params)
                log.success(f"[{self.exchange_name}] Authentication Successful. Session expires in: {auth_result.get('expires_in')}s")

                # Only proceed to subscribe if auth succeeded
                channels = ["user.changes.any.any.raw"]
                log.info(f"[{self.exchange_name}] Subscribing to Private Channels: {channels}")
                sub_result = await self._send_rpc("private/subscribe", {"channels": channels})
                log.success(f"[{self.exchange_name}] Subscription Confirmed: {sub_result}")

            elif self.subscription_scope == "public" and self._active_channels:
                await self._send_rpc("public/subscribe", {"channels": list(self._active_channels)})

        except Exception as e:
            log.error(f"[{self.exchange_name}] Setup Failed: {e}")
            # Close connection to trigger supervisor reconnect
            if self._ws:
                await self._ws.close()

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """Managed connection yielding validated private events."""
        log.info(f"[{self.exchange_name}] Connecting to {self.ws_connection_url}...")
        
        try:
            async with websockets.connect(self.ws_connection_url, ping_interval=30) as ws:
                self._ws = ws
                log.success(f"[{self.exchange_name}] Connection Established.")
                
                # Setup Auth/Subs
                await self._handle_subscriptions()

                async for raw_message in ws:
                    try:
                        data = orjson.loads(raw_message)

                        # Check if this is a response to a tracked RPC
                        resp_id = data.get("id")
                        if resp_id in self._rpc_tracker:
                            future = self._rpc_tracker[resp_id]
                            if "error" in data:
                                future.set_exception(RuntimeError(f"RPC Error: {data['error']}"))
                            else:
                                future.set_result(data.get("result"))
                            continue

                        # Process streaming notifications
                        params = data.get("params", {})
                        channel = params.get("channel")
                        payload = params.get("data")

                        if payload and channel:
                            # Private account events (Orders/Fills)
                            if self.subscription_scope == "private":
                                # Log private events for audit trail
                                log.info(f"[{self.exchange_name}] PRIVATE_EVENT | Channel: {channel}")
                                yield StreamMessage(
                                    exchange=self.exchange_name,
                                    channel=channel,
                                    timestamp=int(time.time() * 1000),
                                    data=payload,
                                )
                            
                            # Public trade events
                            elif "trades" in channel:
                                for trade in payload:
                                    yield StreamMessage(
                                        exchange=self.exchange_name,
                                        channel=channel,
                                        timestamp=trade.get("timestamp"),
                                        data=trade,
                                    )

                    except Exception as e:
                        if "heartbeat" not in str(raw_message):
                            log.error(f"[{self.exchange_name}] Message Error: {e}")

        finally:
            self._ws = None
            # Cancel any pending RPCs
            for future in self._rpc_tracker.values():
                if not future.done():
                    future.cancel()
            self._rpc_tracker.clear()

    async def _process_message_batch(self):
        async for message in self.connect():
            await self.market_data_repo.add_messages_to_stream(self.stream_name, [message])

    async def process_messages(self):
        self._is_running.set()
        
        if self.subscription_scope == "public":
            asyncio.create_task(self._maintain_subscriptions())
        else:
            self._reconnect_event.set()

        while self._is_running.is_set():
            try:
                await self._reconnect_event.wait()
                self._reconnect_event.clear()
                await self._process_message_batch()
            except Exception as e:
                log.exception(f"[{self.exchange_name}] Supervisor Loop Error: {e}")

            if self._is_running.is_set():
                await asyncio.sleep(5)
                self._reconnect_event.set()

    async def _get_channels_from_universe(self, universe: list[dict]) -> set[str]:
        # Required implementation for abstract base
        return set()

    async def close(self):
        self._is_running.clear()
        self._reconnect_event.set()
        if self._ws:
            await self._ws.close()