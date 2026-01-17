# src/trading_shared/trading_shared/utils/healthcheck_script.py

import asyncio
import os
import sys
from pathlib import Path

# Add the project root to sys.path to ensure imports work
sys.path.append(os.getcwd())

async def check_health(service_name: str) -> bool:
    """Check if the service heartbeat exists in Redis."""
    try:
        # Import here to avoid issues if dependencies aren't available
        from trading_shared.clients.redis_client import CustomRedisClient
        from trading_shared.config.models import RedisSettings # Fixed import path

        # Read Redis password from secret file
        redis_password_file = os.getenv("REDIS_PASSWORD_FILE")
        redis_password = None
        if redis_password_file and os.path.exists(redis_password_file):
            redis_password = Path(redis_password_file).read_text().strip()
        
        # Create Redis client
        redis_url = os.getenv("REDIS_URL", "redis://redis-stack:6379")
        
        # [DEBUG] Print config to stderr (visible in docker inspect)
        print(f"DEBUG: Checking health for '{service_name}' at '{redis_url}'", file=sys.stderr)

        settings = RedisSettings(url=redis_url, password=redis_password)
        redis_client = CustomRedisClient(settings=settings)

        # Connect and check heartbeat
        await redis_client.connect()
        heartbeat_key = f"healthcheck:{service_name}:heartbeat"
        
        # [DEBUG] Check Key
        exists = await redis_client.exists(heartbeat_key)
        ttl = await redis_client.ttl(heartbeat_key)
        
        await redis_client.close()

        if exists:
            print(f"DEBUG: Key '{heartbeat_key}' FOUND. TTL: {ttl}", file=sys.stderr)
            return True
        else:
            print(f"DEBUG: Key '{heartbeat_key}' NOT FOUND.", file=sys.stderr)
            return False

    except ImportError as e:
        print(f"ERROR: Import failed: {e}. Python Path: {sys.path}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR: Healthcheck exception: {e}", file=sys.stderr)
        return False


def main():
    """Main entry point for Docker healthcheck."""
    service_name = os.getenv("SERVICE_NAME")
    
    # [FIX] Fallback logic if env var is missing in the healthcheck shell context
    if not service_name:
        # Try to infer from hostname or arguments if needed, but strictly warn for now
        print("ERROR: SERVICE_NAME environment variable not set", file=sys.stderr)
        sys.exit(1)

    try:
        is_healthy = asyncio.run(check_health(service_name))
        if is_healthy:
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()