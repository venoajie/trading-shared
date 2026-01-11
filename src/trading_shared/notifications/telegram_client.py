
# src/trading_shared/notifications/telegram_client.py

import asyncio
import time
import re
from typing import Self

import aiohttp
from loguru import logger as log


class TelegramDeliveryError(Exception):
    """Custom exception for failures after all retries."""
    pass


class TelegramClient:
    """
    A robust transport-layer client for the Telegram Bot API.
    Handles rate limits (429) compliantly by respecting 'Retry-After'.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str | None,
        chat_id: str | None,
    ):
        self._session = session
        self._token = token
        self._chat_id = chat_id
        self._last_send_time = 0.0
        self._min_interval_s = 1.0
        self.is_enabled = bool(token and chat_id)

        if not self.is_enabled:
            log.warning("TelegramClient is disabled: token or chat_id is missing.")

    @classmethod
    async def create(
        cls,
        session: aiohttp.ClientSession,
        token: str | None,
        chat_id: str | None,
    ) -> Self:
        client = cls(session, token, chat_id)
        if client.is_enabled:
            await client._verify_token()
        return client

    async def _verify_token(self):
        log.info("Verifying Telegram Bot Token...")
        api_url = f"https://api.telegram.org/bot{self._token}/getMe"
        try:
            async with self._session.get(api_url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    username = data.get("result", {}).get("username")
                    log.success(f"Telegram token valid. Connected to bot: @{username}")
                    return

                if response.status in:
                    raise ConnectionRefusedError("Telegram Bot Token is invalid or revoked.")

                response.raise_for_status()
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            log.critical(f"TELEGRAM EGRESS BLOCKED: {e}. Starting in DEGRADED mode.")
        except Exception as e:
            log.error(f"Unexpected error during verification: {e}")
            raise

    async def _enforce_client_rate_limit(self):
        """Prevents rapid-fire requests from leaving the client."""
        now = time.monotonic()
        elapsed = now - self._last_send_time
        if elapsed < self._min_interval_s:
            await asyncio.sleep(self._min_interval_s - elapsed)
        self._last_send_time = time.monotonic()

    def _escape_markdown_v2(self, text: str) -> str:
        """Escapes text for Telegram's MarkdownV2 parser."""
        # Chars to escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
        escape_chars = r"_*[]()~`>#+-=|{}.!"
        return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)

    async def send_message(self, text: str, use_code_block: bool = True):
        if not self.is_enabled:
            return

        await self._enforce_client_rate_limit()

        api_url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        
        # [REFACTOR] Correctly format payload for MarkdownV2.
        # The message content is escaped, and then wrapped in a code block.
        # This prevents API errors and ensures clean, monospaced rendering.
        final_text = text
        if use_code_block:
            escaped_text = self._escape_markdown_v2(text)
            final_text = f"```\n{escaped_text}\n```"
        else:
            final_text = self._escape_markdown_v2(text)

        payload = {
            "chat_id": self._chat_id,
            "text": final_text,
            "parse_mode": "MarkdownV2",
        }

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                async with self._session.post(api_url, json=payload, timeout=10) as response:
                    if response.status == 429:
                        retry_after = 5
                        try:
                            data = await response.json()
                            retry_after = data.get("parameters", {}).get("retry_after", retry_after)
                        except Exception:
                            val = response.headers.get("Retry-After")
                            if val:
                                retry_after = int(val)
                        log.warning(f"Telegram 429: Rate limit hit. Sleeping {retry_after}s.")
                        await asyncio.sleep(retry_after + 0.5)
                        continue

                    if response.status == 200:
                        log.debug("Telegram message sent successfully.")
                        return
                    
                    # Log detailed error for bad requests
                    if response.status == 400:
                        error_details = await response.text()
                        log.error(f"Telegram 400 Bad Request: {error_details}. Payload: {payload}")

                    response.raise_for_status()

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                log.warning(f"Network error sending to Telegram: {e} (Attempt {attempt}/{max_retries}).")
                if attempt < max_retries:
                    await asyncio.sleep(2**attempt)
                else:
                    log.error("Max retries reached for Telegram. Message dropped.")
                    raise TelegramDeliveryError(f"Failed to send after {max_retries} attempts.") from e