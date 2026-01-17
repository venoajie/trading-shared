# src/trading_shared/trading_shared/utils/healthcheck.py

import asyncio
from datetime import datetime, timezone

from loguru import logger as log

# [FIX] Import the fail-fast utility
from .fail_fast import create_fail_fast_task


class DeadManSwitch:
    """
    A fail-fast Dead Man's Switch that pings Redis periodically.
    If the heartbeat task dies for any reason, the entire process will exit.
    """

    def __init__(
        self,
        redis_client,
        service_name: str,
        heartbeat_interval: int = 10,
        heartbeat_ttl: int = 30,
    ):
        self.redis_client = redis_client
        self.service_name = service_name
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_ttl = heartbeat_ttl
        self.heartbeat_key = f"healthcheck:{service_name}:heartbeat"
        self._running = False
        self._task: asyncio.Task | None = None

    async def _heartbeat_loop(self):
        """Continuously ping Redis to indicate the service is alive."""
        while self._running:
            try:
                timestamp = datetime.now(timezone.utc).isoformat()
                await self.redis_client.setex(self.heartbeat_key, self.heartbeat_ttl, timestamp)
                log.trace(f"Heartbeat sent: {self.heartbeat_key}")
            except Exception as e:
                # [FIX] If an error occurs, log it and raise to trigger fail-fast
                log.error(f"Heartbeat loop failed: {e}")
                raise  # This will be caught by the fail-fast wrapper

            await asyncio.sleep(self.heartbeat_interval)

    async def start(self):
        """Start the fail-fast heartbeat loop."""
        if self._running:
            log.warning("Dead Man's Switch already running")
            return

        self._running = True
        # [FIX] Use create_fail_fast_task to ensure any crash is fatal
        self._task = create_fail_fast_task(self._heartbeat_loop(), name=f"{self.service_name}_heartbeat")
        log.info(f"Dead Man's Switch started for {self.service_name} (interval={self.heartbeat_interval}s, ttl={self.heartbeat_ttl}s)")

    async def stop(self):
        """Stop the heartbeat loop."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        try:
            await self.redis_client.delete(self.heartbeat_key)
        except Exception as e:
            log.error(f"Failed to delete heartbeat key: {e}")

        log.info(f"Dead Man's Switch stopped for {self.service_name}")

    async def check_health(self) -> bool:
        """Check if the service is healthy by verifying the heartbeat key exists."""
        try:
            exists = await self.redis_client.exists(self.heartbeat_key)
            return bool(exists)
        except Exception as e:
            log.error(f"Health check failed: {e}")
            return False
