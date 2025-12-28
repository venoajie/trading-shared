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
from ...clients.redis_client import CustomRedisClient
from ...config.models import ExchangeSettings
from ...repositories.instrument_repository import InstrumentRepository
from ...repositories.market_data_repository import MarketDataRepository
from ...repositories.system_state_repository import SystemStateRepository
from .base import AbstractWsClient

# --- Shared Library Imports ---
from trading_engine_core.models import MarketDefinition, StreamMessage
from ...repositories.instrument_repository import InstrumentRepository


class DeribitWsClient(AbstractWsClient):
    """A dual-purpose, self-managing WebSocket client for Deribit."""

    def __init__(
        self,
        market_definition: MarketDefinition,
        market_data_repo: MarketDataRepository,
        instrument_repo: InstrumentRepository,
        settings: ExchangeSettings,
        stream_name: str,
        subscription_scope: str = "public",
        redis_client: Optional[CustomRedisClient] = None,
        system_state_repo: Optional[SystemStateRepository] = None,
        universe_state_key: Optional[str] = None,
    ):
        super().__init__(
            market_definition, market_data_repo, stream_name, shard_id=0, total_shards=1
        )
        self.instrument_repo = instrument_repo
        self.settings = settings
        self.subscription_scope = subscription_scope.lower()
        self.redis_client = redis_client
        self.system_state_repo = system_state_repo
        self.universe_state_key = universe_state_key

        self.ws_connection_url = self.market_def.ws_base_url
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = asyncio.Event()

        if self.subscription_scope == "private" and (
            not settings.client_id or not settings.client_secret
        ):
            raise ValueError(
                "Deribit private scope requires client_id and client_secret."
            )
        if self.subscription_scope == "public" and (
            not system_state_repo or not universe_state_key
        ):
            raise ValueError(
                "Deribit public scope requires system_state_repo and universe_state_key."
            )

    async def _get_channels_from_universe(self, universe: List[str]) -> Set[str]:
        """
        Maps canonical universe symbols to Deribit's public trade channel names
        by dynamically looking up the correct instrument name from the database.
        """
        my_targets = set()
        # Create a list of tasks to run the DB lookups concurrently for performance.
        tasks = [
            self.instrument_repo.find_instrument_by_name_and_kind(
                exchange=self.exchange_name,
                canonical_name=symbol,
                instrument_kind="perpetual",
            )
            for symbol in universe
        ]

        results = await asyncio.gather(*tasks)

        for i, instrument in enumerate(results):
            if instrument:
                my_targets.add(f"trades.{instrument['instrument_name']}.raw")
            else:
                symbol = universe[i]
                log.warning(
                    f"[{self.exchange_name}] Could not find a perpetual instrument for '{symbol}' in the database. Cannot subscribe."
                )
        return my_targets

    async def _send_rpc(self, method: str, params: dict):
        """Safely sends a JSON-RPC formatted request to the WebSocket."""
        await self._connected.wait()
        if not self._ws:
            return

        try:
            msg = {
                "jsonrpc": "2.0",
                "id": int(time.time() * 1000),
                "method": method,
                "params": params,
            }
            log.debug(f"[{self.exchange_name}] Sending RPC: {msg}")
            await self._ws.send(orjson.dumps(msg))
        except websockets.exceptions.ConnectionClosed:
            log.warning(
                f"[{self.exchange_name}] Failed to send RPC: Connection is closed."
            )
        except Exception as e:
            log.error(f"[{self.exchange_name}] Unhandled error sending RPC: {e}")

    async def _send_subscribe(self, channels: List[str]):
        await self._send_rpc("public/subscribe", {"channels": channels})

    async def _send_unsubscribe(self, channels: List[str]):
        await self._send_rpc("public/unsubscribe", {"channels": channels})

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """Manages the raw WebSocket connection, including private authentication."""
        try:
            async with websockets.connect(
                self.ws_connection_url, ping_interval=30
            ) as ws:
                self._ws = ws
                self._connected.set()
                log.success(
                    f"[{self.exchange_name}][{self.subscription_scope}] WebSocket connection established."
                )

                if self.subscription_scope == "private":
                    await self._authenticate_and_subscribe()
                elif self._active_channels:  # Public scope reconnect
                    await self._send_subscribe(list(self._active_channels))

                async for message in ws:
                    try:
                        data = orjson.loads(message)
                        params = data.get("params")
                        if (
                            isinstance(params, dict)
                            and "channel" in params
                            and "data" in params
                        ):
                            # Private and public data can be a list or a single object.
                            trade_list = (
                                params["data"]
                                if isinstance(params["data"], list)
                                else [params["data"]]
                            )
                            for trade in trade_list:
                                yield StreamMessage(
                                    exchange=self.exchange_name,
                                    channel=params["channel"],
                                    timestamp=trade.get("timestamp"),
                                    data=trade,
                                )
                    except (orjson.JSONDecodeError, KeyError, TypeError) as e:
                        log.error(
                            f"[{self.exchange_name}] Error processing message: {e}"
                        )
        finally:
            self._ws = None
            self._connected.clear()
            log.warning(
                f"[{self.exchange_name}][{self.subscription_scope}] WebSocket connection closed."
            )

    async def _authenticate_and_subscribe(self):
        """Handles the authentication flow for private connections."""

        auth_params = {
            "grant_type": "client_credentials",
            "client_id": self.settings.client_id,  # Passed as a plain string
            "client_secret": self.settings.client_secret.get_secret_value(),
        }
        await self._send_rpc("public/auth", auth_params)
        log.info(f"[{self.exchange_name}] Authentication request sent.")

        # Static private channel subscriptions
        private_channels = ["user.changes.any.any.raw"]
        sub_params = {"channels": private_channels}
        await self._send_rpc("private/subscribe", sub_params)
        log.info(
            f"[{self.exchange_name}] Sent private subscription request for: {private_channels}"
        )

    async def _process_message_batch(self):
        """Inner loop that consumes from the `connect` generator and processes data."""
        batch = deque()
        async for message in self.connect():
            # For private scope, data is the raw event. For public, it's the trade.
            # The stream repository can handle this polymorphism.
            await self.market_data_repo.add_messages_to_stream(
                self.stream_name, [message]
            )

    async def process_messages(self):
        """The main supervisor loop, which behaves differently based on scope."""
        self._is_running.set()
        reconnect_attempts = 0
        while self._is_running.is_set():
            try:
                tasks = []
                # Public scope uses dynamic, polling subscriptions.
                if self.subscription_scope == "public":
                    tasks.append(asyncio.create_task(self._maintain_subscriptions()))

                # Both scopes need the message processor.
                tasks.append(asyncio.create_task(self._process_message_batch()))

                await asyncio.gather(*tasks)

            except websockets.exceptions.ConnectionClosedError as e:
                log.warning(
                    f"[{self.exchange_name}] Connection closed: {e.code} {e.reason}"
                )
            except asyncio.CancelledError:
                log.info(f"[{self.exchange_name}] Supervisor tasks cancelled.")
                break
            except Exception as e:
                log.error(
                    f"[{self.exchange_name}] Unhandled exception in supervisor: {e}",
                    exc_info=True,
                )

            if self._is_running.is_set():
                reconnect_attempts += 1
                delay = min(2**reconnect_attempts, 60)
                log.info(
                    f"[{self.exchange_name}] Supervisor restarting in {delay}s (attempt {reconnect_attempts})..."
                )
                await asyncio.sleep(delay)

    async def close(self):
        """Initiates a graceful shutdown of the client."""
        log.info(f"[{self.exchange_name}][{self.subscription_scope}] Closing client...")
        self._is_running.clear()
        if self._ws:
            await self._ws.close()
        log.info(f"[{self.exchange_name}][{self.subscription_scope}] Client closed.")
