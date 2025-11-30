## src/services/receiver/exchange_clients/binance_ws_client.py

import asyncio
import orjson
import websockets
from typing import AsyncGenerator, Set
from loguru import logger as log

from .base import AbstractWsClient
from ...clients.postgres_client import PostgresClient
from ...clients.redis_client import CustomRedisClient
from ...config.models import ExchangeSettings, StreamMessage
from trading_engine_core.models import MarketDefinition  # A contract for market info


class BinanceWsClient(AbstractWsClient):
    """
    A dynamic, controllable WebSocket client for Binance that manages subscriptions on-the-fly
    via a Redis control channel. This implementation uses the native `websockets` library
    and does not depend on `ccxt`.
    """

    def __init__(
        self,
        market_definition: MarketDefinition,
        postgres_client: PostgresClient,
        redis_client: CustomRedisClient,
        settings: ExchangeSettings,
    ):
        super().__init__(market_definition, redis_client, postgres_client)
        self.ws_connection_url = self.market_def.ws_base_url
        self._subscriptions: Set[str] = set()
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._is_running = asyncio.Event()
        self._control_channel = f"control:{self.market_def.market_id}:subscriptions"
        self.settings = settings

        if not self._control_channel:
            raise ValueError("Binance subscription control channel not configured.")

    async def _send_subscription_request(
        self,
        method: str,
        params: list,
    ):
        if not self._ws or not self._ws.open:
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
        pool = await self.redis_client.get_pool()
        pubsub = pool.pubsub()
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
                    f"{item['symbol'].lower()}@aggTrade" for item in symbols_to_modify
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
                        await self._send_subscription_request("UNSUBSCRIBE", old_subs)
                        self._subscriptions.difference_update(old_subs)

            except Exception as e:
                log.error(f"Error in control channel listener: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _message_loop(self) -> AsyncGenerator[StreamMessage, None]:
        """The main loop for connecting to the WebSocket and processing messages."""

        stream_names = "/".join(self._subscriptions)
        if not stream_names:
            log.warning(
                f"[{self.exchange_name}] No initial streams to subscribe to for market '{self.market_def.market_id}'. Client will be idle until commanded."
            )
            await self._is_running.wait()
            return

        # The base URL from config is `.../stream`->We only append `?streams=...`
        url = f"{self.ws_connection_url}?streams={stream_names}"

        while self._is_running.is_set():
            try:
                log.info(f"[{self.exchange_name}] Connecting to: {url}")
                async with websockets.connect(
                    url, ping_interval=20, ping_timeout=60
                ) as ws:
                    self._ws = ws
                    log.success(
                        f"[{self.exchange_name}] WebSocket connection established for market '{self.market_def.market_id}'."
                    )

                    # Get Redis pool once per successful connection
                    pool = await self.redis_client.get_pool()

                    async for message in ws:
                        try:
                            payload = orjson.loads(message)
                            if "data" not in payload or "stream" not in payload:
                                continue

                            trade_data = payload["data"]
                            stream_name = payload["stream"]
                            symbol = stream_name.split("@")[0].upper()
                            market_type = self.market_def.market_type

                            # Update the Redis Hash for low-latency lookups (Snapshot)
                            redis_key = f"ticker:{symbol}"
                            
                            # Use the pre-fetched pool object
                            await pool.hset(
                                redis_key, 
                                "payload", 
                                orjson.dumps(trade_data)
                            )
                                                        
                            yield StreamMessage(
                                exchange=self.exchange_name,
                                channel=f"aggTrade.{symbol}.{market_type}",
                                timestamp=trade_data.get("T"),
                                data={
                                    "symbol": symbol,
                                    "market_type": market_type,
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
                            
            except (websockets.ConnectionClosed, ConnectionError) as e:
                log.warning(
                    f"[{self.exchange_name}] Connection closed for market '{self.market_def.market_id}': {e}. Reconnecting in 5s..."
                )
                self._ws = None
                await asyncio.sleep(5)
            except Exception as e:
                log.error(
                    f"[{self.exchange_name}] Unexpected error in connect loop for market '{self.market_def.market_id}': {e}. Reconnecting in 15s.",
                    exc_info=True,
                )
                self._ws = None
                await asyncio.sleep(15)

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        """Orchestrates the client's concurrent tasks."""
        self._is_running.set()

        initial_symbols = [
            item
            for item in (settings.public_symbols or [])
            if item.get("market_type") == self.market_def.market_type
        ]

        for item in initial_symbols:
            symbol = item.get("symbol")
            if symbol:
                stream_name = f"{symbol.lower()}@aggTrade"
                self._subscriptions.add(stream_name)

        log.info(
            f"[{self.exchange_name}][{self.market_def.market_id}] Initial subscriptions set: {self._subscriptions}"
        )

        listener_task = asyncio.create_task(self._control_channel_listener())

        try:
            async for message in self._message_loop():
                yield message
        finally:
            self._is_running.clear()
            listener_task.cancel()
            await asyncio.gather(listener_task, return_exceptions=True)
            log.info(
                f"[{self.exchange_name}][{self.market_def.market_id}] Client tasks shut down."
            )
