
# src/trading_shared/exchanges/websockets/binance.py

# --- Built Ins ---
import asyncio
import random
from collections import deque
from typing import AsyncGenerator, Dict, List, Set

# --- Installed ---
import orjson
import websockets
from loguru import logger as log

# --- Local Application Imports ---
from .base import AbstractWsClient

# --- Shared Library Imports ---
from trading_engine_core.models import StreamMessage


class BinanceWsClient(AbstractWsClient):
    """
    A self-managing, sharded WebSocket client for Binance. It autonomously polls the
    active universe, manages its own subscriptions, and handles reconnections.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ws_connection_url = self.market_def.ws_base_url
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._connected = asyncio.Event()

    def _get_channels_from_universe(self, universe: List[str]) -> Set[str]:
        """
        Filters the canonical universe for this client's specific shard and
        maps the symbols to Binance's required channel name format.
        """
        my_targets = set()
        # Sort for deterministic, stable sharding across all instances
        for i, symbol in enumerate(sorted(universe)):
            if i % self.total_shards == self.shard_id:
                # Map canonical symbol "BTCUSDT" to Binance stream name "btcusdt@trade"
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
            log.warning(f"[{self.market_def.market_id}] Failed to send request: Connection is closed.")
        except Exception as e:
            log.error(f"[{self.market_def.market_id}] Unhandled error sending request: {e}")

    async def _send_subscribe(self, channels: List[str]):
        await self._send_request("SUBSCRIBE", channels)

    async def _send_unsubscribe(self, channels: List[str]):
        await self._send_request("UNSUBSCRIBE", channels)

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """
        Manages the raw WebSocket connection lifecycle and yields parsed messages.
        This is the inner data pump for the supervisor.
        """
        try:
            async with websockets.connect(self.ws_connection_url, ping_interval=20, ping_timeout=60) as ws:
                self._ws = ws
                self._connected.set()
                log.success(f"[{self.market_def.market_id}] WebSocket connection established.")

                # On a successful reconnect, immediately re-apply the last known subscriptions.
                if self._active_channels:
                    log.info(f"[{self.market_def.market_id}] Re-subscribing to {len(self._active_channels)} active channels.")
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
                        log.error(f"[{self.market_def.market_id}] Error processing message: {e}")
        finally:
            self._ws = None
            self._connected.clear()
            log.warning(f"[{self.market_def.market_id}] WebSocket connection closed.")

    async def _process_message_batch(self):
        """Inner loop that consumes from the `connect` generator and processes data."""
        batch = deque()
        async for message in self.connect():
            # Cache the latest ticker price for low-latency access by other services.
            await self.market_data_repo.cache_ticker(message.data["symbol"], message.data)

            # Batch messages for efficient writing to the main Redis Stream.
            batch.append(message)
            if len(batch) >= 100:
                await self.market_data_repo.add_messages_to_stream(self.stream_name, list(batch))
                batch.clear()

    async def process_messages(self):
        """
        The main public entry point and supervisor loop for this client. It tightly
        couples the subscription and message processing tasks. If either fails,
        both are restarted to ensure a consistent state.
        """
        self._is_running.set()
        reconnect_attempts = 0
        while self._is_running.is_set():
            subscription_task = asyncio.create_task(self._maintain_subscriptions())
            message_task = asyncio.create_task(self._process_message_batch())

            # Wait for either task to complete (which indicates a failure or disconnection).
            done, pending = await asyncio.wait(
                {subscription_task, message_task}, return_when=asyncio.FIRST_COMPLETED
            )

            # Clean up any lingering tasks.
            for task in pending:
                task.cancel()

            # If the service is still supposed to be running, log and apply backoff.
            if self._is_running.is_set():
                reconnect_attempts += 1
                delay = min(2**reconnect_attempts, 60)
                log.info(f"[{self.market_def.market_id}] Supervisor restarting tasks in {delay}s (attempt {reconnect_attempts})...")
                await asyncio.sleep(delay)

    async def close(self):
        """Initiates a graceful shutdown of the client."""
        log.info(f"[{self.market_def.market_id}] Closing client...")
        self._is_running.clear()
        if self._ws:
            await self._ws.close()
        log.info(f"[{self.market_def.market_id}] Client closed.")
