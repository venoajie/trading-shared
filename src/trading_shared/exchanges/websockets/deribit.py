# src/trading_shared/exchanges/websockets/deribit.py

# --- Built Ins ---
import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any

# --- Installed ---
import orjson
import websockets
from loguru import logger as log

# --- Shared Library Imports ---
from trading_engine_core.models import MarketDefinition, StreamMessage

# --- Local Application Imports ---
from ...config.models import ExchangeSettings
from ...repositories.instrument_repository import InstrumentRepository
from ...repositories.market_data_repository import MarketDataRepository
from ...repositories.system_state_repository import SystemStateRepository
from .base import AbstractWsClient


class DeribitWsClient(AbstractWsClient):
    """A dual-purpose, self-managing WebSocket client for Deribit."""

    def __init__(
        self,
        market_definition: MarketDefinition,
        market_data_repo: MarketDataRepository,
        instrument_repo: InstrumentRepository,
        settings: ExchangeSettings,
        subscription_scope: str = "public",
        system_state_repo: SystemStateRepository | None = None,
        universe_state_key: str | None = None,
    ):
        super().__init__(
            market_definition, market_data_repo, shard_id=0, total_shards=1
        )
        self.instrument_repo = instrument_repo
        self.settings = settings
        self.subscription_scope = subscription_scope.lower()
        self.system_state_repo = system_state_repo
        self.universe_state_key = universe_state_key
        self.ws_connection_url = self.market_def.ws_base_url
        self._ws: websockets.WebSocketClientProtocol | None = None

        if self.subscription_scope == "private" and (
            not settings.client_id or not settings.client_secret
        ):
            raise ValueError(
                "Deribit private scope requires client_id and client_secret."
            )

    async def _get_channels_from_universe(
        self, universe: list[dict[str, Any]]
    ) -> set[str]:
        """Consumes the clean universe object and filters for Deribit perpetuals."""
        my_targets: set[str] = set()
        for instrument_data in universe:
            if instrument_data.get("exchange_perp") == self.exchange_name:
                if perp_symbol := instrument_data.get("perp_symbol"):
                    my_targets.add(f"trades.{perp_symbol}.raw")
        return my_targets

    async def _send_rpc(self, method: str, params: dict):
        """Safely sends a JSON-RPC formatted request to the WebSocket."""
        if not self._ws:
            return
        try:
            msg = {
                "jsonrpc": "2.0",
                "id": int(time.time() * 1000),
                "method": method,
                "params": params,
            }
            await self._ws.send(orjson.dumps(msg))
        except websockets.exceptions.ConnectionClosed:
            log.warning(
                f"[{self.exchange_name}] Failed to send RPC: Connection closed."
            )

    async def _send_subscribe(self, channels: list[str]):
        """Implements the subscription abstract method."""
        if self.subscription_scope == "public":
            await self._send_rpc("public/subscribe", {"channels": channels})
        elif self.subscription_scope == "private":
            await self._send_rpc("private/subscribe", {"channels": channels})

    async def _send_unsubscribe(self, channels: list[str]):
        """Implements the unsubscription abstract method."""
        if self.subscription_scope == "public":
            await self._send_rpc("public/unsubscribe", {"channels": channels})
        elif self.subscription_scope == "private":
            await self._send_rpc("private/unsubscribe", {"channels": channels})

    async def _handle_subscriptions(self):
        """
        [MODIFIED] This method now uses the newly implemented contract methods for clarity,
        though it could also call _send_rpc directly. This is a stylistic choice for consistency.
        """
        if self.subscription_scope == "private":
            auth_params = {
                "grant_type": "client_credentials",
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret.get_secret_value(),
            }
            await self._send_rpc("public/auth", auth_params)
            private_channels = ["user.changes.any.any.raw"]
            await self._send_subscribe(private_channels)
            log.info(
                f"[{self.exchange_name}] Authenticated and subscribed to private channels."
            )

        elif self.subscription_scope == "public" and self._active_channels:
            await self._send_subscribe(list(self._active_channels))
            log.info(
                f"[{self.exchange_name}] Subscribed to {len(self._active_channels)} public channels."
            )

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """Manages a single, finite connection and yields messages."""
        try:
            async with websockets.connect(
                self.ws_connection_url, ping_interval=30
            ) as ws:
                self._ws = ws
                log.success(
                    f"[{self.exchange_name}][{self.subscription_scope}] WebSocket connection established."
                )
                await self._handle_subscriptions()

                async for message in ws:
                    try:
                        data = orjson.loads(message)
                        params = data.get("params")
                        if (
                            isinstance(params, dict)
                            and "channel" in params
                            and "data" in params
                        ):
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
                    except (orjson.JSONDecodeError, KeyError, TypeError):
                        log.warning(f"[{self.exchange_name}] Could not parse message.")
        finally:
            self._ws = None
            log.warning(
                f"[{self.exchange_name}][{self.subscription_scope}] WebSocket connection closed."
            )

    async def _process_message_batch(self):
        """Inner loop to consume messages and write them to the Redis stream."""
        try:
            async for message in self.connect():
                await self.market_data_repo.add_messages_to_stream(
                    self.stream_name, [message]
                )
        except asyncio.CancelledError:
            pass  # Normal shutdown

    async def process_messages(self):
        """[REFACTORED] The main supervisor loop that manages the connection lifecycle."""
        self._is_running.set()
        reconnect_attempts = 0
        subscription_task = None

        if self.subscription_scope == "public":
            subscription_task = asyncio.create_task(self._maintain_subscriptions())
        else:
            # For private scope, we don't need dynamic subs, just set the event once to connect.
            self._reconnect_event.set()

        while self._is_running.is_set():
            try:
                await self._reconnect_event.wait()
                self._reconnect_event.clear()

                batch_task = asyncio.create_task(self._process_message_batch())
                await batch_task  # Awaits until the connection is lost.

                reconnect_attempts = 0
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception(f"[{self.exchange_name}] Supervisor error.")

            if self._is_running.is_set():
                reconnect_attempts += 1
                delay = min(2**reconnect_attempts, 60)
                log.info(f"[{self.exchange_name}] Reconnecting in {delay}s...")
                await asyncio.sleep(delay)
                self._reconnect_event.set()

        if subscription_task:
            subscription_task.cancel()
        log.info(
            f"[{self.exchange_name}][{self.subscription_scope}] Supervisor loop has shut down."
        )

    async def close(self):
        """Initiates a graceful shutdown."""
        log.warning(
            f"[{self.exchange_name}][{self.subscription_scope}] Closing client..."
        )
        self._is_running.clear()
        self._reconnect_event.set()
        if self._ws:
            await self._ws.close()
