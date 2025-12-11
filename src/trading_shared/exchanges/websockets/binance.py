# src\trading_shared\exchanges\websockets\binance.py

# --- Built Ins  ---
import asyncio
from typing import AsyncGenerator, Set, List
from collections import deque

# --- Installed  ---
from loguru import logger as log
import orjson
import websockets

# --- Local Application Imports ---
from .base import AbstractWsClient
from ...clients.postgres_client import PostgresClient
from ...clients.redis_client import CustomRedisClient
from ...config.models import ExchangeSettings
from ...repositories.instrument_repository import InstrumentRepository
from ...repositories.market_data_repository import MarketDataRepository

# --- Shared Library Imports  ---
from trading_engine_core.models import StreamMessage, MarketDefinition


class BinanceWsClient(AbstractWsClient):
    """
    A dynamic, controllable WebSocket client for Binance that manages subscriptions on-the-fly
    via a Redis control channel. This implementation correctly implements the AbstractWsClient interface.
    """

    def __init__(
        self,
        market_definition: MarketDefinition,
        instrument_repo: InstrumentRepository,
        redis_client: CustomRedisClient,
        market_data_repo: MarketDataRepository,
        settings: ExchangeSettings,
        initial_subscriptions: List[str] | None = None,
    ):
        super().__init__(
            market_definition, market_data_repo, instrument_repo, redis_client
        )
        self.ws_connection_url = self.market_def.ws_base_url
        self._subscriptions: Set[str] = (
            set(initial_subscriptions) if initial_subscriptions else set()
        )
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._is_running = asyncio.Event()
        self._control_channel = f"control:{self.market_def.market_id}:subscriptions"
        self.settings = settings
        # The redis_client is now handled by the base class, but we keep the
        # reference here as this class has specific pub/sub logic.
        self.redis_client = redis_client
        if not self._control_channel:
            raise ValueError("Binance subscription control channel not configured.")

    async def _send_subscription_request(
        self,
        method: str,
        params: list,
    ):
        if not self._ws:
            log.warning("WebSocket is not connected. Cannot send subscription request.")
            return

        request_id = int(asyncio.get_running_loop().time() * 1000)
        payload = {"method": method, "params": params, "id": request_id}
        log.info(f"Sending request to Binance WS: {payload}")
        await self._ws.send(orjson.dumps(payload))

    async def _control_channel_listener(self):
        """Listens on a Redis channel for subscription management commands."""
        log.info(
            f"Listening for subscription commands on Redis channel: '{self._control_channel}'"
        )
        async with self.redis_client.pubsub() as pubsub:
            await pubsub.subscribe(self._control_channel)
            while self._is_running.is_set():
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                    if not message:
                        continue

                    log.info(f"Received command on control channel: {message['data']}")
                    command = orjson.loads(message["data"])
                    action = command.get("action")
                    symbols_to_modify = command.get("symbols", [])

                    if not symbols_to_modify:
                        continue

                    streams_to_modify = [
                        f"{symbol.lower().split('@')[0]}@aggTrade"
                        for symbol in symbols_to_modify
                    ]

                    if action == "subscribe":
                        new_subs = [
                            s for s in streams_to_modify if s not in self._subscriptions
                        ]
                        if new_subs:
                            await self._send_subscription_request("SUBSCRIBE", new_subs)
                            self._subscriptions.update(new_subs)

                    elif action == "unsubscribe":
                        old_subs = [
                            s for s in streams_to_modify if s in self._subscriptions
                        ]
                        if old_subs:
                            await self._send_subscription_request(
                                "UNSUBSCRIBE", old_subs
                            )
                            self._subscriptions.difference_update(old_subs)

                except asyncio.CancelledError:
                    break  # Graceful shutdown
                except Exception as e:
                    log.error(f"Error in control channel listener: {e}", exc_info=True)
                    await asyncio.sleep(5)

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """
        Main message generator loop. Connects to the WebSocket and yields messages.
        This method now correctly implements the 'connect' abstract method.
        """
        stream_names = "/".join(self._subscriptions)
        if not stream_names:
            log.warning(
                f"[{self.exchange_name}] No streams to subscribe to for market '{self.market_def.market_id}'. Client will be idle until commanded."
            )
            # Simple return to allow the reconnect loop to handle the delay.
            return

        url = f"{self.ws_connection_url}?streams={stream_names}"

        try:
            log.info(f"[{self.exchange_name}] Connecting to: {url}")
            async with websockets.connect(url, ping_interval=20, ping_timeout=60) as ws:
                self._ws = ws
                log.success(
                    f"[{self.exchange_name}] WebSocket connection established for market '{self.market_def.market_id}'."
                )

                async for message in ws:
                    try:
                        payload = orjson.loads(message)
                        if "data" not in payload or "stream" not in payload:
                            continue

                        trade_data = payload["data"]
                        stream_name = payload["stream"]
                        symbol = stream_name.split("@")[0].upper()

                        # Use market_type from the MarketDefinition object
                        market_type_str = self.market_def.market_type.value

                        yield StreamMessage(
                            exchange=self.exchange_name,
                            channel=f"aggTrade.{symbol}.{market_type_str}",
                            timestamp=trade_data.get("T"),
                            data={
                                "symbol": symbol,
                                "market_type": market_type_str,
                                "trade_id": trade_data.get("a"),
                                "price": float(trade_data.get("p")),
                                "quantity": float(trade_data.get("q")),
                                "is_buyer_maker": trade_data.get("m"),
                                "was_best_price_match": trade_data.get("M"),
                            },
                        )
                    except (orjson.JSONDecodeError, TypeError, KeyError) as e:
                        log.error(
                            f"[{self.exchange_name}] Error processing message: {e}. Payload: {message}",
                            exc_info=True,
                        )
        finally:
            self._ws = None  # Ensure websocket object is cleared on exit
            log.warning(f"[{self.exchange_name}] Disconnected from {url}.")

    async def process_messages(self):
        """
        Manages the service lifecycle and reconnect loop.
        This method now correctly implements the 'process_messages' abstract method.
        """
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
                    reconnect_attempts = 0  # Reset on successful message

                    # Update Redis ticker snapshot
                    await self.market_data_repo.cache_ticker(
                        message.data["symbol"], message.data
                    )

                    # Append to batch for stream
                    batch.append(message)
                    if len(batch) >= 100:
                        await self.market_data_repo.add_messages_to_stream(
                            self.stream_name, batch
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
        """
        Gracefully shuts down the websocket client.
        This method now correctly implements the 'close' abstract method.
        """

        log.info(
            f"[{self.exchange_name}] Closing client for '{self.market_def.market_id}'..."
        )
        self._is_running.clear()
        if self._ws and self._ws.open:
            await self._ws.close()
        log.info(
            f"[{self.exchange_name}] Client for '{self.market_def.market_id}' closed."
        )
