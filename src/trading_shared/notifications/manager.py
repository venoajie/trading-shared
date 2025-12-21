# src/shared_utils/notifications/manager.py

import asyncio
from typing import Union, Optional
from datetime import datetime
import aiohttp
from loguru import logger as log
from pydantic import SecretStr
from trading_engine_core.models import SystemAlert, TradeNotification, SignalEvent

def _get_secret_value(secret: Union[SecretStr, str, None]) -> Optional[str]:
    if secret is None: 
        return None
    return secret.get_secret_value() if isinstance(secret, SecretStr) else secret

class NotificationManager:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        telegram_token: Union[str, SecretStr],
        telegram_chat_id: str,
    ):
        self._session = session
        self._telegram_chat_id = telegram_chat_id
        self._send_lock = asyncio.Lock()
        
        token_val = _get_secret_value(telegram_token)
        
        if token_val and telegram_chat_id:
            self.enabled = True
            self._base_url = f"https://api.telegram.org/bot{token_val}/sendMessage"
            masked_token = f"{token_val[:4]}...{token_val[-4:]}" if len(token_val) > 10 else "******"
            log.success(f"✅ Telegram Notifications ENABLED | Chat ID: {telegram_chat_id}")
        else:
            self.enabled = False
            log.warning("⚠️ Telegram Notifications DISABLED | Missing Credentials")

    async def _send_telegram_message(self, text: str):
        if not self.enabled: return
        params = {"chat_id": self._telegram_chat_id, "text": text, "parse_mode": "HTML"}
        async with self._send_lock:
            for attempt in range(1, 4):
                try:
                    async with self._session.post(self._base_url, params=params, timeout=10) as resp:
                        if resp.status == 200: return
                        if resp.status == 429:
                            retry = (await resp.json()).get("parameters", {}).get("retry_after", 5)
                            await asyncio.sleep(retry + 1)
                        else:
                            log.error(f"Telegram API Error {resp.status}: {await resp.text()}")
                            return
                except Exception as e:
                    log.error(f"Telegram Connection Error: {e}")
                    await asyncio.sleep(1)

    # --- Helper Functions for Formatting ---
    def _format_currency(self, value: float, precision: int = 2) -> str:
        if value > 1_000_000_000:
            return f"${value/1_000_000_000:.{precision}f}B"
        if value > 1_000_000:
            return f"${value/1_000_000:.{precision}f}M"
        if value > 1_000:
            return f"${value/1_000:.{precision}f}K"
        return f"${value:.{precision}f}"

    def _format_percent(self, value: float) -> str:
        return f"{'+' if value >= 0 else ''}{value:.2%}"

    # --- Message Formatting Logic ---
    def _format_volume_spike_message(self, signal: SignalEvent) -> str:
        """Constructs the detailed message for a VOLUME_SPIKE signal."""
        metrics = signal.metadata.get("metrics", {})
        
        # Extract and default all required values
        pair = signal.symbol
        rvol = metrics.get("rvol", 0.0)
        current_vol = metrics.get("current_volume", 0.0)
        avg_vol = metrics.get("average_volume_20m", 0.0)
        vol_1h = metrics.get("volume_1h", 0.0)
        price_change_1h = metrics.get("price_change_1h", 0.0)
        price_start = metrics.get("price_1h_start", 0.0)
        price_end = metrics.get("price_1h_end", 0.0)
        test_mode = metrics.get("test_mode", False)

        header = "🧪 TEST 📢 VOLUME SPIKE DETECTED 🔵" if test_mode else "⚡ LIVE 📢 VOLUME SPIKE DETECTED 🔴"
        
        # Determine price precision based on magnitude
        price_precision = 8 if price_start < 0.001 else 4

        return (
            f"{header}\n"
            f"─────────────────────\n"
            f"Pair: {pair}\n"
            f"Strategy: {signal.strategy_name}\n"
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

    async def send_signal_alert(self, signal: SignalEvent):

        if signal.signal_type == "VOLUME_SPIKE":
            message = self._format_volume_spike_message(signal)
        else:
            # Fallback for other signal types
            message = f"Received generic signal for {signal.symbol}: {signal.signal_type}"
            
        if message:
            await self.send_telegram_message(message)

    async def send_telegram_message(self, text: str):
        if not self.is_telegram_enabled:
            log.warning("Telegram notifications are disabled (token/chat_id not set).")
            return

        api_url = f"https://api.telegram.org/bot{self._telegram_token}/sendMessage"
        payload = {
            "chat_id": self._telegram_chat_id,
            "text": f"```\n{text}\n```",  # Use markdown for a monospaced block
            "parse_mode": "MarkdownV2",
        }
        try:
            async with self._session.post(api_url, json=payload, timeout=10) as response:
                if response.status != 200:
                    error_text = await response.text()
                    log.error(
                        f"Failed to send Telegram message. Status: {response.status}, "
                        f"Response: {error_text}"
                    )
        except asyncio.TimeoutError:
            log.error("Request to Telegram API timed out.")
        except Exception:
            log.exception("An unexpected error occurred while sending Telegram message.")