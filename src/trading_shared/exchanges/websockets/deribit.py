
# src/trading_shared/exchanges/websockets/deribit.py

# --- Built Ins ---
import asyncio
import time
from collections import deque
from typing import AsyncGenerator, Dict, List, Optional, Set

# --- Installed ---
import orjson
import websockets
from loguru import logger as log

# --- Local Application Imports ---
from ...config.models import ExchangeSettings
from ...repositories.instrument_repository import InstrumentRepository
from ...repositories.market_data_repository import MarketDataRepository
from ...repositories.system_state_repository import SystemStateRepository
from .base import AbstractWsClient

# --- Shared Library Imports ---
from trading_engine_core.models import MarketDefinition, StreamMessage


class DeribitWsClient(AbstractWsClient):
    """
    A self-managing, dynamic WebSocket client for Deribit. It maps canonical
    symbols to Deribit's format and maintains its own subscriptions.
    """

    def __init__(
        self,
        market_definition: MarketDefinition,
        market_data_repo: MarketDataRepository,
        instrument_repo: InstrumentRepository,
        system_state_repo: SystemStateRepository,
        stream_name: str,
        universe_state_key: str,
        redis_client: websockets.RedisClient,
        settings: ExchangeSettings,
        shard_id: int = 0,
        total_shards: int = 1,
    ):
        # FIX: Explicitly pass parent arguments to super().__init__
        super().__init__(
            market_definition=market_definition,
            market_data_repo=market_data_repo,
            instrument_repo=instrument_repo,
            system_state_repo=system_state_repo,
            stream_name=stream_name,
            universe_state_key=universe_state_key,
            redis_client=redis_client,
            shard_id=shard_id,
            total_shards=total_shards,
        )
        # Store child-specific dependencies
        self.settings = settings
        self.ws_connection_url = self.market_def.ws_base_url
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._connected = asyncio.Event()

    def _get_channels_from_universe(self, universe: List[str]) -> Set[str]:
        """
        Maps canonical universe symbols to Deribit's required channel name format.
        """
        my_targets = set()
        for symbol in universe:
            if symbol == "BTCUSDT":
                my_targets.add("trades.BTC-PERPETUAL.raw")
            elif symbol == "ETHUSDT":
                my_targets.add("trades.ETH-PERPETUAL.raw")
        return my_targets

    async def _send_rpc(self, method: str, channels: List[str]):
        """Safely sends a JSON-RPC formatted request to the WebSocket."""
        await self._connected.wait()
        if not self._ws or not channels:
            return

        try:
            msg = {
                "jsonrpc": "2.0",
                "id": int(time.time() * 1000),
                "method": method,
                "params": {"channels": channels},
            }
            log.debug(f"[{self.exchange_name}] Sending RPC: {msg}")
            await self._ws.send(orjson.dumps(msg))
        except websockets.exceptions.ConnectionClosed:
            log.warning(f"[{self.exchange_name}] Failed to send RPC: Connection is closed.")
        except Exception as e:
            log.error(f"[{self.exchange_name}] Unhandled error sending RPC: {e}")

    async def _send_subscribe(self, channels: List[str]):
        await self._send_rpc("public/subscribe", channels)

    async def _send_unsubscribe(self, channels: List[str]):
        await self._send_rpc("public/unsubscribe", channels)

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """Manages the raw WebSocket connection."""
        try:
            async with websockets.connect(self.ws_connection_url, ping_interval=30) as ws:
                self._ws = ws
                self._connected.set()
                log.success(f"[{self.exchange_name}] WebSocket connection established.")

                if self._active_channels:
                    log.info(f"[{self.exchange_name}] Re-subscribing to {len(self._active_channels)} active channels.")
                    await self._send_subscribe(list(self._active_channels))

                async for message in ws:
                    try:
                        data = orjson.loads(message)
                        params = data.get("params")
                        if isinstance(params, dict) and "channel" in params and "data" in params:
                            for trade in params["data"]:
                                yield StreamMessage(
                                    exchange=self.exchange_name,
                                    channel=params["channel"],
                                    timestamp=trade.get("timestamp"),
                                    data={
                                        "symbol": trade.get("instrument_name"),
                                        "price": trade.get("price"),
                                        "quantity": trade.get("amount"),
                                    },
                                )
                    except (orjson.JSONDecodeError, KeyError, TypeError) as e:
                        log.error(f"[{self.exchange_name}] Error processing message: {e}")
        finally:
            self._ws = None
            self._connected.clear()
            log.warning(f"[{self.exchange_name}] WebSocket connection closed.")

    async def _process_message_batch(self):
        """Inner loop that consumes from the `connect` generator and processes data."""
        batch = deque()
        async for message in self.connect():
            await self.market_data_repo.cache_ticker(message.data["symbol"], message.data)
            batch.append(message)
            if len(batch) >= 100:
                await self.market_data_repo.add_messages_to_stream(self.stream_name, list(batch))
                batch.clear()

    async def process_messages(self):
        """The main supervisor loop for this client."""
        self._is_running.set()
        reconnect_attempts = 0
        while self._is_running.is_set():
            subscription_task = asyncio.create_task(self._maintain_subscriptions())
            message_task = asyncio.create_task(self._process_message_batch())

            done, pending = await asyncio.wait(
                {subscription_task, message_task}, return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()

            if self._is_running.is_set():
                reconnect_attempts += 1
                delay = min(2**reconnect_attempts, 60)
                log.info(f"[{self.exchange_name}] Supervisor restarting tasks in {delay}s (attempt {reconnect_attempts})...")
                await asyncio.sleep(delay)

    async def close(self):
        """Initiates a graceful shutdown of the client."""
        log.info(f"[{self.exchange_name}] Closing client...")
        self._is_running.clear()
        if self._ws:
            await self._ws.close()
        log.info(f"[{self.exchange_name}] Client closed.")