
#### **[CRITICAL]**

*   **File & Line Number(s):** `src/trading_shared/clients/postgres_client.py`, Line 32
*   **Observation:** The `__aenter__` method calls `await self.get_pool()`, but no method named `get_pool` exists in the class.
*   **Impact Analysis:** This constitutes a fatal bug. Any attempt to use the client as an asynchronous context manager (`async with PostgresClient(...)`) will fail immediately with an `AttributeError`. This violates the class's API contract and renders a primary lifecycle management pattern for run-once tasks completely non-functional.
*   **Actionable Recommendation:** Correct the method call to `self.start_pool()`, which correctly implements the get-or-create logic for the connection pool.

    ```python
    # src\trading_shared\clients\postgres_client.py

    # ... (omitted for brevity)

    async def __aenter__(self):
        """Allows the client to be used as an async context manager."""
        # CORRECTED: Call the existing start_pool method.
        await self.start_pool()  # Ensure connection is established on entry
        return self

    # ... (omitted for brevity)
    ```

#### **[WARNING]**

*   **File & Line Number(s):** `src/trading_shared/clients/postgres_client.py`, Lines 191-192
*   **Observation:** The `bulk_upsert_instruments` method modifies the `instruments` list, a mutable argument, in-place by adding an `'exchange'` key to each dictionary.
*   **Impact Analysis:** This creates an implicit side effect that is not declared in the method's signature or documentation. Callers providing a list that is used elsewhere in their application will find it unexpectedly mutated. This can lead to subtle, hard-to-debug state management bugs in consuming services.
*   **Actionable Recommendation:** Create a deep copy of the instrument data before modification to ensure the function is pure with respect to its inputs.

    ```python
    # src\trading_shared\clients\postgres_client.py

    # ... (omitted for brevity)
    async def bulk_upsert_instruments(
        self,
        instruments: List[Dict[str, Any]],
        exchange_name: str,
    ):
        """
        Performs a bulk upsert of instrument data by passing an array of JSONB
        objects to the legacy database function.
        """
        if not instruments:
            return

        # CORRECTED: Create a new list to avoid side effects.
        instruments_with_exchange = [
            {**inst, "exchange": exchange_name} for inst in instruments
        ]

        async def command(conn: asyncpg.Connection):
            # The 'instruments' list of dicts is automatically encoded to JSONB[].
            await conn.execute(
                "SELECT bulk_upsert_instruments($1::jsonb[])",
                # Use the new list.
                instruments_with_exchange,
            )

        await self._execute_resiliently(command, "bulk_upsert_instruments")
        log.info(
            f"Successfully bulk-upserted {len(instruments)} instruments for '{exchange_name}'."
        )
    # ... (omitted for brevity)
    ```

#### **[RECOMMENDATION]**

*   **File & Line Number(s):** `src/trading_shared/clients/postgres_client.py`, Line 69
*   **Observation:** The method `start_pool` also serves to return an existing pool, functioning as a "get-or-create" method. The name `start_pool` implies it only creates a new resource, which is not its complete behavior.
*   **Impact Analysis:** This minor naming ambiguity can reduce code clarity. Developers might mistakenly believe the method is more heavyweight than it is, potentially leading to suboptimal usage patterns where they avoid calling it to check for a valid pool.
*   **Actionable Recommendation:** Rename the method to more accurately reflect its idempotent nature, for example, `ensure_pool_is_ready`.

    ```python
    # src\trading_shared\clients\postgres_client.py

    # ... (omitted for brevity)
    # RENAMED for clarity
    async def ensure_pool_is_ready(self) -> asyncpg.Pool:
        async with self._lock:
            if self._pool is not None and not self._pool._closed:
                return self._pool
    # ... (omitted for brevity)

    # And update callers, e.g., in _execute_resiliently:
    # pool = await self.ensure_pool_is_ready()
    ```

---

### **Audit Report: `redis_client.py`**

---

#### **[CRITICAL]**

*   **File & Line Number(s):** `src/trading_shared/clients/redis_client.py`, Line 45
*   **Observation:** The `__aenter__` method calls `await self.get_pool()`, but no public method named `get_pool` exists. The intended method is the private `_get_pool`.
*   **Impact Analysis:** This is a fatal bug identical to the one in `PostgresClient`. It makes the async context manager protocol unusable, raising an `AttributeError` and preventing clean resource management for run-once tasks. This directly contradicts the architectural requirements for supporting different service lifecycles.
*   **Actionable Recommendation:** Correct the method call to `self._get_pool()` to align with the class's internal implementation.

    ```python
    # src\trading_shared\clients\redis_client.py

    # ... (omitted for brevity)
    async def __aenter__(self):
        """Allows the client to be used as an async context manager."""
        # CORRECTED: Call the existing private _get_pool method.
        await self._get_pool()  # Ensure connection is established on entry
        return self
    # ... (omitted for brevity)
    ```

#### **[WARNING]**

*   **File & Line Number(s):** `src/trading_shared/clients/redis_client.py`, Lines 69-73
*   **Observation:** The `_get_pool` method performs a proactive `ping()` health check every time it is called, even if a valid pool object already exists.
*   **Impact Analysis:** This adds one full network round-trip time (RTT) of latency to *every single Redis operation* initiated through `_execute_resiliently`. The `_execute_resiliently` wrapper already provides robust, reactive error handling for connection failures. This proactive check is redundant and introduces a significant, unnecessary performance penalty in high-throughput services.
*   **Actionable Recommendation:** Remove the proactive `ping()`. Rely on the reactive retry mechanism in `_execute_resiliently` to handle connection failures, which is more efficient. The connection logic should only attempt to reconnect if the pool does not exist or a command has already failed.

    ```python
    # src\trading_shared\clients\redis_client.py

    # ... (omitted for brevity)
    async def _get_pool(self) -> aioredis.Redis:
        async with self._lock:
            # SIMPLIFIED: If pool exists, assume it's good. Let the resilient
            # executor handle failures reactively.
            if self._pool:
                return self._pool

            if self._circuit_open:
    # ... (omitted for brevity)
    ```

#### **[WARNING]**

*   **File & Line Number(s):** `src/trading_shared/clients/redis_client.py`, Line 101
*   **Observation:** The connection creation loop inside `_get_pool` uses a broad `except Exception as e:`.
*   **Impact Analysis:** This pattern is dangerous because it catches and logs *all* exceptions, including non-recoverable ones like configuration errors (`ValueError` from a malformed URL) or programming errors. By treating all exceptions as transient connection failures, it masks the root cause of persistent startup problems, delaying diagnosis and resolution.
*   **Actionable Recommendation:** Catch only specific, expected exceptions related to network and connection establishment. Let other exceptions propagate to fail fast and provide a clear error signal.

    ```python
    # src\trading_shared\clients\redis_client.py

    # ... (omitted for brevity)
                    )
                    await asyncio.wait_for(self._pool.ping(), timeout=3)
                    self._reconnect_attempts = 0
                    log.info("Redis connection established")
                    return self._pool
                # CORRECTED: Catch specific, transient errors.
                except (
                    redis_exceptions.ConnectionError,
                    redis_exceptions.TimeoutError,
                    TimeoutError,
                    socket.gaierror,
                ) as e:
                    log.warning(f"Connection failed on attempt {attempt + 1}: {e}")
                    await self._safe_close_pool()
                    if attempt < 4:
    # ... (omitted for brevity)
    ```

#### **[RECOMMENDATION]**

*   **File & Line Number(s):** `src/trading_shared/clients/redis_client.py`, Line 39
*   **Observation:** The `_write_sem` semaphore, which limits concurrent bulk write operations, is hardcoded to a value of `4`.
*   **Impact Analysis:** While using a semaphore for throttling is a good resilience pattern, a hardcoded value is inflexible. This value may be suboptimal for different deployment environments (e.g., local development vs. high-core production servers) or workloads, potentially creating an artificial bottleneck or failing to provide sufficient backpressure.
*   **Actionable Recommendation:** Make the semaphore limit configurable via the `RedisSettings` model, with a sensible default.

    ```python
    # In config/models.py (or equivalent)
    class RedisSettings(BaseModel):
        # ... other settings
        write_concurrency_limit: int = 4

    # src\trading_shared\clients\redis_client.py
    class CustomRedisClient:
        def __init__(self, settings: RedisSettings):
            self._settings = settings
            # ...
            # CORRECTED: Use configurable value
            self._write_sem = asyncio.Semaphore(self._settings.write_concurrency_limit)
            self._lock = asyncio.Lock()
    ```

#### **[RECOMMENDATION]**

*   **File & Line Number(s):** `postgres_client.py` Line 69, `redis_client.py` Line 41
*   **Observation:** The public methods for explicitly initializing the clients are named differently: `start_pool` in `PostgresClient` and `connect` in `CustomRedisClient`.
*   **Impact Analysis:** This API inconsistency across two clients within the same shared library increases the cognitive load on developers and violates the principle of least surprise. It can lead to errors when developers switch between using the two clients.
*   **Actionable Recommendation:** Standardize the lifecycle management API. Rename `PostgresClient.start_pool` to `connect` to match `CustomRedisClient` and establish a consistent convention.

    ```python
    # src\trading_shared\clients\postgres_client.py
    class PostgresClient:
        # ...
        # RENAMED for consistency
        async def connect(self) -> asyncpg.Pool:
            # ... existing start_pool logic
    ```