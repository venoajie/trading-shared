# src/trading_shared/notifications/telegram_client.py

import asyncio
from typing import Self

import aiohttp
from loguru import logger as log
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class TelegramDeliveryError(Exception):
    """Custom exception for failures after all retries."""

    pass


class TelegramClient:
    """
    A pure, resilient transport-layer client for the Telegram Bot API.
    It is responsible for sending pre-formatted messages with retry logic.
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
        """Asynchronously creates and validates a TelegramClient instance."""
        client = cls(session, token, chat_id)
        if client.is_enabled:
            await client._verify_token()
        return client

    async def _verify_token(self):
        """
        Performs a 'getMe' API call to verify the bot token.
        Refactored to allow degraded startup on network timeout.
        """
        log.info("Verifying Telegram Bot Token...")
        api_url = f"https://api.telegram.org/bot{self._token}/getMe"
        try:
            async with self._session.get(api_url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    username = data.get("result", {}).get("username")
                    log.success(f"Telegram token valid. Connected to bot: @{username}")
                    return

                # Non-retryable auth errors still cause a crash as they indicate invalid secrets
                if response.status in [401, 404]:
                    raise ConnectionRefusedError("Telegram Bot Token is invalid or revoked. Check secrets.")
                response.raise_for_status()

        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            # Degraded mode allowance
            log.critical(
                f"TELEGRAM EGRESS BLOCKED: Timeout/Connection error during verification. "
                f"The service will start in DEGRADED mode. Notifications will fail until egress is restored. "
                f"Error: {e}"
            )
            # We do not raise the error here; we allow the service to continue.
            return
        except Exception as e:
            log.error(f"Unexpected error during Telegram token verification: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )
    async def send_message(self, text: str, parse_mode: str = "MarkdownV2"):
        """
        Sends a message to the configured Telegram chat with retry logic.
        Raises TelegramDeliveryError if all retries fail.
        """
        if not self.is_enabled:
            log.trace("Skipping Telegram send because client is disabled.")
            return

        api_url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        # Telegram MarkdownV2 requires escaping of special characters.
        # This is a transport-level concern.
        escaped_text = text.replace("-", "\\-").replace(".", "\\.").replace("!", "\\!").replace("(", "\\(").replace(")", "\\)")

        payload = {
            "chat_id": self._chat_id,
            "text": f"```\n{escaped_text}\n```",
            "parse_mode": parse_mode,
        }
        try:
            async with self._session.post(api_url, json=payload, timeout=10) as response:
                response.raise_for_status()  # Raises for 4xx/5xx responses
                log.debug("Successfully sent message to Telegram.")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning(f"Telegram send failed, will retry. Error: {e}")
            raise  # Re-raise to trigger tenacity's retry mechanism
        except Exception as e:
            log.error(f"Unhandled exception during Telegram send: {e}")
            # Wrap in our custom exception to signal terminal failure
            raise TelegramDeliveryError(f"Failed to send message after retries: {e}") from e
