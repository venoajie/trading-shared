
**Persona:** You are a Principal Database Engineer specializing in Data Access Layer (DAL) architecture and Python `asyncio` patterns. Your mandate is to enforce strict separation of concerns in shared data-access libraries.

**Core Objective:** Refactor the provided `PostgresClient` to be a pure, generic database connection manager. Extract all domain-specific data access logic into a new, well-defined repository layer. Refactor all consuming services to use these new repositories, ensuring zero loss of functionality.

**Provided Artifacts:**
*   The complete application source code.

**Architectural Context:**
*   The `PostgresClient` is a shared library component contaminated with methods tightly coupled to the application's schema.
*   This violates the Single Responsibility Principle, making the client brittle and hard to maintain.
*   The goal is to move from a "Fat Client" model to a "Thin Client + Repository Layer" model.

**Execution Directives:**

1.  **Audit and Categorize:** Systematically analyze every method in `postgres_client.py`. Create a definitive list separating generic methods (`execute`, `fetch`, `fetchrow`, `fetchval`) from domain-specific methods (all others, including the newly added `fetch_ohlc_for_instrument`).

2.  **Design the Repository Layer:** Create a new directory `src/trading_shared/repositories/`. Group the identified domain-specific methods into logical repository classes within this directory:
    *   `InstrumentRepository`
    *   `TradeRepository`
    *   `OrderRepository`
    *   `OhlcRepository`
    *   `TickerRepository`
    *   `SystemRepository`
    *   Each repository will be initialized with an instance of the `PostgresClient`.

3.  **Refactor `PostgresClient`:** Remove all domain-specific methods. The final class must only contain its `__init__`, context managers, connection pool logic, `_parse_resolution_to_timedelta`, `_setup_json_codec`, and the four generic execution methods.

4.  **Implement Repositories:** Create the new repository files. Implement the classes designed in Step 2. The internal logic of the methods will be identical to their previous versions but will now call the generic client (e.g., `return await self._db.fetch(...)`).

5.  **Refactor All Consumer Services:**
    *   **Receiver (`deribit.py`):** Inject `InstrumentRepository` and refactor the call to `fetch_instruments_by_exchange`.
    *   **Executor (`state_manager.py`):** Inject `InstrumentRepository` and `OhlcRepository`. Refactor calls to `fetch_instruments_by_exchange` and `fetch_ohlc_for_instrument`.
    *   **Janitor (`tasks.py`):** Inject `InstrumentRepository` and refactor the call to `bulk_upsert_instruments`.
    *   **Maintenance (`service.py`):** No changes needed. It correctly uses the generic `execute` method.

6.  **Update Service Orchestration (`main.py`):** For each affected service, update its `main.py` file to instantiate the required repositories and inject them into the service class.

**Verification Checklist:**
*   `PostgresClient` contains *only* generic methods. (Yes/No)
*   All domain methods are successfully moved to the correct repository. (Yes/No)
*   `receiver`, `executor`, and `janitor` services are refactored to use the new repositories. (Yes/No)
*   The `main.py` file for each affected service is updated to handle dependency injection. (Yes/No)
*   The `maintenance` service remains untouched. (Yes/No)