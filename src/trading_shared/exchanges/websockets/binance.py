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
        # Suffix to identify connection chunks in logs
        market_id_suffix: str = "",
        control_channel: str | None = None,
    ):
        super().__init__(
            market_definition, market_data_repo, instrument_repo, redis_client
        )
        # Adjust market_id for logging
        if market_id_suffix:
            self.market_def.market_id = (
                f"{self.market_def.market_id}_{market_id_suffix}"
            )

        self.ws_connection_url = self.market_def.ws_base_url
        self.instruments_to_subscribe = instruments_to_subscribe
        self._subscriptions: Set[str] = {
            f"{inst['instrument_name'].lower()}@trade"
            for inst in self.instruments_to_subscribe
        }

        # NEW: Set of instrument names for this chunk
        self._chunk_instrument_names = {
            inst["instrument_name"].lower() for inst in self.instruments_to_subscribe
        }

        self._ws: websockets.WebSocketClientProtocol | None = None
        self._is_running = asyncio.Event()

        # Set control channel (shared or per-chunk)
        if control_channel:
            self._control_channel = control_channel
        else:
            self._control_channel = f"control:{self.market_def.market_id}:subscriptions"

        self.settings = settings
        self.redis_client = redis_client
        self._redis_semaphore = asyncio.Semaphore(5)  # Limit concurrent Redis ops
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

                    log.info(
                        f"Received command on control channel: {message['data']}"
                    )
                    command = orjson.loads(message["data"])
                    action = command.get("action")
                    symbols_to_modify = command.get("symbols", [])

                    if not symbols_to_modify:
                        continue

                    # FILTER: Only process symbols in this chunk's instrument list
                    filtered_symbols = [
                        symbol
                        for symbol in symbols_to_modify
                        if symbol.lower() in self._chunk_instrument_names
                    ]

                    if not filtered_symbols:
                        log.debug(
                            f"No relevant symbols for chunk '{self.market_def.market_id}' in command"
                        )
                        continue

                    # NOTE: Binance uses @aggTrade for aggregated trades. Using @trade for raw.
                    streams_to_modify = [
                        f"{symbol.lower().split('@')[0]}@trade"
                        for symbol in filtered_symbols
                    ]

                    if action == "subscribe":
                        new_subs = [
                            s
                            for s in streams_to_modify
                            if s not in self._subscriptions
                        ]
                        if new_subs:
                            await self._send_subscription_request(
                                "SUBSCRIBE", new_subs
                            )
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
                    break
                except Exception as e:
                    log.error(
                        f"Error in control channel listener: {e}", exc_info=True
                    )
                    await asyncio.sleep(5)

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """
        Main message generator loop. Connects to the WebSocket and yields messages.
        """
        stream_names = "/".join(self._subscriptions)
        if not stream_names:
            log.warning(
                f"[{self.exchange_name}] No streams to subscribe to for market '{self.market_def.market_id}'. Client will be idle."
            )
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
                        market_type_str = self.market_def.market_type.value

                        yield StreamMessage(
                            exchange=self.exchange_name,
                            channel=f"trade.{symbol}.{market_type_str}",  # Use 'trade' for consistency
                            timestamp=trade_data.get("T"),
                            data={
                                "symbol": symbol,
                                "market_type": market_type_str,
                                "trade_id": trade_data.get(
                                    "t"
                                ),  # 't' is trade ID for individual trades
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
            log.warning(f"[{self.exchange_name}] Disconnected from {url}.")

    async def process_messages(self):
        """
        Manages the service lifecycle and reconnect loop.
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
                    reconnect_attempts = 0

                    await self.market_data_repo.cache_ticker(
                        message.data["symbol"], message.data
                    )

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
