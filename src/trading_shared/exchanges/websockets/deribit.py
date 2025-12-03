# src\trading_shared\exchange\websockets\deribit.py

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

# --- Local Application Imports ---
from ...clients.redis_client import CustomRedisClient
from ...clients.postgres_client import PostgresClient
from ...config.models import ExchangeSettings # Configuration model
#from ..trading.deribit_constants import WebsocketParameters
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
        market_def: MarketDefinition,
        settings: ExchangeSettings,
    ):
        self.redis = redis_client
        self.market_def = market_def
        self.settings = settings

        super().__init__(market_definition, redis_client, postgres_client)
        self.ws_connection_url = self.market_def.ws_base_url
        if not self.ws_connection_url:
            raise ValueError("Deribit ws_url not configured.")

        self.client_id = settings.exchanges["deribit"].client_id
        self.client_secret = settings.exchanges["deribit"].client_secret
        self.websocket_client: Optional[websockets.WebSocketClientProtocol] = None
        self.last_message_time = 0.0
        self.reconnect_attempts = 0
        self.monitor_task: Optional[asyncio.Task] = None
        self.redis_pool = None
        self.instrument_names: List[str] = []

    async def _send_json(
        self,
        data: dict,
    ):
        """Use standard json for Deribit compatibility"""
        if self.websocket_client and self.websocket_client.open:
            await self.websocket_client.send(json.dumps(data))

    async def _auth(self) -> bool:
        """
        [REFACTORED] Authenticates and waits specifically for the auth response,
        ignoring other messages. This prevents race conditions.
        """
        AUTH_ID = 9929
        msg = {
            "jsonrpc": "2.0",
            "id": AUTH_ID,
            "method": "public/auth",
            "params": {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        }
        await self._send_json(msg)

        try:
            # Loop and wait specifically for the message with our AUTH_ID
            while True:
                response_raw = await asyncio.wait_for(
                    self.websocket_client.recv(), timeout=10.0
                )
                data = orjson.loads(response_raw)

                if not isinstance(data, dict):
                    continue

                if data.get("id") == AUTH_ID:
                    # This is our auth response.
                    result = data.get("result")
                    if isinstance(result, dict) and result.get("access_token"):
                        log.info(f"[{self.exchange_name}] Authentication successful")
                        return True

                    error_details = data.get(
                        "error", f"No access token in result: {result}"
                    )
                    log.error(
                        f"[{self.exchange_name}] Authentication failed: {error_details}"
                    )
                    return False
                else:
                    # This is another message (e.g., heartbeat confirmation). Ignore it.
                    log.debug(
                        f"Ignoring message while waiting for auth response: {data}"
                    )

        except asyncio.TimeoutError:
            log.error(
                f"[{self.exchange_name}] Timed out waiting for authentication response."
            )
            return False
        except Exception as e:
            log.error(
                f"[{self.exchange_name}] Exception during authentication: {e}",
                exc_info=True,
            )
            return False

    async def _load_instruments(self):
        """Cache instruments to avoid DB queries on every reconnect"""
        if not self.instrument_names:
            records = await self.postgres_client.fetch_all_instruments()
            self.instrument_names = [
                r["instrument_name"]
                for r in records
                if r["exchange"] == self.exchange_name
                and r["market_type"] == self.market_def.market_type.value
            ]

            if not self.instrument_names:
                log.warning(
                    f"[{self.exchange_name}] No instruments found in DB to subscribe to."
                )

    async def _subscribe(self):
        """
        Loads instruments with a retry mechanism before
        sending the subscription request. This prevents a race condition on startup
        where the client might start before the janitor has finished populating the DB.
        """
        max_instrument_load_attempts = 5
        for attempt in range(max_instrument_load_attempts):
            await self._load_instruments()
            if self.instrument_names:
                log.info(
                    f"[{self.exchange_name}] Successfully loaded {len(self.instrument_names)} instruments for subscription."
                )
                break
            else:
                log.warning(
                    f"[{self.exchange_name}] Instrument list is empty (attempt {attempt + 1}/{max_instrument_load_attempts}). Janitor may still be running. Retrying in 10 seconds..."
                )
                await asyncio.sleep(10)
        else:  # This 'else' belongs to the 'for' loop
            log.error(
                f"[{self.exchange_name}] Failed to load instruments after {max_instrument_load_attempts} attempts. Client will be idle for this connection."
            )
            return  # Exit without subscribing if no instruments are found

        channels = ["user.orders.any.any.raw", "user.trades.any.any.raw"]
        for instrument in self.instrument_names:
            channels.append(f"incremental_ticker.{instrument}")
            channels.append(f"chart.trades.{instrument}.1")

        chunk_size = 100
        for i in range(0, len(channels), chunk_size):
            chunk = channels[i : i + chunk_size]
            msg = {
                "jsonrpc": "2.0",
                "id": int(time.time() * 1000),
                "method": "private/subscribe",
                "params": {"channels": chunk},
            }
            log.info(
                f"[{self.exchange_name}] Sending subscription request for {len(chunk)} channels."
            )
            await self._send_json(msg)

    async def _monitor_connection(self):
        """Safer connection monitoring"""
        try:
            while self.websocket_client and not self.websocket_client.closed:
                await asyncio.sleep(5)
                current_time = time.time()
                elapsed = current_time - self.last_message_time
                if (
                    self.last_message_time > 0
                    and elapsed > WebsocketParameters.WEBSOCKET_TIMEOUT
                ):
                    log.warning(
                        f"WebSocket timeout detected ({elapsed:.1f}s). Forcing reconnect."
                    )
                    await self.websocket_client.close()
                    break
        except asyncio.CancelledError:
            log.debug("Monitor task cancelled normally")
        except Exception as e:
            log.error(f"Monitor task failed: {e}")

    def _handle_control_message(self, data: dict) -> bool:
        """
        Handles heartbeat requests and other non-data messages.
        Returns True if the message was a control message, False otherwise.
        """
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

        # This will now handle subscription confirmations and other RPC responses.
        if "id" in data and "result" in data:
            log.debug(f"Received RPC confirmation for request ID {data.get('id')}")
            return True

        return False

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        while True:
            try:
                delay = min(2**self.reconnect_attempts, 30) + random.random()
                if self.reconnect_attempts > 0:
                    log.info(f"[{self.exchange_name}] Reconnecting in {delay:.1f}s...")
                    await asyncio.sleep(delay)

                async with websockets.connect(
                    self.ws_connection_url, ping_interval=None
                ) as ws:
                    self.websocket_client = ws
                    self.reconnect_attempts = 0
                    self.last_message_time = 0.0
                    log.info(f"[{self.exchange_name}] WebSocket connection established")

                    self.monitor_task = asyncio.create_task(self._monitor_connection())

                    if not self.redis_pool:
                        self.redis_pool = await self.redis_client.get_pool()

                    # Send heartbeat setup but don't wait for response here.
                    await self._send_json(
                        {
                            "jsonrpc": "2.0",
                            "id": 0,
                            "method": "public/set_heartbeat",
                            "params": {"interval": 30},
                        }
                    )

                    # Authenticate robustly
                    if not await self._auth():
                        log.error("Authentication failed, will retry connection.")
                        continue

                    # Subscribe and start processing
                    await self._subscribe()
                    self.last_message_time = time.time()

                    async for message in ws:
                        self.last_message_time = time.time()
                        try:
                            data = orjson.loads(message)

                            if not isinstance(data, dict):
                                log.debug(f"Received non-dictionary message: {data}")
                                continue

                            if self._handle_control_message(data):
                                continue

                            params = data.get("params")
                            if (
                                isinstance(params, dict)
                                and "channel" in params
                                and "data" in params
                            ):
                                channel = params["channel"]
                                payload = params["data"]

                                if "incremental_ticker" in channel:
                                    instrument_name = channel.split(".")[1]
                                    redis_key = f"ticker:{instrument_name}"
                                    await self.redis_pool.hset(
                                        redis_key, "payload", orjson.dumps(payload)
                                    )

                                yield StreamMessage(
                                    exchange=self.exchange_name,
                                    channel=channel,
                                    timestamp=int(time.time() * 1000),
                                    data=payload,
                                )
                            else:
                                log.warning(f"Unhandled data message: {data}")

                        except orjson.JSONDecodeError:
                            log.error(f"Invalid JSON received: {message[:100]}...")
                        except Exception as e:
                            log.error(
                                f"Error processing message: {e} - Payload: {message[:200]}",
                                exc_info=True,
                            )

            except (websockets.ConnectionClosed, ConnectionError) as e:
                log.warning(f"Connection closed: {e}")
                self.reconnect_attempts += 1
            except Exception as e:
                log.error(f"Unexpected error in connect loop: {e}", exc_info=True)
                self.reconnect_attempts += 1
            finally:
                if self.monitor_task and not self.monitor_task.done():
                    self.monitor_task.cancel()
                    try:
                        await self.monitor_task
                    except asyncio.CancelledError:
                        pass
                self.monitor_task = None


