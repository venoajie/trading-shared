"""
Centralized State Management Service

Responsibility: Manages all system state according to the hierarchical protocol.
Enforces: system:state:global, system:state:<exchange>, system:regime:<exchange>:<instrument>
Deprecates: system:state:simple, system:state (without suffix)
"""

import json
from datetime import datetime, timezone
from typing import Dict, Optional, List
from enum import Enum

from loguru import logger as log
from pydantic import BaseModel, Field

from trading_shared.clients.redis_client import CustomRedisClient


class SystemState(str, Enum):
    """Controlled vocabulary for system state values."""

    BOOTSTRAPPING = "BOOTSTRAPPING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    LOCKED = "LOCKED"
    AUDITING = "AUDITING"
    MAINTENANCE = "MAINTENANCE"


class StateRecord(BaseModel):
    """Structured state record with metadata."""

    status: SystemState
    reason: str = ""
    timestamp: float = Field(
        default_factory=lambda: datetime.now(timezone.utc).timestamp()
    )
    metadata: Dict = Field(default_factory=dict)


class SystemStateManager:
    """
    Centralized state manager implementing the hierarchical protocol:
    1. system:state:global (highest priority)
    2. system:state:<exchange> (exchange-specific)
    3. system:regime:<exchange>:<instrument> (market regime)

    All state operations MUST go through this service.
    """

    def __init__(self, redis_client: CustomRedisClient):
        self.redis = redis_client
        self._cache = {}
        self._cache_ttl = 5  # seconds

    async def set_global_state(
        self, state: SystemState, reason: str = "", metadata: Optional[Dict] = None
    ) -> None:
        """
        Sets the global system state. LOCKED global state overrides all other states.
        """
        record = StateRecord(status=state, reason=reason, metadata=metadata or {})

        await self.redis.hset(
            "system:state:global",
            mapping={
                "status": record.status.value,
                "reason": record.reason,
                "timestamp": str(record.timestamp),
                "metadata": json.dumps(record.metadata),
            },
        )

        # Expire after 1 hour to prevent stale state
        await self.redis.expire("system:state:global", 3600)

        log.info(f"Global state set to {state.value}: {reason}")

        # Clear any deprecated keys
        await self._cleanup_deprecated_keys()

    async def set_exchange_state(
        self,
        exchange: str,
        state: SystemState,
        reason: str = "",
        metadata: Optional[Dict] = None,
    ) -> None:
        """
        Sets exchange-specific state. Exchange state is subordinate to global state.
        """
        # Check global state first - if LOCKED, log warning but proceed
        global_state = await self.get_global_state()
        if global_state and global_state.status == SystemState.LOCKED:
            log.warning(
                f"Setting exchange state while global is LOCKED: {exchange}={state.value}"
            )

        record = StateRecord(status=state, reason=reason, metadata=metadata or {})
        key = f"system:state:{exchange.lower()}"

        await self.redis.hset(
            key,
            mapping={
                "status": record.status.value,
                "reason": record.reason,
                "timestamp": str(record.timestamp),
                "metadata": json.dumps(record.metadata),
            },
        )

        # Expire after 30 minutes
        await self.redis.expire(key, 1800)

        log.info(f"Exchange {exchange} state set to {state.value}: {reason}")

    async def get_global_state(self) -> Optional[StateRecord]:
        """Gets the current global system state."""
        cache_key = "global_state"
        if cache_key in self._cache:
            cached_time, record = self._cache[cache_key]
            if (datetime.now(timezone.utc).timestamp() - cached_time) < self._cache_ttl:
                return record

        data = await self.redis.hgetall("system:state:global")
        if not data:
            return None

        try:
            record = StateRecord(
                status=SystemState(data.get(b"status", b"").decode()),
                reason=data.get(b"reason", b"").decode(),
                timestamp=float(data.get(b"timestamp", b"0").decode()),
                metadata=json.loads(data.get(b"metadata", b"{}").decode()),
            )
            self._cache[cache_key] = (datetime.now(timezone.utc).timestamp(), record)
            return record
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            log.error(f"Failed to parse global state: {e}")
            return None

    async def get_exchange_state(self, exchange: str) -> Optional[StateRecord]:
        """Gets the current state for a specific exchange."""
        cache_key = f"exchange_state_{exchange}"
        if cache_key in self._cache:
            cached_time, record = self._cache[cache_key]
            if (datetime.now(timezone.utc).timestamp() - cached_time) < self._cache_ttl:
                return record

        key = f"system:state:{exchange.lower()}"
        data = await self.redis.hgetall(key)
        if not data:
            return None

        try:
            record = StateRecord(
                status=SystemState(data.get(b"status", b"").decode()),
                reason=data.get(b"reason", b"").decode(),
                timestamp=float(data.get(b"timestamp", b"0").decode()),
                metadata=json.loads(data.get(b"metadata", b"{}").decode()),
            )
            self._cache[cache_key] = (datetime.now(timezone.utc).timestamp(), record)
            return record
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            log.error(f"Failed to parse exchange state for {exchange}: {e}")
            return None

    async def can_trade_on_exchange(self, exchange: str) -> bool:
        """
        Determines if trading is allowed on an exchange.
        Implements the hierarchical check: global → exchange
        """
        global_state = await self.get_global_state()
        if global_state and global_state.status in [
            SystemState.LOCKED,
            SystemState.MAINTENANCE,
        ]:
            log.warning(f"Trading blocked by global state: {global_state.status.value}")
            return False

        exchange_state = await self.get_exchange_state(exchange)
        if exchange_state and exchange_state.status in [
            SystemState.HEALTHY,
            SystemState.DEGRADED,
        ]:
            return True

        log.warning(
            f"Trading blocked on {exchange}: state={exchange_state.status if exchange_state else 'UNKNOWN'}"
        )
        return False

    async def get_all_states(self) -> Dict:
        """Returns all current states for debugging/monitoring."""
        global_state = await self.get_global_state()
        exchanges = ["deribit", "binance"]  # Should be dynamic
        exchange_states = {}

        for exchange in exchanges:
            state = await self.get_exchange_state(exchange)
            if state:
                exchange_states[exchange] = state

        return {
            "global": global_state.dict() if global_state else None,
            "exchanges": {k: v.dict() for k, v in exchange_states.items()},
        }

    async def _cleanup_deprecated_keys(self):
        """Removes deprecated state keys to prevent confusion."""
        deprecated_keys = [
            "system:state:simple",
            "system:state",  # Without suffix
        ]

        for key in deprecated_keys:
            try:
                await self.redis.delete(key)
                log.debug(f"Cleaned up deprecated key: {key}")
            except Exception as e:
                log.warning(f"Failed to clean up deprecated key {key}: {e}")


# Convenience function for dependency injection
def get_state_manager(redis_client: CustomRedisClient) -> SystemStateManager:
    """Factory function for dependency injection."""
    return SystemStateManager(redis_client)
