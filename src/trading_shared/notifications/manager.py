# src\shared_utils\notifications\manager.py

# --- Built Ins  ---
import asyncio
from typing import Union
from datetime import datetime

# --- Installed  ---
import aiohttp
from loguru import logger as log
from pydantic import SecretStr

# --- Shared Library Imports  ---
from trading_engine_core.models import SystemAlert, TradeNotification


def _get_secret_value(secret: Union[SecretStr, str]) -> str:
    """Safely gets the string value from a SecretStr or a plain str."""
    if isinstance(secret, SecretStr):
        return secret.get_secret_value()
    return secret


class NotificationManager:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        telegram_token: str = Union[str, SecretStr],
        telegram_chat_id: str = None,
    ):
        """
        Initialize with injected credentials.
        """
        self._session = session
        self.enabled = False
        self._base_url = None
        self._telegram_chat_id = telegram_chat_id
        self._send_lock = asyncio.Lock()

        if telegram_token and telegram_chat_id:
            self.enabled = True
            self._base_url = f"https://api.telegram.org/bot{_get_secret_value(telegram_token)}/sendMessage"
            log.info("Telegram notifications are enabled.")
        else:
            log.warning(
                "Telegram notifications are disabled (credentials not provided)."
            )
            self.enabled = False

    async def _send_telegram_message(self, text: str):
        if not self.enabled:
            return
        params = {"chat_id": self._telegram_chat_id, "text": text, "parse_mode": "HTML"}

        # Use lock to prevent rate limit flooding
        async with self._send_lock:
            for attempt in range(3):
                try:
                    async with self._session.post(
                        self._base_url, params=params
                    ) as response:
                        if response.status == 200:
                            return
                        elif response.status == 429:
                            error_data = await response.json()
                            retry_after = error_data.get("parameters", {}).get(
                                "retry_after", 5
                            )
                            log.warning(
                                f"Telegram rate limit. Sleeping {retry_after}s."
                            )
                            await asyncio.sleep(retry_after + 1)
                        else:
                            log.error(f"Telegram fail: {response.status}")
                            return
                except Exception as e:
                    log.error(f"Telegram exception: {e}")
                    await asyncio.sleep(1)

    async def send_trade_notification(self, notification: TradeNotification):
        if not self.enabled:
            return
        text = (
            f"<b>Trade Executed</b>\n\n<b>{notification.direction.upper()}</b> {notification.amount} of "
            f"<code>{notification.instrument_name}</code> at <code>{notification.price}</code>"
        )
        await self._send_telegram_message(text)

    async def send_system_alert(self, alert: SystemAlert):
        if not self.enabled:
            return
        text = (
            f"<b>🚨 SYSTEM ALERT 🚨</b>\n\n<b>Severity:</b> {alert.severity}\n<b>Component:</b> {alert.component}\n"
            f"<b>Event:</b> {alert.event}\n\n<b>Details:</b>\n<pre>{alert.details}</pre>"
        )
        await self._send_telegram_message(text)

    async def send_message(self, text: str):
        """Send a generic HTML-formatted message to Telegram."""
        await self._send_telegram_message(text)
        
        # Add to trading_shared/notifications/manager.py
    async def send_signal_alert(self, signal_event):
        """Send a strategy signal to Telegram."""
        if not self.enabled:
            return
        
        # Format the signal as HTML
        meta = signal_event.metadata
        
        if signal_event.signal_type == "ENTRY_SHORT":
            emoji = "🔻"
            action = "SHORT"
            color = "🔴"
        else:
            emoji = "🚀"
            action = "LONG"
            color = "🟢"
        
        # Check if this is a test signal
        is_test = meta.get('test_signal', False)
        
        if is_test:
            title = f"🧪 TEST SIGNAL - {action} {emoji}"
        else:
            title = f"{emoji} {action} SIGNAL {color}"
        
        # Format numbers nicely
        volume_ratio = meta.get('volume_ratio', 0)
        current_volume = meta.get('current_volume_usd', 0)
        avg_volume = meta.get('avg_volume_usd', 0)
        price_change = meta.get('price_change_1m', 0) * 100  # Convert to %
        
        text = (
            f"{title}\n"
            f"─────────────────────\n"
            f"<b>Asset:</b> {meta.get('base_asset', 'N/A')}\n"
            f"<b>Pair:</b> {signal_event.symbol}\n"
            f"<b>Volume Spike:</b> {volume_ratio:.1f}x\n"
            f"<b>Current Volume:</b> ${current_volume:,.0f}\n"
            f"<b>Avg Volume:</b> ${avg_volume:,.0f}\n"
            f"<b>1m Change:</b> {price_change:+.2f}%\n"
            f"<b>Strategy:</b> {signal_event.strategy_name}\n"
            f"<b>Strength:</b> {signal_event.strength:.1f}\n"
        )
        
        if is_test:
            text += "<i>This is a TEST signal - not for trading</i>\n"
        
        text += "─────────────────────\n"
        text += f"<i>Timestamp: {datetime.utcnow().strftime('%H:%M:%S')} UTC</i>"
        
        await self._send_telegram_message(text)