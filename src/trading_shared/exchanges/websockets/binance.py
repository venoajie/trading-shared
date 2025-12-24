
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
        market_id_suffix: str = "",
        control_channel: str | None = None,
    ):
        super().__init__(
            market_definition, market_data_repo, instrument_repo, redis_client
        )
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
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._is_running = asyncio.Event()

        # [CORRECTION] Make control_channel a public attribute to define a clear interface.
        if control_channel:
            self.control_channel = control_channel
        else:
            self.control_channel = f"control:{self.market_def.market_id}:subscriptions"

        self.settings = settings
        self.redis_client = redis_client
        if not self.control_channel:
            raise ValueError("Binance subscription control channel not configured.")

    async def _send_subscription_request(self, method: str, params: list):
        # [CORRECTION] Add a robust type guard to prevent crashes from state pollution.
        if not isinstance(self._ws, websockets.WebSocketClientProtocol) or not self._ws.open:
            if self._ws is not None:
                # This log is critical for diagnosing the root cause.
                log.critical(
                    f"[{self.market_def.market_id}] State pollution detected! "
                    f"_ws attribute is of type '{type(self._ws).__name__}' instead of 'WebSocketClientProtocol'. "
                    f"Value: {self._ws}. Cannot send subscription request."
                )
            else:
                log.warning(f"[{self.market_def.market_id}] WebSocket is not connected. Cannot send '{method}' request.")
            return

        request_id = int(asyncio.get_running_loop().time() * 1000)
        payload = {"method": method.upper(), "params": params, "id": request_id}
        log.info(f"[{self.market_def.market_id}] Sending WS request: {payload}")
        await self._ws.send(orjson.dumps(payload))

    async def _control_channel_listener(self):
        """
        Listens for universe state updates and calculates subscription deltas.
        """
        log.info(f"[{self.market_def.market_id}] Listening for commands on '{self.control_channel}'")

        while self._is_running.is_set():
            try:
                async with self.redis_client.pubsub() as pubsub:
                    await pubsub.subscribe(self.control_channel)
                    while self._is_running.is_set():
                        try:
                            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                            if not message:
                                continue

                            log.info(f"[{self.market_def.market_id}] Received new universe state on control channel.")
                            full_universe_symbols: List[str] = orjson.loads(message["data"])

                            num_clients = 5
                            client_index = int(self.market_def.market_id.split('_')[-1]) - 1
                            
                            chunk_symbols = sorted(full_universe_symbols)[client_index::num_clients]
                            
                            target_streams = {f"{symbol.lower()}@trade" for symbol in chunk_symbols}

                            streams_to_add = list(target_streams - self._subscriptions)
                            streams_to_remove = list(self._subscriptions - target_streams)

                            if not streams_to_add and not streams_to_remove:
                                continue

                            if streams_to_remove:
                                await self._send_subscription_request("UNSUBSCRIBE", streams_to_remove)
                            
                            if streams_to_add:
                                await self._send_subscription_request("SUBSCRIBE", streams_to_add)

                            self._subscriptions = target_streams
                            log.success(f"[{self.market_def.market_id}] Subscriptions updated: {len(streams_to_add)} added, {len(streams_to_remove)} removed.")

                        except (orjson.JSONDecodeError, KeyError, TypeError) as e:
                            log.warning(f"[{self.market_def.market_id}] Invalid command received: {e}")
                        except (ConnectionError, OSError) as e:
                            log.warning(f"[{self.market_def.market_id}] Control channel connection lost: {e}. Reconnecting...")
                            break
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"[{self.market_def.market_id}] Unexpected error in control channel listener: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        url = f"{self.ws_connection_url}"

        try:
            log.info(f"[{self.exchange_name}] Connecting to: {url}")
            async with websockets.connect(url, ping_interval=20, ping_timeout=60) as ws:
                self._ws = ws
                log.success(f"[{self.exchange_name}] WebSocket connection established for '{self.market_def.market_id}'.")

                if self._subscriptions:
                    await self._send_subscription_request("SUBSCRIBE", list(self._subscriptions))

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
                        log.error(f"[{self.exchange_name}] Error processing message: {e}. Payload: {message}", exc_info=True)
        finally:
            self._ws = None
            log.warning(f"[{self.exchange_name}] Disconnected from {url}.")

    async def process_messages(self):
        self._is_running.set()
        log.info(f"[{self.exchange_name}] Starting message processor for '{self.market_def.market_id}'.")
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
                    await self.market_data_repo.cache_ticker(message.data["symbol"], message.data)
                    batch.append(message)
                    if len(batch) >= 100:
                        await self.market_data_repo.add_messages_to_stream(self.stream_name, list(batch))
                        batch.clear()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"[{self.exchange_name}] Unhandled error in processor for '{self.market_def.market_id}': {e}", exc_info=True)
            finally:
                if self._is_running.is_set():
                    reconnect_attempts += 1
                    delay = min(2**reconnect_attempts, 60)
                    log.info(f"[{self.exchange_name}] Message stream for '{self.market_def.market_id}' ended. Reconnecting in {delay}s...")
                    await asyncio.sleep(delay)
        listener_task.cancel()
        await asyncio.gather(listener_task, return_exceptions=True)
        log.info(f"[{self.exchange_name}] Message processor for '{self.market_def.market_id}' shut down.")

    async def close(self):
        log.info(f"[{self.exchange_name}] Closing client for '{self.market_def.market_id}'...")
        self._is_running.clear()
        if self._ws and self._ws.open:
            await self._ws.close()
        log.info(f"[{self.exchange_name}] Client for '{self.market_def.market_id}' closed.")