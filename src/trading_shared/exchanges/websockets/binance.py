# src/trading_shared/trading_shared/exchanges/websockets/binance.py

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import orjson
import websockets
from loguru import logger as log
from trading_engine_core.models import MarketDefinition, StreamMessage

from ...config.models import ExchangeSettings
from ...repositories.instrument_repository import InstrumentRepository
from ...repositories.market_data_repository import MarketDataRepository
from ...repositories.system_state_repository import SystemStateRepository
from .base import AbstractWsClient


class BinanceWsClient(AbstractWsClient):
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
        super().__init__(market_definition, market_data_repo, shard_id=shard_id, total_shards=total_shards)
        self.system_state_repo = system_state_repo
        self.universe_state_key = universe_state_key
        self.ws_connection_url = self.market_def.ws_base_url
        self._ws: websockets.WebSocketClientProtocol | None = None
        self.shard_num_for_log = self.shard_id + 1

    async def _get_channels_from_universe(self, universe: list[dict[str, Any]]) -> set[str]:
        # 1. Identify valid targets (Spot instruments)
        my_targets = {
            entry.get("symbol") or entry.get("instrument_name")
            for entry in universe
            if (entry.get("exchange", "").lower() == self.exchange_name.lower()) and ("spot" in entry.get("market_type", "").lower())
        }

        # 2. Apply Sharding
        sharded_targets = {sym for i, sym in enumerate(sorted(my_targets)) if i % self.total_shards == self.shard_id}

        # 3. [FIX] Determine Subscription Type (Trade vs Ticker)
        # We check the 'market_type' of the Client Configuration, not the Instrument.
        if "ticker" in self.market_def.market_type.value:
            return {f"{sym.replace('-', '').lower()}@ticker" for sym in sharded_targets}

        # Default to Trade streams
        return {f"{sym.replace('-', '').lower()}@trade" for sym in sharded_targets}

    async def connect(self) -> AsyncGenerator[StreamMessage, None]:
        if not self._active_channels:
            log.warning(f"[{self.market_def.market_id}] No channels to subscribe to.")
            return
        url_path = "/stream?streams=" + "/".join(sorted(self._active_channels))
        full_url = self.ws_connection_url + url_path
        try:
            async with websockets.connect(full_url, ping_interval=180) as ws:
                self._ws = ws
                log.success(f"[{self.market_def.market_id}_{self.shard_num_for_log}] Connected with {len(self._active_channels)} channels.")
                async for message in ws:
                    try:
                        data = orjson.loads(message)
                        payload = data.get("data")
                        stream = data.get("stream")

                        # [FIX] Support both 'trade' and 'ticker' streams
                        if payload and stream:
                            is_trade = "trade" in stream
                            is_ticker = "ticker" in stream

                            if is_trade or is_ticker:
                                # Tickers use 'E' (Event Time), Trades use 'T' (Trade Time)
                                ts = payload.get("T") or payload.get("E")

                                # Log occasionally to prove liveness (First shard only)
                                if self.shard_id == 0 and is_ticker and "BTC" in payload.get("s", ""):
                                    log.trace(f"Tick: {payload.get('s')} Price: {payload.get('c')}")

                                yield StreamMessage(
                                    exchange=self.exchange_name,
                                    channel=stream,
                                    timestamp=ts,
                                    data=payload,
                                )
                    except (orjson.JSONDecodeError, KeyError, TypeError):
                        log.warning("Failed to decode or parse Binance message.")
        except websockets.exceptions.InvalidStatus as e:
            log.critical(f"[{self.market_def.market_id}_{self.shard_num_for_log}] 404 REJECTION. Invalid symbols in shard.")
            raise e
        finally:
            self._ws = None
            log.warning(f"[{self.market_def.market_id}] WebSocket connection closed.")

    async def _process_message_batch(self):
        try:
            messages_to_write = []
            async for message in self.connect():
                messages_to_write.append(message)
                if len(messages_to_write) >= 100:
                    await self.market_data_repo.add_messages_to_stream(self.stream_name, messages_to_write)
                    messages_to_write = []

            if messages_to_write:
                await self.market_data_repo.add_messages_to_stream(self.stream_name, messages_to_write)

        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception(f"[{self.market_def.market_id}] Unhandled error in message batch processor.")

    async def process_messages(self):
        self._is_running.set()
        subscription_task = asyncio.create_task(self._maintain_subscriptions())
        while self._is_running.is_set():
            try:
                await self._reconnect_event.wait()
                self._reconnect_event.clear()
                batch_task = asyncio.create_task(self._process_message_batch())
                await batch_task
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception(f"[{self.market_def.market_id}] Supervisor error.")
                if self._is_running.is_set():
                    await asyncio.sleep(5)
                    self._reconnect_event.set()
        subscription_task.cancel()
        log.info(f"[{self.market_def.market_id}] Supervisor loop has shut down.")

    async def close(self):
        log.warning(f"[{self.market_def.market_id}] Closing client...")
        self._is_running.clear()
        self._reconnect_event.set()
        if self._ws:
            await self._ws.close()
