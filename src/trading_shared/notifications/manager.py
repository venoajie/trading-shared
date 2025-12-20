# src/shared_utils/notifications/manager.py

import asyncio
from typing import Union, Optional
from datetime import datetime
import aiohttp
from loguru import logger as log
from pydantic import SecretStr
from trading_engine_core.models import SystemAlert, TradeNotification, SignalEvent

def _get_secret_value(secret: Union[SecretStr, str, None]) -> Optional[str]:
    """Helper to extract string from SecretStr or return raw string."""
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
        """
        Initialize the notification manager.
        
        Args:
            session: Active aiohttp session for making requests.
            telegram_token: The Bot API token.
            telegram_chat_id: The target chat ID.
        """
        self._session = session
        self._telegram_chat_id = telegram_chat_id
        self._send_lock = asyncio.Lock()
        
        # Extract token value safely
        token_val = _get_secret_value(telegram_token)
        
        # --- IMPROVED INITIALIZATION LOGGING ---
        if token_val and telegram_chat_id:
            self.enabled = True
            self._base_url = f"https://api.telegram.org/bot{token_val}/sendMessage"
            
            # Mask token for security in logs
            masked_token = f"{token_val[:4]}...{token_val[-4:]}" if len(token_val) > 10 else "******"
            log.success(f"✅ Telegram Notifications ENABLED | Chat ID: {telegram_chat_id} | Bot: {masked_token}")
        else:
            self.enabled = False
            missing = []
            if not token_val: missing.append("Bot Token")
            if not telegram_chat_id: missing.append("Chat ID")
            log.warning(f"⚠️ Telegram Notifications DISABLED | Missing Credentials: {', '.join(missing)}")

    async def _send_telegram_message(self, text: str):
        if not self.enabled:
            return

        params = {"chat_id": self._telegram_chat_id, "text": text, "parse_mode": "HTML"}

        async with self._send_lock:
            # Simple retry logic (3 attempts)
            for attempt in range(1, 4):
                try:
                    async with self._session.post(self._base_url, params=params, timeout=10) as response:
                        if response.status == 200:
                            return
                        elif response.status == 429:
                            try:
                                error_data = await response.json()
                                retry_after = error_data.get("parameters", {}).get("retry_after", 5)
                            except:
                                retry_after = 5
                            log.warning(f"Telegram Rate Limit. Sleeping {retry_after}s.")
                            await asyncio.sleep(retry_after + 1)
                        else:
                            err_text = await response.text()
                            log.error(f"Telegram API Error ({response.status}): {err_text}")
                            return # Don't retry on non-transient 4xx/5xx errors other than rate limit
                except asyncio.TimeoutError:
                    log.warning(f"Telegram Timeout (Attempt {attempt}/3)")
                    await asyncio.sleep(1)
                except Exception as e:
                    log.error(f"Telegram Connection Failed: {e}")
                    await asyncio.sleep(1)

    async def send_signal_alert(self, signal: SignalEvent):
        """Standardized Signal Alert Formatter."""
        if not self.enabled: 
            return

        # Extract metadata with defaults
        meta = signal.metadata
        rvol = meta.get("rvol", 0.0)
        price_change = meta.get("price_change_24h", 0.0)
        raw_vol = meta.get("raw_volume", 0.0)
        is_test = meta.get("test_mode", False)

        # Determine Visuals
        if "SHORT" in signal.signal_type.upper():
            emoji, action, color = ("🔻", "SHORT", "🔴")
        else:
            emoji, action, color = ("🚀", "LONG", "🟢")

        title = f"{'🧪 TEST' if is_test else emoji} {action} SIGNAL {color}"

        # Construct Message
        lines = [
            f"<b>{title}</b>",
            "─────────────────────",
            f"<b>Pair:</b> <code>{signal.symbol}</code>",
            f"<b>Volume Spike:</b> {rvol:.2f}x",
            f"<b>24h Vol:</b> ${raw_vol:,.0f}",
            f"<b>24h Chg:</b> {price_change:+.2f}%",
            f"<b>Strategy:</b> {signal.strategy_name}",
            f"<b>Strength:</b> {signal.strength:.2f}",
            "─────────────────────",
            f"<i>Time: {datetime.utcnow().strftime('%H:%M:%S')} UTC</i>"
        ]
        
        await self._send_telegram_message("\n".join(lines))