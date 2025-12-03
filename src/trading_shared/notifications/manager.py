# src\shared_utils\notifications\manager.py

# --- Built Ins  ---
import asyncio

# --- Installed  ---
import aiohttp
from loguru import logger as log

# --- Shared Library Imports  ---
from trading_engine_core.models import SystemAlert, TradeNotification


class NotificationManager:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        telegram_token: str = None,
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
            self._base_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
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
