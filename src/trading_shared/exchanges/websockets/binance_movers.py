# src/trading_shared/trading_shared/exchanges/websockets/binance_movers.py

import asyncio
import orjson
import websockets
from loguru import logger as log

from ...config.models import ExchangeSettings
from ...core.models import MarketDefinition
from ...repositories.system_state_repository import SystemStateRepository
from .base import AbstractWsClient
from ...core.enums import MoverPeriod, MoverNoticeType


class BinanceMoversWsClient(AbstractWsClient):
    """
    Dedicated client for Binance's 'abnormaltradingnotices' stream.
    Its sole responsibility is to ingest mover events and promote them
    to the strategist's "Spotlight" override map.
    """

    def __init__(
        self,
        market_definition: MarketDefinition,
        system_state_repo: SystemStateRepository,
        settings: ExchangeSettings,
    ):
        super().__init__(market_definition, market_data_repo=None)
        self.system_state_repo = system_state_repo
        self.ws_connection_url = settings.ws_url.replace("wss://stream.", "wss://bstream.")
        self._ws: websockets.WebSocketClientProtocol | None = None

        self.override_key = "system:map:strategist:overrides"
        # The TTL for how long a promoted symbol stays in the spotlight.
        self.override_ttl_seconds = 900  # 15 minutes

    async def connect(self):
        """Connects to the singleton stream and yields raw messages."""
        full_url = self.ws_connection_url + "/stream"
        try:
            async with websockets.connect(full_url, ping_interval=180) as ws:
                self._ws = ws
                await ws.send(orjson.dumps({"method": "SUBSCRIBE", "params": ["abnormaltradingnotices"], "id": 1}))
                log.success(f"[{self.market_def.market_id}] Connected to Abnormal Trading Notices.")
                async for message in ws:
                    yield message
        finally:
            self._ws = None
            log.warning(f"[{self.market_def.market_id}] WebSocket connection closed.")

    async def _normalize_symbol(self, raw_symbol: str) -> str | None:
        """Simple heuristic to convert a raw symbol like 'BTCUSDT' to 'BTC-USDT'."""
        known_quotes = {"USDT", "USDC", "FDUSD", "BTC", "ETH", "BNB", "TRY"}
        for quote in known_quotes:
            if raw_symbol.endswith(quote):
                base = raw_symbol[: -len(quote)]
                return f"{base}-{quote}"
        return None

    async def process_messages(self):
        self._is_running.set()
        while self._is_running.is_set():
            try:
                async for message in self.connect():
                    try:
                        data = orjson.loads(message)
                        payload = data.get("data")

                        if not payload or data.get("stream") != "abnormaltradingnotices":
                            continue

                        # --- NO FILTERING APPLIED ---
                        # The receiver faithfully forwards all events. The strategist
                        # will be responsible for interpreting the period and notice type.

                        raw_sym = payload.get("symbol")
                        canonical_sym = await self._normalize_symbol(raw_sym)

                        if canonical_sym:
                            # Promote to the Redis Hash with a 15-minute TTL on the field
                            # NOTE: HSET with EX is not standard. We use a pipeline for an atomic operation.
                            pipe = self.system_state_repo.redis.pipeline()
                            pipe.hset(self.override_key, canonical_sym, orjson.dumps(payload))
                            # This promotes the *symbol* with a TTL, not the whole map.
                            # We create a separate key for the TTL to manage expiration.
                            ttl_key = f"system:ttl:{self.override_key}:{canonical_sym}"
                            pipe.set(ttl_key, 1, ex=self.override_ttl_seconds)
                            await pipe.execute()

                            log.info(f"💡 MOVER PROMOTED: {canonical_sym} | Event: {payload.get('eventType')}")

                    except (orjson.JSONDecodeError, KeyError):
                        pass  # Ignore malformed messages
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Movers client error. Reconnecting in 5s...")
                await asyncio.sleep(5)

    async def close(self):
        self._is_running.clear()
        if self._ws:
            await self._ws.close()

    # Unused abstract methods stubs
    async def _get_channels_from_universe(self, universe: list) -> set:
        return set()
