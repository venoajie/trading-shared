
# src/trading_shared/exchanges/websockets/deribit.py

import asyncio
import json  # <-- MODIFIED: Import the standard json library
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
    """
    A robust, dual-purpose WebSocket client for Deribit, designed for high-availability
    and clear separation of public/private scopes. It features a request/response
    tracking system for all critical RPC calls to ensure operational correctness.
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
        self._rpc_tracker: dict[int, asyncio.Future] = {}

        if self.subscription_scope == "private" and (not settings.client_id or not settings.client_secret):
            raise ValueError("Deribit private scope requires client_id and client_secret.")

    async def _send_rpc(self, method: str, params: dict) -> Any:
        if not self._ws:
            raise ConnectionError(f"[{self.exchange_name}] Cannot send RPC: No active connection.")

        rpc_id = int(time.time() * 1_000_000)
        msg = {"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params}
        future = asyncio.get_running_loop().create_future()
        self._rpc_tracker[rpc_id] = future

        try:
            # --- CRITICAL FIX ---
            # Reverted to standard `json.dumps` for outgoing RPC calls.
            # The Deribit auth endpoint is strict and silently drops requests
            # formatted by `orjson`. This ensures maximum compatibility.
            payload_str = json.dumps(msg)

            safe_params = {k: ("***" if "secret" in k.lower() else v) for k, v in params.items()}
            log.debug(f"[{self.exchange_name}] >>> RPC SEND | ID: {rpc_id} | Method: {method} | Params: {safe_params}")
            await self._ws.send(payload_str)
            return await asyncio.wait_for(future, timeout=10.0)
        except asyncio.TimeoutError:
            log.error(f"[{self.exchange_name}] RPC TIMEOUT | ID: {rpc_id} | Method: {method}")
            raise
        finally:
            self._rpc_tracker.pop(rpc_id, None)

    async def _handle_subscriptions(self):
        try:
            if self.subscription_scope == "private":
                log.info(f"[{self.exchange_name}] Initiating authentication...")
                auth_params = {
                    "grant_type": "client_credentials",
                    "client_id": self.settings.client_id,
                    "client_secret": self.settings.client_secret.get_secret_value(),
                }
                auth_result = await self._send_rpc("public/auth", auth_params)
                log.success(f"[{self.exchange_name}] Authentication successful. Access token expires in {auth_result.get('expires_in')}s.")

                private_channels = ["user.changes.any.any.raw"]
                log.info(f"[{self.exchange_name}] Subscribing to private channel: {private_channels[0]}")
                sub_result = await self._send_rpc("private/subscribe", {"channels": private_channels})
                log.success(f"[{self.exchange_name}] Subscription to private channel confirmed: {sub_result}")

            elif self.subscription_scope == "public" and self._active_channels:
                log.info(f"[{self.exchange_name}] Subscribing to {len(self._active_channels)} public channels.")
                await self._send_rpc("public/subscribe", {"channels": list(self._active_channels)})
                log.success(f"[{self.exchange_name}] Public channel subscription sent.")
        except Exception as e:
            log.error(f"[{self.exchange_name}] Connection setup failed: {e}", exc_info=True)
            if self._ws:
                await self._ws.close()

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        log.info(f"[{self.exchange_name}] Attempting to connect to {self.ws_connection_url}...")
        try:
            async with websockets.connect(self.ws_connection_url, ping_interval=30) as ws:
                self._ws = ws
                log.success(f"[{self.exchange_name}][{self.subscription_scope}] WebSocket connection established.")
                await self._handle_subscriptions()
                async for raw_message in ws:
                    try:
                        # Keep using high-performance orjson for parsing incoming messages
                        data = orjson.loads(raw_message)

                        if (resp_id := data.get("id")) in self._rpc_tracker:
                            future = self._rpc_tracker[resp_id]
                            if "error" in data:
                                log.warning(f"[{self.exchange_name}] <<< RPC ERROR | ID: {resp_id} | Error: {data['error']}")
                                future.set_exception(RuntimeError(f"RPC Error: {data['error']}"))
                            else:
                                result = data.get("result")
                                log.debug(f"[{self.exchange_name}] <<< RPC RECV | ID: {resp_id} | Result: {result}")
                                future.set_result(result)
                            continue

                        if params := data.get("params", {}):
                            if (channel := params.get("channel")) and (payload := params.get("data")):
                                if self.subscription_scope == "private":
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
                    except (orjson.JSONDecodeError, KeyError, TypeError) as e:
                        if "heartbeat" not in str(raw_message):
                            log.warning(f"[{self.exchange_name}] Error processing message: {e} | Raw: {str(raw_message)[:150]}")
        finally:
            self._ws = None
            log.warning(f"[{self.exchange_name}][{self.subscription_scope}] WebSocket connection closed.")
            for future in self._rpc_tracker.values():
                if not future.done():
                    future.cancel()
            self._rpc_tracker.clear()

    async def _process_message_batch(self):
        try:
            async for message in self.connect():
                await self.market_data_repo.add_messages_to_stream(self.stream_name, [message])
        except asyncio.CancelledError:
            pass
        except websockets.exceptions.ConnectionClosedError as e:
            log.warning(f"[{self.exchange_name}] Connection closed unexpectedly: {e.code} {e.reason}")
        except Exception:
            log.exception(f"[{self.exchange_name}] Unexpected error in message batch processor.")

    async def process_messages(self):
        self._is_running.set()
        reconnect_attempts = 0
        if self.subscription_scope == "public":
            subscription_task = asyncio.create_task(self._maintain_subscriptions())
        else:
            self._reconnect_event.set()

        while self._is_running.is_set():
            try:
                await self._reconnect_event.wait()
                self._reconnect_event.clear()
                await self._process_message_batch()
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

        if 'subscription_task' in locals() and not subscription_task.done():
            subscription_task.cancel()
        log.info(f"[{self.exchange_name}][{self.subscription_scope}] Supervisor loop has shut down.")

    async def _get_channels_from_universe(self, universe: list[str]) -> set[str]:
        return set()

    async def close(self):
        log.warning(f"[{self.exchange_name}][{self.subscription_scope}] Closing client...")
        self._is_running.clear()
        self._reconnect_event.set()
        if self._ws:
            await self._ws.close()