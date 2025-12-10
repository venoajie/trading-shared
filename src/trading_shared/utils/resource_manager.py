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
    An async context manager that guarantees the graceful cleanup of resources.

    This manager is designed to be dependency-agnostic. It ensures that resources
    are closed upon exiting the `async with` block, regardless of whether the
    block exits cleanly or via an exception.

    Cleanup Protocol:
    1. It first checks for a standard `__aexit__` method.
    2. If not found, it falls back to checking for an awaitable `close()` method.
    3. Resources are closed in the reverse order they are provided.

    Args:
        resources: An iterable of instantiated resource objects (e.g., clients).

    Example:
        service = MyService(db_client)
        # Service is listed first, so it will be closed last on entry, first on exit.
        all_resources = [service, db_client, http_session]
        async with managed_resources(all_resources):
            await service.start()
            ...
    """
    resource_list: List[Any] = list(resources)
    try:
        yield
    finally:
        log.info(f"Closing {len(resource_list)} managed resources in reverse order...")
        # Iterate in reverse for safe, dependency-aware shutdown.
        for resource in reversed(resource_list):
            resource_name = type(resource).__name__
            try:
                # Prioritize the standard __aexit__ protocol.
                if hasattr(resource, "__aexit__") and callable(
                    getattr(resource, "__aexit__")
                ):
                    await resource.__aexit__(None, None, None)
                # Fallback to the .close() convention.
                elif hasattr(resource, "close") and callable(
                    getattr(resource, "close")
                ):
                    await resource.close()
                # If no cleanup method is found, do nothing.
                else:
                    log.trace(
                        f"Resource '{resource_name}' has no cleanup method (__aexit__ or close). Skipping."
                    )

            except Exception:
                # Log but do not re-raise. Ensures a failure in closing one
                # resource does not prevent others from being closed.
                log.exception(
                    f"A non-critical error occurred while closing resource: '{resource_name}'"
                )
