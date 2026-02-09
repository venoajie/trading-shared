# src/trading_shared/trading_shared/exchanges/websockets/binance_movers.py

import asyncio
import orjson
import websockets
from loguru import logger as log

from ...config.models import ExchangeSettings
from ...core.models import MarketDefinition
from ...repositories.system_state_repository import SystemStateRepository
from .base import AbstractWsClient


class BinanceMoversWsClient(AbstractWsClient):
    """
    Dedicated client for 'abnormaltradingnotices'.
    Refactored to use the direct single-stream endpoint for robustness.
    """

    def __init__(
        self,
        market_definition: MarketDefinition,
        system_state_repo: SystemStateRepository,
        settings: ExchangeSettings,
    ):
        super().__init__(market_definition, market_data_repo=None)
        self.system_state_repo = system_state_repo
        # [MODIFIED] We now construct the full, direct URL here
        base_url = settings.ws_url.replace("wss://stream.", "wss://bstream.")
        self.ws_connection_url = f"{base_url}/ws/abnormaltradingnotices"

        self._ws: websockets.WebSocketClientProtocol | None = None

        self.override_key = "system:map:strategist:overrides"
        self.override_ttl_seconds = 900  # 15 minutes

    async def connect(self):
        """Connects to the dedicated single-stream endpoint."""
        try:
            async with websockets.connect(self.ws_connection_url, ping_interval=180) as ws:
                self._ws = ws

                log.success(f"[{self.market_def.market_id}] Connected to Abnormal Trading Notices.")
                async for message in ws:
                    yield message
        finally:
            self._ws = None

    async def _normalize_symbol(self, raw_symbol: str) -> str | None:
        """Heuristic to convert 'BTCUSDT' to 'BTC-USDT'."""
        known_quotes = {"USDT", "USDC", "FDUSD", "BTC", "ETH", "BNB", "TRY"}
        for quote in known_quotes:
            if raw_symbol.endswith(quote):
                return f"{raw_symbol[: -len(quote)]}-{quote}"
        return None

    async def process_messages(self):
        self._is_running.set()
        while self._is_running.is_set():
            try:
                async for message in self.connect():
                    try:
                        # For this stream, the raw message is the payload
                        payload = orjson.loads(message)

                        raw_sym = payload.get("symbol")
                        canonical_sym = await self._normalize_symbol(raw_sym)

                        if canonical_sym:
                            pipe = self.system_state_repo.redis.pipeline()
                            pipe.hset(self.override_key, canonical_sym, orjson.dumps(payload))

                            ttl_key = f"system:state:mover_ttl:{canonical_sym}"
                            pipe.set(ttl_key, 1, ex=self.override_ttl_seconds)
                            await pipe.execute()

                            log.info(f"💡 MOVER PROMOTED: {canonical_sym} | Event: {payload.get('eventType')}")

                    except (orjson.JSONDecodeError, KeyError):
                        pass
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
