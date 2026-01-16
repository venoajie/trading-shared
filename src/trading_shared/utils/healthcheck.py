# src/shared/utils/healthcheck.py

import asyncio
from datetime import datetime, timezone

from loguru import logger as log


class DeadManSwitch:
    """
    A Dead Man's Switch that pings Redis periodically to indicate the service is alive.
    If the main loop dies, the heartbeat stops, and Docker healthcheck will fail.
    """

    def __init__(
        self,
        redis_client,
        service_name: str,
        heartbeat_interval: int = 10,
        heartbeat_ttl: int = 30,
    ):
        """
        Args:
            redis_client: Redis client instance
            service_name: Name of the service (e.g., "receiver", "distributor")
            heartbeat_interval: How often to ping Redis (seconds)
            heartbeat_ttl: TTL for the heartbeat key in Redis (seconds)
        """
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
                log.error(f"Failed to send heartbeat to Redis: {e}")

            await asyncio.sleep(self.heartbeat_interval)

    async def start(self):
        """Start the heartbeat loop."""
        if self._running:
            log.warning("Dead Man's Switch already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
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

        # Clean up the heartbeat key
        try:
            await self.redis_client.delete(self.heartbeat_key)
        except Exception as e:
            log.error(f"Failed to delete heartbeat key: {e}")

        log.info(f"Dead Man's Switch stopped for {self.service_name}")

    async def check_health(self) -> bool:
        """
        Check if the service is healthy by verifying the heartbeat key exists.
        This is used by the healthcheck script.
        """
        try:
            exists = await self.redis_client.exists(self.heartbeat_key)
            return bool(exists)
        except Exception as e:
            log.error(f"Health check failed: {e}")
            return False
