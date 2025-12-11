# src/trading_shared/exchanges/websockets/deribit.py

# --- Built Ins  ---
import asyncio
import json
import random
import time
from collections import deque
from typing import AsyncGenerator, List, Optional, Union

# --- Installed  ---
from loguru import logger as log
import orjson
import websockets
from pydantic import SecretStr

# --- Local Application Imports ---
from ...clients.postgres_client import PostgresClient
from ...clients.redis_client import CustomRedisClient
from ...config.models import ExchangeSettings
from ...repositories.market_data_repository import MarketDataRepository
from .base import AbstractWsClient

# --- Shared Library Imports  ---
from trading_engine_core.models import StreamMessage, MarketDefinition

EXCHANGE_EVENTS_STREAM = "stream:exchange_events:deribit"

class DeribitWsClient(AbstractWsClient):
    def __init__(
        self,
        market_definition: MarketDefinition,
        postgres_client: PostgresClient,
        market_data_repo: MarketDataRepository,
        settings: ExchangeSettings,
        subscription_scope: str = "public",
        redis_client: Optional[CustomRedisClient] = None,
    ):
        super().__init__(market_definition, market_data_repo, postgres_client, redis_client)
        self.settings = settings
        self.subscription_scope = subscription_scope.lower()

        if self.subscription_scope == "private" and not self.redis_client:
            raise ValueError("DeribitWsClient in 'private' scope requires a redis_client.")
        if not self.settings.client_id or not self.settings.client_secret:
            raise ValueError("Deribit client_id and client_secret must be configured.")

        if self.subscription_scope == "public":
            self.stream_name = f"stream:market_data:{self.exchange_name}"
        elif self.subscription_scope == "private":
            # Use the constant for internal consistency.
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
        self.instrument_names: List[str] = []

    def _get_secret_value(self, secret: Union[SecretStr, str]) -> str:
        """Safely gets the string value from a SecretStr or a plain str."""
        if isinstance(secret, SecretStr):
            return secret.get_secret_value()
        return secret

    async def _send_json(self, data: dict):
        if self.websocket_client:
            await self.websocket_client.send(json.dumps(data))

    async def _load_instruments(self) -> bool:
        # This is only required for public subscriptions
        if not self.instrument_names:
            try:
                records = await self.postgres_client.fetch_instruments_by_exchange(
                    self.exchange_name
                )
                self.instrument_names = [
                    r["instrument_name"]
                    for r in records
                    if r["market_type"] == self.market_def.market_type.value
                ]
                if not self.instrument_names:
                    log.warning(
                        f"[{self.exchange_name}] No instruments found in DB for market type '{self.market_def.market_type.value}'."
                    )
                    return False
                log.info(
                    f"[{self.exchange_name}] Loaded {len(self.instrument_names)} instruments for subscription."
                )
                return True
            except ConnectionError:
                log.error(
                    f"[{self.exchange_name}] Failed to load instruments due to database connection error."
                )
                return False
        return True

    async def _subscribe(self):
        """Subscribes to channels based on the client's scope."""
        channels = []
        method = "public/subscribe"  # Default for public scope

        if self.subscription_scope == "public":
            if not await self._load_instruments():
                log.error(
                    f"[{self.exchange_name}] Instrument loading failed. Cannot subscribe."
                )
                return
            for instrument in self.instrument_names:
                channels.append(f"incremental_ticker.{instrument}")
                channels.append(f"chart.trades.{instrument}.1")
        elif self.subscription_scope == "private":
            method = "private/subscribe"
            channels = ["user.orders.any.any.raw", "user.trades.any.any.raw"]

        if not channels:
            log.warning(
                f"[{self.exchange_name}] No channels to subscribe to for scope '{self.subscription_scope}'."
            )
            return

        # Chunking for large subscription lists (primarily for public scope)
        chunk_size = 100
        for i in range(0, len(channels), chunk_size):
            chunk = channels[i : i + chunk_size]
            msg = {
                "jsonrpc": "2.0",
                "id": int(time.time() * 1000) + i,
                "method": method,
                "params": {"channels": chunk},
            }
            log.info(
                f"[{self.exchange_name}][{self.subscription_scope}] Sending subscription request for {len(chunk)} channels."
            )
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
            log.info(
                f"[{self.exchange_name}][{self.subscription_scope}] WebSocket connection established."
            )

            # Authentication is only performed for private scope
            is_authenticated = self.subscription_scope != "private"

            if not is_authenticated:
                await self._send_json(auth_msg)

            async for message in ws:
                try:
                    data = orjson.loads(message)
                    if not isinstance(data, dict):
                        continue

                    if not is_authenticated:
                        if data.get("id") == AUTH_ID:
                            if "error" in data:
                                log.error(
                                    f"[{self.exchange_name}] Authentication failed: {data['error']}"
                                )
                                return  # Fatal error, stop the generator
                            log.success(
                                f"[{self.exchange_name}] Authentication successful."
                            )
                            is_authenticated = True
                            await self._subscribe()
                        continue

                    if self._handle_control_message(data):
                        continue

                    # On the first non-control message after connecting, subscribe.
                    if is_authenticated and self.subscription_scope == "public":
                        await self._subscribe()
                        is_authenticated = False  # Prevent re-subscribing

                    params = data.get("params")
                    if (
                        isinstance(params, dict)
                        and "channel" in params
                        and "data" in params
                    ):
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
        log.info(
            f"[{self.exchange_name}][{self.subscription_scope}] Starting message processor."
        )

        while self._is_running.is_set():
            try:
                batch = deque()
                async for message in self.connect():
                    if not self._is_running.is_set():
                        break

                    reconnect_attempts = 0
                    batch.append(message)

                    # Flush logic now uses the correct repository based on scope
                    # and is resilient to Redis connection errors.
                    if len(batch) >= 100:
                        is_flushed = False
                        while not is_flushed and self._is_running.is_set():
                            try:
                                # The base class now holds the correct repository instance
                                await self.market_data_repo.add_messages_to_stream(
                                    self.stream_name, list(batch)
                                )
                                is_flushed = True
                                batch.clear()
                            except ConnectionError:
                                log.error(
                                    f"[{self.exchange_name}] Failed to flush batch to Redis. Retrying in 5s..."
                                )
                                await asyncio.sleep(5)

            except asyncio.CancelledError:
                break
            except (
                websockets.exceptions.ConnectionClosed,
                ConnectionRefusedError,
                asyncio.TimeoutError,
            ) as e:
                log.warning(
                    f"[{self.exchange_name}] WebSocket connection error: {type(e).__name__}. Will reconnect."
                )
            except Exception:
                log.exception(
                    f"[{self.exchange_name}] Unhandled error in processor for scope '{self.subscription_scope}'"
                )
            finally:
                if self.websocket_client:
                    await self.websocket_client.close()
                    self.websocket_client = None

                if self._is_running.is_set():
                    reconnect_attempts += 1
                    delay = min(2**reconnect_attempts, 60) + random.random()
                    log.info(f"[{self.exchange_name}] Reconnecting in {delay:.1f}s...")
                    await asyncio.sleep(delay)

        log.info(
            f"[{self.exchange_name}][{self.subscription_scope}] Message processor shut down."
        )

    async def close(self):
        log.info(f"[{self.exchange_name}][{self.subscription_scope}] Closing client...")
        self._is_running.clear()
        if self.websocket_client:
            try:
                await self.websocket_client.close()
            except websockets.exceptions.ConnectionClosed:
                pass
        log.info(f"[{self.exchange_name}][{self.subscription_scope}] Client closed.")
