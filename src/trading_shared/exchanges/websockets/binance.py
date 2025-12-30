# src/trading_shared/exchanges/websockets/binance.py
# --- Built Ins ---
import asyncio
import time
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


class BinanceWsClient(AbstractWsClient):
    """A self-managing, sharded WebSocket client for Binance public trade data."""

    def __init__(
        self,
        market_definition: MarketDefinition,
        market_data_repo: MarketDataRepository,
        instrument_repo: InstrumentRepository,
        system_state_repo: SystemStateRepository,
        universe_state_key: str,
        settings: ExchangeSettings,
        shard_id: int,
        total_shards: int,
    ):
        super().__init__(
            market_definition,
            market_data_repo,
            shard_id=shard_id,
            total_shards=total_shards,
        )
        self.instrument_repo = instrument_repo
        self.system_state_repo = system_state_repo
        self.universe_state_key = universe_state_key
        self.settings = settings

        self.ws_connection_url = self.market_def.ws_base_url
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = asyncio.Event()

    async def _get_channels_from_universe(
        self, universe: List[Dict[str, any]]
    ) -> Set[str]:
        """
        FIX: Correctly parses the rich universe object to extract symbols.
        This method now correctly consumes the state published by the strategist.
        """
        my_targets = set()
        for instrument_data in universe:
            # 1. Ensure the instrument belongs to this exchange.
            if instrument_data.get("exchange") == self.exchange_name:
                # 2. Extract the simple string symbol from the rich object.
                symbol = instrument_data.get("spot_symbol")
                if symbol:
                    my_targets.add(symbol)

        # 3. Apply sharding logic to the final list of symbols.
        sharded_targets = {
            symbol
            for i, symbol in enumerate(sorted(list(my_targets)))
            if i % self.total_shards == self.shard_id
        }

        # 4. Format the symbols into valid Binance channel names.
        return {f"{symbol.lower()}@trade" for symbol in sharded_targets}

    async def _send_rpc(self, method: str, params: List[str]):
        """Safely sends a JSON-RPC formatted request to the WebSocket."""
        await self._connected.wait()
        if not self._ws:
            return

        try:
            msg = {
                "method": method.upper(),
                "params": params,
                "id": int(time.time() * 1000),
            }
            log.debug(f"[{self.market_def.market_id}] Sending RPC: {msg}")
            await self._ws.send(orjson.dumps(msg))
        except websockets.exceptions.ConnectionClosed:
            log.warning(
                f"[{self.market_def.market_id}] Failed to send RPC: Connection closed."
            )
        except Exception as e:
            log.error(f"[{self.market_def.market_id}] Unhandled error sending RPC: {e}")

    async def _send_subscribe(self, channels: List[str]):
        await self._send_rpc("SUBSCRIBE", channels)

    async def _send_unsubscribe(self, channels: List[str]):
        await self._send_rpc("UNSUBSCRIBE", channels)

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """Manages the raw WebSocket connection."""
        try:
            url_path = "/stream?streams=" + "/".join(self._active_channels)
            async with websockets.connect(
                self.ws_connection_url + url_path, ping_interval=180
            ) as ws:
                self._ws = ws
                self._connected.set()
                log.success(
                    f"[{self.market_def.market_id}] WebSocket connection established."
                )

                async for message in ws:
                    try:
                        data = orjson.loads(message)
                        payload = data.get("data")
                        if payload and data.get("stream"):
                            yield StreamMessage(
                                exchange=self.exchange_name,
                                channel=data["stream"],
                                timestamp=payload.get("T"),
                                data=payload,
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
        """Inner loop to consume from the generator and write to Redis."""
        async for message in self.connect():
            await self.market_data_repo.add_messages_to_stream(
                self.stream_name, [message]
            )

    async def process_messages(self):
        """The main supervisor loop that manages dynamic subscriptions and the connection."""
        self._is_running.set()
        reconnect_attempts = 0
        while self._is_running.is_set():
            try:
                # The subscription manager and message processor now run concurrently.
                # When _maintain_subscriptions changes state, the connect() method
                # will be re-established by the supervisor loop.
                sub_task = asyncio.create_task(self._maintain_subscriptions())

                while self._is_running.is_set():
                    if not self._active_channels:
                        log.info(
                            f"[{self.market_def.market_id}] No active channels. Waiting for universe update..."
                        )
                        await asyncio.sleep(5)
                        continue

                    await self._process_message_batch()

            except websockets.exceptions.ConnectionClosedError as e:
                log.warning(
                    f"[{self.market_def.market_id}] Connection closed with error: {e.code} {e.reason}"
                )
            except asyncio.CancelledError:
                log.info(f"[{self.market_def.market_id}] Supervisor tasks cancelled.")
                break
            except Exception as e:
                log.error(
                    f"[{self.market_def.market_id}] Unhandled exception in supervisor: {e}",
                    exc_info=True,
                )

            if self._is_running.is_set():
                reconnect_attempts += 1
                delay = min(2**reconnect_attempts, 60)
                log.info(
                    f"[{self.market_def.market_id}] Supervisor restarting in {delay}s (attempt {reconnect_attempts})..."
                )
                await asyncio.sleep(delay)

    async def close(self):
        log.info(f"[{self.market_def.market_id}] Closing client...")
        self._is_running.clear()
        if self._ws:
            await self._ws.close()
        log.info(f"[{self.market_def.market_id}] Client closed.")
