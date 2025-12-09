# src/trading_shared/utils/resource_manager.py

# --- Built Ins ---
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator, Iterable
from typing import Any, List

# --- Installed ---
from loguru import logger as log


@asynccontextmanager
async def managed_resources(resources: Iterable[Any]) -> AsyncGenerator[None, None]:
    """
    An async context manager that guarantees the graceful cleanup of any
    resource with an awaitable 'close' method.

    This manager is designed to be dependency-agnostic. It does not instantiate
    resources; it only ensures the `close()` method of pre-instantiated
    objects is called upon exiting the `async with` block, regardless of
    whether the block exits cleanly or via an exception.

    Args:
        resources: An iterable of instantiated resource objects (e.g., clients).
                   Each object is checked for an awaitable `close()` method,
                   which will be called during cleanup.

    Example:
        clients = [PostgresClient(), CustomRedisClient(), WsClient()]
        async with managed_resources(clients):
            # ... service logic using the clients ...
            pass
        # At this point, .close() has been awaited on all clients.
    """
    # Convert to a list immediately to avoid consuming the iterable.
    resource_list: List[Any] = list(resources)
    try:
        # The 'yield' passes control back to the 'async with' block.
        # The resources are already instantiated and available in the calling scope.
        yield
    finally:
        log.info(f"Closing {len(resource_list)} managed resources...")
        # --- RELEASE (Guaranteed Execution) ---
        for resource in resource_list:
            # Check if the resource has a callable 'close' method to avoid errors.
            if hasattr(resource, "close") and callable(getattr(resource, "close")):
                resource_name = type(resource).__name__
                try:
                    # Await the close method to perform cleanup.
                    await resource.close()
                except Exception:
                    # Log but do not re-raise. This ensures that a failure in closing
                    # one resource does not prevent subsequent resources from being closed.
                    log.exception(
                        f"A non-critical error occurred while closing resource: '{resource_name}'"
                    )