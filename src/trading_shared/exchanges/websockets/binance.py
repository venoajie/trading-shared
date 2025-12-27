# src/trading_shared/exchanges/websockets/binance.py

# --- Built Ins  ---
import asyncio
from typing import Any, AsyncGenerator, Dict, List, Set
from collections import deque

# --- Installed  ---
from loguru import logger as log
import orjson
import websockets

# --- Local Application Imports ---
from .base import AbstractWsClient
from ...clients.redis_client import CustomRedisClient
from ...config.models import ExchangeSettings
from ...repositories.instrument_repository import InstrumentRepository
from ...repositories.market_data_repository import MarketDataRepository

# --- Shared Library Imports  ---
from trading_engine_core.models import StreamMessage, MarketDefinition


class BinanceWsClient(AbstractWsClient):
    """
    A dynamic WebSocket client for Binance. Each instance manages a single connection
    for a chunk of instrument streams.
    """

    def __init__(
        self,
        market_definition: MarketDefinition,
        instrument_repo: InstrumentRepository,
        redis_client: CustomRedisClient,
        market_data_repo: MarketDataRepository,
        settings: ExchangeSettings,
        instruments_to_subscribe: List[Dict[str, Any]],
        stream_name: str,
        market_id_suffix: str = "",
        control_channel: str | None = None,
    ):
        super().__init__(
            market_definition,
            market_data_repo,
            instrument_repo,
            redis_client,
            stream_name=stream_name,
        )
        self.market_id_suffix = market_id_suffix
        if self.market_id_suffix:
            self.market_def.market_id = (
                f"{self.market_def.market_id}_{self.market_id_suffix}"
            )
        self.ws_connection_url = self.market_def.ws_base_url
        self.instruments_to_subscribe = instruments_to_subscribe
        self._subscriptions: Set[str] = {
            f"{inst['instrument_name'].lower()}@trade"
            for inst in self.instruments_to_subscribe
        }
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._is_running = asyncio.Event()

        # Introduce an asyncio.Event to manage and signal connection state.
        self._connected = asyncio.Event()

        self.control_channel = control_channel
        if not self.control_channel:
            raise ValueError("Binance subscription control channel not configured.")

    async def _send_subscription_request(self, method: str, params: list):
        await self._connected.wait()

        if not self._ws or not self._ws.open:
            log.warning(
                f"[{self.market_def.market_id}] WebSocket is not connected. Cannot send '{method}' request."
            )
            return

        # An empty params list is a valid way to unsubscribe from all streams.
        if not params and method == "SUBSCRIBE":
            log.warning(
                f"[{self.market_def.market_id}] Received empty subscription list. Unsubscribing from all streams."
            )
            method = "UNSUBSCRIBE"
            params = list(
                self._subscriptions
            )  # Unsubscribe from what we currently have
            if not params:
                return  # Nothing to do

        request_id = int(asyncio.get_running_loop().time() * 1000)
        payload = {"method": method.upper(), "params": params, "id": request_id}
        log.info(f"[{self.market_def.market_id}] Sending WS request: {payload}")
        await self._ws.send(orjson.dumps(payload))

    async def _control_channel_listener(self):
        log.info(
            f"[{self.market_def.market_id}] Listening for commands on '{self.control_channel}'"
        )

        while self._is_running.is_set():
            try:
                async with self.redis_client.pubsub() as pubsub:
                    await pubsub.subscribe(self.control_channel)
                    while self._is_running.is_set():
                        message = await pubsub.get_message(
                            ignore_subscribe_messages=True, timeout=1.0
                        )
                        if not message:
                            continue

                        try:
                            command = orjson.loads(message["data"])

                            if command.get("chunk_id") != self.market_id_suffix:
                                continue

                            log.info(
                                f"[{self.market_def.market_id}] Received targeted command."
                            )
                            target_streams = set(command.get("streams", []))

                            # Do not calculate a diff. The command represents the desired state.
                            # A single SUBSCRIBE call to the Binance API with the new list will
                            # automatically handle unsubscribing from old streams and subscribing to new ones.
                            if target_streams == self._subscriptions:
                                continue  # No change needed

                            await self._send_subscription_request(
                                "SUBSCRIBE", list(target_streams)
                            )

                            self._subscriptions = target_streams
                            log.success(
                                f"[{self.market_def.market_id}] Subscription state set to {len(target_streams)} streams."
                            )

                        except (orjson.JSONDecodeError, KeyError, TypeError) as e:
                            log.warning(
                                f"[{self.market_def.market_id}] Invalid command received: {e}"
                            )
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(
                    f"[{self.market_def.market_id}] Unexpected error in control channel listener: {e}",
                    exc_info=True,
                )
                await asyncio.sleep(5)

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        url = f"{self.ws_connection_url}"
        try:
            log.info(f"[{self.exchange_name}] Connecting to: {url}")
            async with websockets.connect(url, ping_interval=20, ping_timeout=60) as ws:
                self._ws = ws
                log.success(
                    f"[{self.exchange_name}] WebSocket connection established for '{self.market_def.market_id}'."
                )

                # Set the event to signal that the connection is live and ready.
                self._connected.set()

                # Resubscribe to current state on reconnect
                if self._subscriptions:
                    await self._send_subscription_request(
                        "SUBSCRIBE", list(self._subscriptions)
                    )

                async for message in ws:
                    try:
                        payload = orjson.loads(message)
                        if "data" not in payload or "stream" not in payload:
                            continue
                        trade_data = payload["data"]
                        stream_name = payload["stream"]
                        symbol = stream_name.split("@")[0].upper()
                        market_type_str = self.market_def.market_type.value
                        yield StreamMessage(
                            exchange=self.exchange_name,
                            channel=f"trade.{symbol}.{market_type_str}",
                            timestamp=trade_data.get("T"),
                            data={
                                "symbol": symbol,
                                "market_type": market_type_str,
                                "trade_id": trade_data.get("t"),
                                "price": float(trade_data.get("p")),
                                "quantity": float(trade_data.get("q")),
                                "is_buyer_maker": trade_data.get("m"),
                            },
                        )
                    except (orjson.JSONDecodeError, TypeError, KeyError) as e:
                        log.error(
                            f"[{self.exchange_name}] Error processing message: {e}. Payload: {message}",
                            exc_info=True,
                        )
        finally:
            self._ws = None
            # Clear the event to signal that the connection is down.
            self._connected.clear()
            log.warning(f"[{self.exchange_name}] Disconnected from {url}.")

    async def process_messages(self):
        self._is_running.set()
        log.info(
            f"[{self.exchange_name}] Starting message processor for '{self.market_def.market_id}'."
        )
        listener_task = asyncio.create_task(self._control_channel_listener())
        reconnect_attempts = 0
        while self._is_running.is_set():
            try:
                batch = deque()
                message_generator = self.connect()
                async for message in message_generator:
                    if not self._is_running.is_set():
                        break
                    reconnect_attempts = 0
                    await self.market_data_repo.cache_ticker(
                        message.data["symbol"], message.data
                    )
                    batch.append(message)
                    if len(batch) >= 100:
                        await self.market_data_repo.add_messages_to_stream(
                            self.stream_name, list(batch)
                        )
                        batch.clear()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(
                    f"[{self.exchange_name}] Unhandled error in processor for '{self.market_def.market_id}': {e}",
                    exc_info=True,
                )
            finally:
                if self._is_running.is_set():
                    reconnect_attempts += 1
                    delay = min(2**reconnect_attempts, 60)
                    log.info(
                        f"[{self.exchange_name}] Message stream for '{self.market_def.market_id}' ended. Reconnecting in {delay}s..."
                    )
                    await asyncio.sleep(delay)
        listener_task.cancel()
        await asyncio.gather(listener_task, return_exceptions=True)
        log.info(
            f"[{self.exchange_name}] Message processor for '{self.market_def.market_id}' shut down."
        )

    async def close(self):
        log.info(
            f"[{self.exchange_name}] Closing client for '{self.market_def.market_id}'..."
        )
        self._is_running.clear()
        if self._ws and self._ws.open:
            await self._ws.close()
        log.info(
            f"[{self.exchange_name}] Client for '{self.market_def.market_id}' closed."
        )
