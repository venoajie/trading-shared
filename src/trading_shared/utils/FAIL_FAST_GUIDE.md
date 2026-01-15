# Fail-Fast Implementation Guide

## 🎯 Problem: Silent Async Death

When background tasks created with `asyncio.create_task()` raise unhandled exceptions, they die silently. The container stays `Up` in Docker, but the service is partially broken. This is called **"Silent Async Death"**.

### Before (❌ Bad):
```python
# Task dies silently, container stays "Up", failure is masked
task = asyncio.create_task(my_background_worker())
```

### After (✅ Good):
```python
from shared.utils.fail_fast import create_fail_fast_task

# Task failure kills the process, Docker restarts container
task = create_fail_fast_task(my_background_worker(), name="worker")
```

---

## 🚀 Quick Start

### 1. Import the utility
```python
from shared.utils.fail_fast import create_fail_fast_task
```

### 2. Replace `asyncio.create_task()` calls
```python
# OLD CODE:
self._tasks = [
    asyncio.create_task(self._run_loop_1()),
    asyncio.create_task(self._run_loop_2()),
]

# NEW CODE:
self._tasks = [
    create_fail_fast_task(self._run_loop_1(), name="loop_1"),
    create_fail_fast_task(self._run_loop_2(), name="loop_2"),
]
```

---

## 📋 Implementation Examples

### Example 1: Service with Multiple Background Tasks

```python
# src/services/myservice/myservice/service.py

import asyncio
from typing import List
from loguru import logger as log
from shared.utils.fail_fast import create_fail_fast_task

class MyService:
    def __init__(self):
        self.is_running = asyncio.Event()
        self._tasks: List[asyncio.Task] = []
    
    async def start(self):
        log.info("Starting MyService...")
        self.is_running.set()
        
        # Create all background tasks with fail-fast protection
        self._tasks = [
            create_fail_fast_task(
                self._data_processor_loop(),
                name="myservice_data_processor"
            ),
            create_fail_fast_task(
                self._health_check_loop(),
                name="myservice_health_check"
            ),
            create_fail_fast_task(
                self._metrics_reporter_loop(),
                name="myservice_metrics_reporter"
            ),
        ]
        
        log.info("MyService started with fail-fast protection.")
    
    async def close(self):
        log.info("Closing MyService...")
        self.is_running.clear()
        
        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for cancellation to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)
        log.info("MyService closed.")
    
    async def _data_processor_loop(self):
        """Background task that processes data continuously."""
        while self.is_running.is_set():
            try:
                await self._process_data()
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                # Expected during shutdown
                break
            except Exception:
                # This will be caught by fail_fast and kill the process
                log.exception("Critical error in data processor")
                raise
    
    async def _health_check_loop(self):
        """Background task that performs health checks."""
        while self.is_running.is_set():
            try:
                await self._check_health()
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Critical error in health check")
                raise
    
    async def _metrics_reporter_loop(self):
        """Background task that reports metrics."""
        while self.is_running.is_set():
            try:
                await self._report_metrics()
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Critical error in metrics reporter")
                raise
```

### Example 2: Dynamic Worker Pool

```python
# src/services/backfill/backfill/service.py

from shared.utils.fail_fast import create_fail_fast_task

class BackfillService:
    async def start(self):
        worker_count = self.settings.worker_count
        log.info(f"Spawning {worker_count} workers with fail-fast protection...")
        
        # Create multiple workers dynamically
        worker_tasks = [
            create_fail_fast_task(
                self._run_worker(worker_id),
                name=f"backfill_worker_{worker_id}"
            )
            for worker_id in range(worker_count)
        ]
        
        # Create reconciliation task
        reconciler_task = create_fail_fast_task(
            self._reconciliation_loop(),
            name="backfill_reconciliation"
        )
        
        self._tasks = worker_tasks + [reconciler_task]
        log.success("Backfill Service started with fail-fast protection.")
```

### Example 3: Stream Consumers

```python
# src/services/distributor/distributor/service.py

from shared.utils.fail_fast import create_fail_fast_task

class DistributorService:
    async def start(self):
        log.info(f"Starting consumers for streams: {self.all_streams}")
        self.is_running.set()
        
        # Create a consumer task for each stream
        for stream_name in self.all_streams:
            task = create_fail_fast_task(
                self._start_consumer(stream_name),
                name=f"distributor_consumer_{stream_name.replace(':', '_')}"
            )
            self._tasks.append(task)
        
        # Create cache refresh task
        cache_task = create_fail_fast_task(
            self._cache_refresh_loop(),
            name="distributor_cache_refresh"
        )
        self._tasks.append(cache_task)
        
        log.info("Distributor started with fail-fast protection.")
```

---

## 🔍 What Happens When a Task Fails?

### 1. Exception is Caught
The fail-fast callback catches any unhandled exception in the task.

### 2. Critical Log is Written
```
╔═══════════════════════════════════════════════════════════════╗
║ FATAL: Unhandled exception in background task 'worker_loop'
║ The process will now EXIT to trigger container restart
╚═══════════════════════════════════════════════════════════════╝

Exception: ValueError: Invalid data format

Full Traceback:
Traceback (most recent call last):
  File "service.py", line 42, in _worker_loop
    await process_data(data)
ValueError: Invalid data format
```

### 3. Process Exits with Code 1
```python
sys.exit(1)
```

### 4. Docker Restarts the Container
```bash
$ docker ps
CONTAINER ID   STATUS
abc123def456   Restarting (1) 2 seconds ago
```

### 5. Fresh Start
The container restarts with a clean state, preventing zombie services.

---

## 🎨 Advanced Usage: Decorator Pattern

For critical coroutines that should never fail silently, use the decorator:

```python
from shared.utils.fail_fast import wrap_critical_coroutine

class MyService:
    @wrap_critical_coroutine
    async def _critical_reconciliation_loop(self):
        """This loop is so critical that any failure should restart the service."""
        while self.is_running.is_set():
            await self._reconcile_state()
            await asyncio.sleep(60)
    
    async def start(self):
        # No need for create_fail_fast_task here, the decorator handles it
        await self._critical_reconciliation_loop()
```

---

## ⚠️ Important Notes

### 1. **CancelledError is Handled Gracefully**
The fail-fast utility recognizes `asyncio.CancelledError` as a normal shutdown signal and does NOT kill the process.

```python
# This is safe - cancellation won't trigger process exit
task.cancel()
await task  # CancelledError is caught and logged, not fatal
```

### 2. **Name Your Tasks**
Always provide descriptive names for easier debugging:

```python
# ❌ Bad - generic name
create_fail_fast_task(self._loop())

# ✅ Good - descriptive name
create_fail_fast_task(self._loop(), name="analyzer_realtime_analysis")
```

### 3. **Use in Services, Not in Main**
The `main()` function should already have top-level exception handling. Use fail-fast for background tasks only:

```python
# main.py - Already has exception handling
async def main() -> int:
    try:
        service = MyService()
        await service.start()  # This is fine
        await shutdown_event.wait()
    except Exception:
        log.exception("Service failed")
        return 1
    return 0

# service.py - Use fail-fast for background tasks
class MyService:
    async def start(self):
        self._task = create_fail_fast_task(
            self._background_loop(),
            name="background_loop"
        )
```

---

## 🧪 Testing Fail-Fast Behavior

### Test 1: Verify Process Exit
```python
import asyncio
import sys
from shared.utils.fail_fast import create_fail_fast_task

async def failing_task():
    await asyncio.sleep(1)
    raise ValueError("Test failure")

async def test():
    task = create_fail_fast_task(failing_task(), name="test_task")
    await asyncio.sleep(2)  # Wait for task to fail

# Run this - the process should exit with code 1
asyncio.run(test())
```

### Test 2: Verify Cancellation is Safe
```python
async def cancellable_task():
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        print("Task cancelled gracefully")
        raise

async def test():
    task = create_fail_fast_task(cancellable_task(), name="test_task")
    await asyncio.sleep(2)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    print("Process still running - cancellation didn't kill it")

# Run this - the process should NOT exit
asyncio.run(test())
```

---

## 📊 Migration Checklist

- [ ] Import `create_fail_fast_task` in all service files
- [ ] Replace all `asyncio.create_task()` calls with `create_fail_fast_task()`
- [ ] Add descriptive names to all tasks
- [ ] Remove old exception logging callbacks (if any)
- [ ] Test service restart behavior in Docker
- [ ] Monitor logs for fail-fast messages
- [ ] Update service documentation

---

## 🔗 Related Files

- **Utility Implementation**: `src/shared/utils/fail_fast.py`
- **Updated Services**:
  - `src/services/analyzer/analyzer/service.py`
  - `src/services/backfill/backfill/service.py`
  - `src/services/distributor/distributor/service.py`
  - `src/services/maintenance/maintenance/service.py`

---

## 📚 Further Reading

- [Python asyncio Tasks](https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task)
- [Docker Container Restart Policies](https://docs.docker.com/config/containers/start-containers-automatically/)
- [Kubernetes Liveness Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
