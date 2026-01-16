# Unit Tests for trading-shared

## Test Coverage

This directory contains comprehensive unit tests for the `trading-shared` package.

### Test Files Created

1. **test_universe_config.py** - Tests for universe configuration loading and validation
   - FilterSettings model validation
   - UniverseDefinition model validation
   - UniverseConfig loading from TOML files
   - Exception chaining with proper `from` clause (B904 compliance)

2. **test_asset_utils.py** - Tests for asset normalization utilities
   - Denomination prefix removal (1000, 10000, etc.)
   - Leveraged token suffix removal (UP, DOWN)
   - Edge cases and combinations

3. **test_identity.py** - Tests for identity management
   - UUID generation for account IDs
   - Identity provisioning with database mocking
   - Deterministic UUID generation

4. **test_fail_fast.py** - Tests for fail-fast task management
   - Task creation with exception handlers
   - Process exit on unhandled exceptions
   - Cancellation handling

5. **test_healthcheck.py** - Tests for DeadManSwitch healthcheck
   - Heartbeat loop functionality
   - Start/stop operations
   - Redis interaction and error handling

6. **test_labelling.py** - Tests for strategy labelling utilities
   - Label generation with/without cycle IDs
   - Closing label generation
   - Label parsing for legacy and new formats

7. **test_constants.py** - Tests for constant definitions
   - Exchange name constants validation

8. **test_mappers.py** - Tests for exchange market type mappers
   - Deribit market type mapping (all variants)
   - Binance market type mapping with hints
   - Edge cases and unknown types

9. **test_transformers.py** - Tests for exchange instrument transformers
   - Binance instrument transformation (spot, futures, perpetual)
   - Deribit instrument transformation
   - Expiration timestamp handling

10. **test_risk_models.py** - Tests for risk management models
    - PMEParamsCurrency validation
    - PMEParams with API format restructuring
    - MarginCalculationResult validation

11. **test_notification_models.py** - Tests for notification models
    - TradeNotification validation
    - SystemAlert with severity levels

12. **test_universe_cache.py** - Tests for universe caching
    - Symbol normalization and lookup
    - Storage mode retrieval
    - Thread-safe concurrent access

13. **test_binance_websocket.py** - Tests for Binance WebSocket client
    - Channel generation from universe
    - Sharding logic
    - Symbol normalization (C414 compliance - removed unnecessary list())

14. **test_pme_calculator.py** - Tests for portfolio margin calculator
    - Margin calculation with tracked positions
    - Hypothetical position handling
    - API error handling

## Code Quality Fixes

### Ruff Compliance

All source code issues identified by `ruff check --fix` have been resolved:

1. **B904 - Exception Chaining**: Fixed in `universe_config.py`
   ```python
   # Before:
   raise RuntimeError(f"UniverseConfig validation failed for {path.absolute()}: {e}")
   
   # After:
   raise RuntimeError(f"UniverseConfig validation failed for {path.absolute()}: {e}") from e
   ```

2. **C414 - Unnecessary list() call**: Fixed in `binance.py`
   ```python
   # Before:
   sharded_targets = {sym for i, sym in enumerate(sorted(list(my_targets))) if i % self.total_shards == self.shard_id}
   
   # After:
   sharded_targets = {sym for i, sym in enumerate(sorted(my_targets)) if i % self.total_shards == self.shard_id}
   ```

## Running Tests

### Run all unit tests:
```bash
pytest tests/unit/shared/ -v
```

### Run with coverage:
```bash
pytest tests/unit/shared/ -v --cov=src/trading_shared --cov-report=term-missing
```

### Run specific test file:
```bash
pytest tests/unit/shared/test_universe_config.py -v
```

## Test Characteristics

✅ **All tests are isolated** - No external dependencies (Redis, PostgreSQL, network)
✅ **Fast execution** - All tests complete in <5 seconds total
✅ **Async support** - Proper use of `pytest.mark.asyncio` for async tests
✅ **Comprehensive mocking** - All external dependencies are mocked
✅ **Edge case coverage** - Tests cover error conditions and boundary cases
✅ **Docstrings** - All test classes and modules include explanatory docstrings
✅ **Ruff compliant** - All code passes `ruff check --fix` without errors

## Coverage Targets

Based on `.github/workflows/python-publish.yml`:
- **Minimum coverage**: 90%
- **Target**: 85-100% depending on module complexity

## CI/CD Integration

These tests are designed to run in the GitHub Actions workflow defined in `.github/workflows/python-publish.yml`:

```yaml
- name: Test with Pytest and generate coverage report
  env:
    PYTHONPATH: src
  run: |
    python -m pytest \
      --cov=src \
      --cov-report=xml \
      --cov-fail-under=90
```
