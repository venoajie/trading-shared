# src/trading_shared/notifications/manager.py

import asyncio
from typing import Optional, Self
import aiohttp
from loguru import logger as log
from trading_engine_core.models import SignalEvent


class NotificationManager:
    """Manages the formatting and dispatching of notifications."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        telegram_token: Optional[str],
        telegram_chat_id: Optional[str],
    ):
        self._session = session
        self._telegram_token = telegram_token
        self._telegram_chat_id = telegram_chat_id
        self.is_telegram_enabled = bool(telegram_token and telegram_chat_id)

    @classmethod
    async def create(
        cls,
        session: aiohttp.ClientSession,
        telegram_token: Optional[str],
        telegram_chat_id: Optional[str],
    ) -> Self:
        """
        Asynchronously creates and validates a NotificationManager instance.
        """
        manager = cls(session, telegram_token, telegram_chat_id)
        if manager.is_telegram_enabled:
            await manager._verify_token_on_startup()
        else:
            log.warning("Telegram notifications are disabled (token/chat_id not set).")
        return manager

    async def _verify_token_on_startup(self):
        """
        Performs a 'getMe' API call to verify the bot token is valid at service startup.
        """
        log.info("Verifying Telegram Bot Token with the 'getMe' API endpoint...")
        api_url = f"https://api.telegram.org/bot{self._telegram_token}/getMe"
        try:
            async with self._session.get(api_url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    bot_username = data.get("result", {}).get("username")
                    log.success(
                        f"Telegram token is valid. Connected to bot: @{bot_username}"
                    )
                    return

                if response.status == 404:
                    log.critical(
                        "Telegram token verification failed: API returned 404 Not Found."
                    )
                    raise ConnectionRefusedError(
                        "The provided Telegram Bot Token is invalid or revoked."
                    )

                if response.status == 401:
                    log.critical(
                        "Telegram token verification failed: API returned 401 Unauthorized."
                    )
                    raise ConnectionRefusedError(
                        "The provided Telegram Bot Token is unauthorized."
                    )

                error_text = await response.text()
                log.error(
                    f"Telegram token verification failed with status {response.status}: {error_text}"
                )
                raise ConnectionError("Failed to verify Telegram token.")

        except asyncio.TimeoutError:
            log.error("Request to Telegram API timed out during token verification.")
            raise
        except Exception as e:
            log.exception(
                "An unexpected error occurred during Telegram token verification."
            )
            raise e

    # --- Helper Functions for Formatting ---
    def _format_currency(self, value: float, precision: int = 2) -> str:
        if value > 1_000_000_000:
            return f"${value / 1_000_000_000:.{precision}f}B"
        if value > 1_000_000:
            return f"${value / 1_000_000:.{precision}f}M"
        if value > 1_000:
            return f"${value / 1_000:.{precision}f}K"
        return f"${value:.{precision}f}"

    def _format_percent(self, value: float) -> str:
        return f"{'+' if value >= 0 else ''}{value:.2%}"

    # --- Message Formatting Logic ---
    def _format_volume_spike_message(self, signal: SignalEvent) -> str:
        """Constructs the detailed message using quote (USD) volume keys."""
        metrics = signal.metadata.get("metrics", {})

        pair = signal.symbol
        rvol = metrics.get("rvol", 0.0)

        # Use the explicit 'quote_volume' keys for all currency formatting.
        current_vol = metrics.get("current_quote_volume", 0.0)
        avg_vol = metrics.get("avg_quote_volume_20m", 0.0)
        vol_1h = metrics.get("quote_volume_1h", 0.0)

        price_change_1h = metrics.get("price_change_1h", 0.0)
        price_start = metrics.get("price_1h_start", 0.0)
        price_end = metrics.get("price_1h_end", 0.0)
        test_mode = metrics.get("test_mode", False)

        header = (
            "🧪 TEST 📢 VOLUME SPIKE DETECTED 🔵"
            if test_mode
            else "⚡ LIVE 📢 VOLUME SPIKE DETECTED 🔴"
        )

        price_precision = 8 if price_start < 0.001 else 4

        return (
            f"{header}\n"
            f"─────────────────────\n"
            f"Pair: {pair}\n"
            # f"Strategy: {signal.strategy_name}\n"
            f"─────────────────────\n"
            f"Volume Analysis:\n"
            f"  › Spike (RVOL): {rvol:.2f}x\n"
            f"  › Current Volume: {self._format_currency(current_vol, 0)}\n"
            f"  › Average Volume: {self._format_currency(avg_vol, 0)}\n"
            f"  › 1h Total Volume: {self._format_currency(vol_1h)}\n"
            f"─────────────────────\n"
            f"Price Analysis (1h):\n"
            f"  › Change: {self._format_percent(price_change_1h)}\n"
            f"  › Start:  ${price_start:.{price_precision}f}\n"
            f"  › End:    ${price_end:.{price_precision}f}\n"
            f"─────────────────────"
        )

    # --- Main Dispatcher ---
    async def send_signal_alert(self, signal: SignalEvent):
        message = ""
        if signal.signal_type == "VOLUME_SPIKE":
            message = self._format_volume_spike_message(signal)
        else:
            message = (
                f"Received generic signal for {signal.symbol}: {signal.signal_type}"
            )

        if message:
            await self.send_telegram_message(message)

    async def send_telegram_message(self, text: str):
        if not self.is_telegram_enabled:
            return

        api_url = f"https://api.telegram.org/bot{self._telegram_token}/sendMessage"
        payload = {
            "chat_id": self._telegram_chat_id,
            "text": f"```\n{text}\n```",
            "parse_mode": "MarkdownV2",
        }
        try:
            async with self._session.post(
                api_url, json=payload, timeout=10
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    log.error(
                        f"Failed to send Telegram message. Status: {response.status}, "
                        f"Response: {error_text}"
                    )
        except asyncio.TimeoutError:
            log.error("Request to Telegram API timed out.")
        except Exception:
            log.exception(
                "An unexpected error occurred while sending Telegram message."
            )
