#!/usr/bin/env python3
# src/shared/utils/healthcheck_script.py

"""
Docker healthcheck script that verifies the service heartbeat in Redis.
Exit code 0 = healthy, Exit code 1 = unhealthy
"""

import asyncio
import os
import sys
from pathlib import Path


async def check_health(service_name: str) -> bool:
    """Check if the service heartbeat exists in Redis."""
    try:
        # Import here to avoid issues if dependencies aren't available
        from trading_shared.clients.redis_client import CustomRedisClient
        from trading_shared.models.redis_settings import RedisSettings

        # Read Redis password from secret file
        redis_password_file = os.getenv("REDIS_PASSWORD_FILE")
        redis_password = None
        if redis_password_file and os.path.exists(redis_password_file):
            redis_password = Path(redis_password_file).read_text().strip()

        # Create Redis client
        redis_url = os.getenv("REDIS_URL", "redis://redis-stack:6379")
        settings = RedisSettings(url=redis_url, password=redis_password)
        redis_client = CustomRedisClient(settings=settings)

        # Connect and check heartbeat
        await redis_client.connect()
        heartbeat_key = f"healthcheck:{service_name}:heartbeat"
        exists = await redis_client.exists(heartbeat_key)
        await redis_client.close()

        return bool(exists)
    except Exception as e:
        print(f"Healthcheck failed: {e}", file=sys.stderr)
        return False


def main():
    """Main entry point for Docker healthcheck."""
    service_name = os.getenv("SERVICE_NAME")
    if not service_name:
        print("ERROR: SERVICE_NAME environment variable not set", file=sys.stderr)
        sys.exit(1)

    try:
        is_healthy = asyncio.run(check_health(service_name))
        if is_healthy:
            print(f"✓ {service_name} is healthy")
            sys.exit(0)
        else:
            print(f"✗ {service_name} is unhealthy (no heartbeat)", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"✗ Healthcheck error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
