# src/trading_shared/exchanges/websockets/deribit.py

# --- Built Ins  ---
import asyncio
import json
import random
import time
from typing import AsyncGenerator, List, Optional

# --- Installed  ---
from loguru import logger as log
import orjson
import websockets
from pydantic import SecretStr # Import SecretStr for type hinting

# --- Local Application Imports ---
from ...clients.redis_client import CustomRedisClient
from ...clients.postgres_client import PostgresClient
from ...config.models import ExchangeSettings
from ...exchanges.trading.deribit_constants import WebsocketParameters
from .base import AbstractWsClient

# --- Shared Library Imports  ---
from trading_engine_core.models import StreamMessage, MarketDefinition


class DeribitWsClient(AbstractWsClient):
    def __init__(
        self,
        market_definition: MarketDefinition,
        postgres_client: PostgresClient,
        redis_client: CustomRedisClient,
        settings: ExchangeSettings,
    ):
        super().__init__(market_definition, redis_client, postgres_client)
        self.settings = settings
        self._is_running = asyncio.Event()
        self.ws_connection_url = self.market_def.ws_base_url
        if not self.ws_connection_url:
            raise ValueError("Deribit ws_base_url not configured in MarketDefinition.")
        if not self.settings.client_id or not self.settings.client_secret:
            raise ValueError("Deribit client_id and client_secret must be configured.")
            
        # These will hold the SecretStr objects
        self._client_id: SecretStr = self.settings.client_id
        self._client_secret: SecretStr = self.settings.client_secret
        
        self.websocket_client: Optional[websockets.WebSocketClientProtocol] = None
        self.instrument_names: List[str] = []

    async def _send_json(self, data: dict):
        if self.websocket_client:
            await self.websocket_client.send(json.dumps(data))

    async def _load_instruments(self) -> bool:
        """Loads instruments from DB. Returns True on success, False on failure."""
        if not self.instrument_names:
            try:
                records = await self.postgres_client.fetch_instruments_by_exchange(self.exchange_name)
                self.instrument_names = [
                    r["instrument_name"]
                    for r in records
                    if r["market_type"] == self.market_def.market_type.value
                ]
                if not self.instrument_names:
                    log.warning(f"[{self.exchange_name}] No instruments found in DB for market type '{self.market_def.market_type.value}'.")
                    return False
                log.info(f"[{self.exchange_name}] Loaded {len(self.instrument_names)} instruments for subscription.")
                return True
            except ConnectionError:
                log.error(f"[{self.exchange_name}] Failed to load instruments due to database connection error.")
                return False
        return True

    async def _subscribe(self):
        channels = ["user.orders.any.any.raw", "user.trades.any.any.raw"]
        for instrument in self.instrument_names:
            channels.append(f"incremental_ticker.{instrument}")
            channels.append(f"chart.trades.{instrument}.1")

        chunk_size = 100
        for i in range(0, len(channels), chunk_size):
            chunk = channels[i : i + chunk_size]
            msg = {
                "jsonrpc": "2.0",
                "id": int(time.time() * 1000) + i,
                "method": "private/subscribe",
                "params": {"channels": chunk},
            }
            log.info(f"[{self.exchange_name}] Sending subscription request for {len(chunk)} channels.")
            await self._send_json(msg)

    def _handle_control_message(self, data: dict) -> bool:
        method = data.get("method")
        if method == "heartbeat":
            params = data.get("params")
            if isinstance(params, dict) and params.get("type") == "test_request":
                asyncio.create_task(self._send_json({"jsonrpc": "2.0", "id": 0, "method": "public/test"}))
            return True
        if "id" in data and "result" in data:
            log.debug(f"Received RPC confirmation for request ID {data.get('id')}")
            return True
        return False

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        if not await self._load_instruments():
            log.error(f"[{self.exchange_name}] Instrument loading failed. Aborting connection attempt.")
            # Yield nothing and return, allowing the reconnect loop to handle backoff.
            return

        AUTH_ID = 9929
        # CORRECTED: Unwrap SecretStr objects to plain strings for serialization.
        auth_msg = {
            "jsonrpc": "2.0",
            "id": AUTH_ID,
            "method": "public/auth",
            "params": {
                "grant_type": "client_credentials",
                "client_id": self._client_id.get_secret_value(),
                "client_secret": self._client_secret.get_secret_value(),
            },
        }

        async with websockets.connect(self.ws_connection_url, ping_interval=None) as ws:
            self.websocket_client = ws
            log.info(f"[{self.exchange_name}] WebSocket connection established for '{self.market_def.market_id}'.")

            await self._send_json(auth_msg)
            is_authenticated = False

            async for message in ws:
                try:
                    data = orjson.loads(message)
                    if not isinstance(data, dict):
                        continue

                    if not is_authenticated:
                        if data.get("id") == AUTH_ID:
                            if "error" in data:
                                log.error(f"[{self.exchange_name}] Authentication failed: {data['error']}")
                                return # Abort on auth failure
                            log.info(f"[{self.exchange_name}] Authentication successful")
                            is_authenticated = True
                            await self._subscribe()
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
        log.info(f"[{self.exchange_name}] Starting message processor for '{self.market_def.market_id}'.")

        while self._is_running.is_set():
            try:
                batch = []
                async for message in self.connect():
                    if not self._is_running.is_set():
                        break
                    
                    reconnect_attempts = 0 # Reset on successful message
                    batch.append(message.model_dump(exclude_none=True))
                    
                    if len(batch) >= 100:
                        # CORRECTED: Implement a resilient batch flush to prevent data loss.
                        is_flushed = False
                        while not is_flushed:
                            try:
                                await self.redis_client.xadd_bulk(self.stream_name, batch)
                                is_flushed = True
                                log.debug(f"[{self.exchange_name}] Flushed batch of {len(batch)} messages.")
                                batch.clear()
                            except ConnectionError:
                                log.error(f"[{self.exchange_name}] Failed to flush batch to Redis. Retrying in 5s...")
                                await asyncio.sleep(5)
                                if not self._is_running.is_set():
                                    log.warning(f"[{self.exchange_name}] Shutdown initiated during Redis retry. Discarding batch.")
                                    break # Exit inner loop on shutdown

            except asyncio.CancelledError:
                break # Normal shutdown
            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, asyncio.TimeoutError) as e:
                log.warning(f"[{self.exchange_name}] WebSocket connection error: {type(e).__name__}. Will reconnect.")
            except Exception:
                log.exception(f"[{self.exchange_name}] Unhandled error in processor for '{self.market_def.market_id}'")
            finally:
                if self.websocket_client:
                    await self.websocket_client.close()
                    self.websocket_client = None
                
                if self._is_running.is_set():
                    reconnect_attempts += 1
                    delay = min(2**reconnect_attempts, 60) + random.random()
                    log.info(f"[{self.exchange_name}] Reconnecting in {delay:.1f}s...")
                    await asyncio.sleep(delay)

        log.info(f"[{self.exchange_name}] Message processor for '{self.market_def.market_id}' shut down.")

    async def close(self):
        log.info(f"[{self.exchange_name}] Closing client for '{self.market_def.market_id}'...")
        self._is_running.clear()
        if self.websocket_client:
            try:
                await self.websocket_client.close()
            except websockets.exceptions.ConnectionClosed:
                pass
        log.info(f"[{self.exchange_name}] Client for '{self.market_def.market_id}' closed.")