# src/trading_shared/exchanges/websockets/binance.py

# --- Built Ins ---
import asyncio
from collections import deque
from typing import AsyncGenerator, Optional, List, Set

# --- Installed ---
import orjson
import websockets
from loguru import logger as log

# --- Local Application Imports ---
from ...clients.redis_client import CustomRedisClient
from ...config.models import ExchangeSettings
from ...repositories.instrument_repository import InstrumentRepository
from ...repositories.market_data_repository import MarketDataRepository
from ...repositories.system_state_repository import SystemStateRepository
from .base import AbstractWsClient

# --- Shared Library Imports ---
from trading_engine_core.models import MarketDefinition, StreamMessage


class BinanceWsClient(AbstractWsClient):
    """A self-managing, sharded WebSocket client for Binance."""

    def __init__(
        self,
        market_definition: MarketDefinition,
        market_data_repo: MarketDataRepository,
        instrument_repo: InstrumentRepository,
        system_state_repo: SystemStateRepository,
        stream_name: str,
        universe_state_key: str,
        settings: ExchangeSettings,
        shard_id: int,
        total_shards: int,
    ):
        super().__init__(
            market_definition,
            market_data_repo,
            stream_name,
            shard_id=shard_id,
            total_shards=total_shards,
        )
        self.instrument_repo = instrument_repo
        self.system_state_repo = system_state_repo
        self.universe_state_key = universe_state_key
        self.settings = settings
        # Note: shard_id and total_shards are now set on the base class.

        self.ws_connection_url = self.market_def.ws_base_url
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = asyncio.Event()

    async def _get_channels_from_universe(self, universe: List[str]) -> Set[str]:
        """
        Filters the canonical universe for this client's specific shard and
        maps the symbols to Binance's required channel name format.
        """
        my_targets = set()

        valid_symbols = [
            symbol for symbol in universe if "UP" not in symbol and "DOWN" not in symbol
        ]

        for i, symbol in enumerate(sorted(valid_symbols)):
            if i % self.total_shards == self.shard_id:
                my_targets.add(f"{symbol.lower()}@trade")
        return my_targets

    async def _send_request(self, method: str, params: List[str]):
        """Safely sends a subscription or unsubscription request to the WebSocket."""
        await self._connected.wait()
        if not self._ws or not params:
            return

        try:
            request_id = int(asyncio.get_running_loop().time() * 1000)
            payload = {"method": method.upper(), "params": params, "id": request_id}
            log.debug(f"[{self.market_def.market_id}] Sending WS request: {payload}")
            await self._ws.send(orjson.dumps(payload))
        except websockets.exceptions.ConnectionClosed:
            log.warning(
                f"[{self.market_def.market_id}] Failed to send request: Connection is closed."
            )
        except Exception as e:
            log.error(
                f"[{self.market_def.market_id}] Unhandled error sending request: {e}"
            )

    async def _send_subscribe(self, channels: List[str]):
        await self._send_request("SUBSCRIBE", channels)

    async def _send_unsubscribe(self, channels: List[str]):
        await self._send_request("UNSUBSCRIBE", channels)

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """
        Manages the raw WebSocket connection lifecycle and yields parsed messages.
        """
        try:
            async with websockets.connect(
                self.ws_connection_url, ping_interval=20, ping_timeout=60
            ) as ws:
                self._ws = ws
                self._connected.set()
                log.success(
                    f"[{self.market_def.market_id}] WebSocket connection established."
                )

                if self._active_channels:
                    log.info(
                        f"[{self.market_def.market_id}] Re-subscribing to {len(self._active_channels)} active channels."
                    )
                    await self._send_subscribe(list(self._active_channels))

                async for message in ws:
                    try:
                        payload = orjson.loads(message)
                        if "data" not in payload or "stream" not in payload:
                            continue
                        trade_data = payload["data"]
                        symbol = trade_data.get("s")
                        if not symbol:
                            continue

                        yield StreamMessage(
                            exchange=self.exchange_name,
                            channel=payload["stream"],
                            timestamp=trade_data.get("T"),
                            data={
                                "symbol": symbol,
                                "price": float(trade_data.get("p")),
                                "quantity": float(trade_data.get("q")),
                            },
                        )
                    except (orjson.JSONDecodeError, KeyError, TypeError) as e:
                        log.error(
                            f"[{self.market_def.market_id}] Error processing message: {e}"
                        )
        finally:
            self._ws = None
            self._connected.clear()
            log.warning(f"[{self.market_def.market_id}] WebSocket connection closed.")

    async def _process_message_batch(self):
        """Inner loop that consumes from the `connect` generator and processes data."""
        batch = deque()
        async for message in self.connect():
            await self.market_data_repo.cache_ticker(
                message.data["symbol"], message.data
            )
            batch.append(message)
            if len(batch) >= 100:
                await self.market_data_repo.add_messages_to_stream(
                    self.stream_name, list(batch)
                )
                batch.clear()

    async def process_messages(self):
        """
        The main public entry point and supervisor loop for this client.
        """
        self._is_running.set()
        reconnect_attempts = 0
        while self._is_running.is_set():
            try:
                subscription_task = asyncio.create_task(self._maintain_subscriptions())
                message_task = asyncio.create_task(self._process_message_batch())
                await asyncio.gather(subscription_task, message_task)
            except websockets.exceptions.ConnectionClosedError as e:
                log.warning(
                    f"[{self.market_def.market_id}] Connection closed with error: {e.code} {e.reason}"
                )
            except asyncio.CancelledError:
                log.info(f"[{self.market_def.market_id}] Supervisor tasks cancelled.")
                break  # Exit the loop cleanly on cancellation
            except Exception as e:
                log.error(
                    f"[{self.market_def.market_id}] Unhandled exception in supervisor: {e}",
                    exc_info=True,
                )

            if self._is_running.is_set():
                reconnect_attempts += 1
                delay = min(2**reconnect_attempts, 60)
                log.info(
                    f"[{self.market_def.market_id}] Supervisor restarting tasks in {delay}s (attempt {reconnect_attempts})..."
                )
                await asyncio.sleep(delay)

    async def close(self):
        """Initiates a graceful shutdown of the client."""
        log.info(f"[{self.market_def.market_id}] Closing client...")
        self._is_running.clear()
        if self._ws:
            await self._ws.close()
        log.info(f"[{self.market_def.market_id}] Client closed.")
