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

    async def send_signal_alert(self, signal: SignalEvent):
        if not self.enabled: return
        
        meta = signal.metadata
        context = meta.get("context", {})
        trigger = meta.get("trigger", {})

        # --- REFACTORED HEADER LOGIC (NEUTRAL) ---
        is_test = context.get("test_mode", False) or meta.get("test_mode", False)
        
        # Default neutral styling
        emoji = "📢"
        color = "🔵"
        title_text = "VOLUME SPIKE DETECTED"

        # Construct Title
        title = f"{'🧪 TEST ' if is_test else ''}{emoji} {title_text} {color}"

        # --- DATA EXTRACTION (1H FOCUS) ---
        # Prioritize "trigger" dict (V2 protocol), fallback to root meta (V1)
        rvol = trigger.get("rvol", meta.get("rvol", 0.0))
        
        # New 1h Metrics
        vol_1h = context.get("volume_1h", meta.get("volume_1h", 0.0))
        chg_1h = trigger.get("price_change_1h", meta.get("price_change_1h", 0.0))
        
        lines = [
            f"<b>{title}</b>",
            "─────────────────────",
            f"<b>Pair:</b> <code>{signal.symbol}</code>",
            f"<b>Spike (RVOL):</b> {rvol:.2f}x",
            f"<b>1h Volume:</b> ${vol_1h:,.0f}",
            f"<b>1h Change:</b> {chg_1h:+.2f}%",
            f"<b>Strategy:</b> {signal.strategy_name}",
            "─────────────────────",
            f"<i>Time: {datetime.utcnow().strftime('%H:%M:%S')} UTC</i>"
        ]
        await self._send_telegram_message("\n".join(lines))