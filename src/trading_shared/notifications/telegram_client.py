# src/trading_shared/notifications/telegram_client.py

import asyncio
import time
from typing import Self, Optional

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
        # Client-side safety buffer (prevents bursting)
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

                if response.status in [401, 404]:
                    raise ConnectionRefusedError("Telegram Bot Token is invalid or revoked.")

                response.raise_for_status()

        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            log.critical(f"TELEGRAM EGRESS BLOCKED: {e}. Starting in DEGRADED mode.")
            return
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

    async def send_message(self, text: str, parse_mode: str = "MarkdownV2"):
        if not self.is_enabled:
            return

        await self._enforce_client_rate_limit()

        api_url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        # Basic escaping for MarkdownV2 to prevent 400 Bad Request
        escaped_text = text.replace("-", "\\-").replace(".", "\\.").replace("!", "\\!")
        escaped_text = escaped_text.replace("(", "\\(").replace(")", "\\)").replace("=", "\\=")

        payload = {
            "chat_id": self._chat_id,
            "text": f"```\n{escaped_text}\n```",
            "parse_mode": parse_mode,
        }

        # --- Manual Retry Loop for 429 Handling ---
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                async with self._session.post(api_url, json=payload, timeout=10) as response:
                    # CASE: Rate Limit Hit
                    if response.status == 429:
                        retry_after = 5  # Default fallback
                        try:
                            # Telegram sends retry_after in the JSON parameters
                            data = await response.json()
                            retry_after = data.get("parameters", {}).get("retry_after", retry_after)
                        except Exception:
                            # Fallback to header if JSON parsing fails
                            val = response.headers.get("Retry-After")
                            if val:
                                retry_after = int(val)

                        log.warning(f"Telegram 429: Too Many Requests. Sleeping {retry_after}s (Attempt {attempt})")
                        await asyncio.sleep(retry_after + 0.5)  # Add small buffer
                        continue  # Retry the loop

                    # CASE: Success
                    if response.status == 200:
                        log.debug("Telegram message sent successfully.")
                        return

                    # CASE: Other Error
                    response.raise_for_status()

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                log.warning(f"Network error sending Telegram message: {e}.")
                if attempt < max_retries:
                    sleep_time = 2**attempt
                    log.info(f"Retrying in {sleep_time}s...")
                    await asyncio.sleep(sleep_time)
                else:
                    log.error("Max retries reached. Message dropped.")
                    raise TelegramDeliveryError(f"Failed to send after {max_retries} attempts.") from e
