# --- Built Ins  ---
import asyncio
import json
import random
import time
from collections import deque
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

# --- Installed  ---
from loguru import logger as log
import orjson
import websockets
from pydantic import SecretStr

# --- Local Application Imports ---
from ...clients.redis_client import CustomRedisClient
from ...config.models import ExchangeSettings
from ...repositories.instrument_repository import InstrumentRepository
from ...repositories.market_data_repository import MarketDataRepository
from .base import AbstractWsClient

# --- Shared Library Imports  ---
from trading_engine_core.models import StreamMessage, MarketDefinition

EXCHANGE_EVENTS_STREAM = "stream:exchange_events:deribit"


class DeribitWsClient(AbstractWsClient):
    def __init__(
        self,
        market_definition: MarketDefinition,
        instrument_repo: InstrumentRepository,
        market_data_repo: MarketDataRepository,
        settings: ExchangeSettings,
        subscription_scope: str = "public",
        redis_client: Optional[CustomRedisClient] = None,
        instruments_to_subscribe: List[Dict[str, Any]] | None = None,
        **kwargs,
    ):
        super().__init__(
            market_definition, market_data_repo, instrument_repo, redis_client
        )
        self.settings = settings
        self.subscription_scope = subscription_scope.lower()
        self.instruments_to_subscribe = instruments_to_subscribe or []

        if self.subscription_scope == "private" and not self.redis_client:
            raise ValueError(
                "DeribitWsClient in 'private' scope requires a redis_client."
            )
        if not self.settings.client_id or not self.settings.client_secret:
            raise ValueError("Deribit client_id and client_secret must be configured.")

        if self.subscription_scope == "public":
            self.stream_name = f"stream:market_data:{self.exchange_name}"
        elif self.subscription_scope == "private":
            self.stream_name = EXCHANGE_EVENTS_STREAM
        else:
            raise ValueError(f"Invalid subscription_scope: '{self.subscription_scope}'")

        self._is_running = asyncio.Event()
        self.ws_connection_url = self.market_def.ws_base_url
        if not self.ws_connection_url:
            raise ValueError("Deribit ws_base_url not configured in MarketDefinition.")

        self._client_id: Union[SecretStr, str] = self.settings.client_id
        self._client_secret: Union[SecretStr, str] = self.settings.client_secret
        self.websocket_client: Optional[websockets.WebSocketClientProtocol] = None

    def _get_secret_value(self, secret: Union[SecretStr, str]) -> str:
        """Safely gets the string value from a SecretStr or a plain str."""
        if isinstance(secret, SecretStr):
            return secret.get_secret_value()
        return secret

    async def _send_json(self, data: dict):
        if self.websocket_client:
            await self.websocket_client.send(json.dumps(data))

    async def _subscribe(self):
        """Subscribes to channels based on the client's scope."""
        channels = []
        method = "public/subscribe"

        if self.subscription_scope == "public":
            if not self.instruments_to_subscribe:
                log.warning(f"[{self.exchange_name}] No instruments provided for public subscription.")
                return
            log.info(f"[{self.exchange_name}] Building public subscriptions for {len(self.instruments_to_subscribe)} instruments.")
            for instrument in self.instruments_to_subscribe:
                # Assuming 'instrument_name' is the key from the database record
                channels.append(f"trades.{instrument['instrument_name']}.raw")

        elif self.subscription_scope == "private":
            method = "private/subscribe"
            channels = ["user.orders.any.any.raw", "user.trades.any.any.raw"]

        if not channels:
            log.warning(f"[{self.exchange_name}] No channels to subscribe to for scope '{self.subscription_scope}'.")
            return

        chunk_size = 100
        for i in range(0, len(channels), chunk_size):
            chunk = channels[i : i + chunk_size]
            msg = {
                "jsonrpc": "2.0",
                "id": int(time.time() * 1000) + i,
                "method": method,
                "params": {"channels": chunk},
            }
            log.info(f"[{self.exchange_name}][{self.subscription_scope}] Sending subscription request for {len(chunk)} channels.")
            await self._send_json(msg)

    def _handle_control_message(self, data: dict) -> bool:
        method = data.get("method")
        if method == "heartbeat":
            params = data.get("params")
            if isinstance(params, dict) and params.get("type") == "test_request":
                asyncio.create_task(
                    self._send_json(
                        {"jsonrpc": "2.0", "id": 0, "method": "public/test"}
                    )
                )
            return True
        if "id" in data and "result" in data:
            log.debug(f"Received RPC confirmation for request ID {data.get('id')}")
            return True
        return False

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        AUTH_ID = 9929

        auth_msg = {
            "jsonrpc": "2.0",
            "id": AUTH_ID,
            "method": "public/auth",
            "params": {
                "grant_type": "client_credentials",
                "client_id": self._get_secret_value(self._client_id),
                "client_secret": self._get_secret_value(self._client_secret),
            },
        }

        async with websockets.connect(self.ws_connection_url, ping_interval=30) as ws:
            self.websocket_client = ws
            log.info(f"[{self.exchange_name}][{self.subscription_scope}] WebSocket connection established.")
            
            is_authenticated = self.subscription_scope != "private"
            has_subscribed = False

            if not is_authenticated:
                await self._send_json(auth_msg)
            
            # For public scope, subscribe immediately after connecting
            if self.subscription_scope == 'public':
                await self._subscribe()
                has_subscribed = True

            async for message in ws:
                try:
                    data = orjson.loads(message)
                    if not isinstance(data, dict):
                        continue

                    if not is_authenticated:
                        if data.get("id") == AUTH_ID:
                            if "error" in data:
                                log.error(f"[{self.exchange_name}] Authentication failed: {data['error']}")
                                return
                            log.success(f"[{self.exchange_name}] Authentication successful.")
                            is_authenticated = True
                            await self._subscribe()
                            has_subscribed = True
                        continue

                    if self._handle_control_message(data):
                        continue

                    params = data.get("params")
                    if isinstance(params, dict) and "channel" in params and "data" in params:
                        yield StreamMessage(
                            exchange=self.exchange_name,
                            channel=params["channel"],
                            timestamp=int(time.time() * 1000),
                            data=params["data"],
                        )
                except orjson.JSONDecodeError:
                    log.warning(f"Invalid JSON received: {message[:100]}...")
                except Exception:
                    log.exception("Error processing message")

    async def process_messages(self):
        self._is_running.set()
        reconnect_attempts = 0
        log.info(f"[{self.exchange_name}][{self.subscription_scope}] Starting message processor.")

        while self._is_running.is_set():
            try:
                batch = deque()
                async for message in self.connect():
                    if not self._is_running.is_set():
                        break

                    reconnect_attempts = 0
                    batch.append(message)

                    if len(batch) >= 100:
                        is_flushed = False
                        while not is_flushed and self._is_running.is_set():
                            try:
                                await self.market_data_repo.add_messages_to_stream(
                                    self.stream_name, list(batch)
                                )
                                is_flushed = True
                                batch.clear()
                            except ConnectionError:
                                log.error(f"[{self.exchange_name}] Failed to flush batch to Redis. Retrying in 5s...")
                                await asyncio.sleep(5)

            except asyncio.CancelledError:
                break
            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, asyncio.TimeoutError) as e:
                log.warning(f"[{self.exchange_name}] WebSocket connection error: {type(e).__name__}. Will reconnect.")
            except Exception:
                log.exception(f"[{self.exchange_name}] Unhandled error in processor for scope '{self.subscription_scope}'")
            finally:
                if self.websocket_client:
                    await self.websocket_client.close()
                    self.websocket_client = None

                if self._is_running.is_set():
                    reconnect_attempts += 1
                    delay = min(2**reconnect_attempts, 60) + random.random()
                    log.info(f"[{self.exchange_name}] Reconnecting in {delay:.1f}s...")
                    await asyncio.sleep(delay)

        log.info(f"[{self.exchange_name}][{self.subscription_scope}] Message processor shut down.")

    async def close(self):
        log.info(f"[{self.exchange_name}][{self.subscription_scope}] Closing client...")
        self._is_running.clear()
        if self.websocket_client:
            try:
                await self.websocket_client.close()
            except websockets.exceptions.ConnectionClosed:
                pass
        log.info(f"[{self.exchange_name}][{self.subscription_scope}] Client closed.")