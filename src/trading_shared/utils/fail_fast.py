"""
Fail-Fast Task Management Utility

Prevents "Silent Async Death" by ensuring unhandled exceptions in background
tasks cause the process to exit loudly, triggering container restarts.

Usage:
    from shared.utils.fail_fast import create_fail_fast_task
    
    task = create_fail_fast_task(my_coroutine(), name="my_task")
"""

import sys
import asyncio
import traceback
from typing import Coroutine, Optional
from loguru import logger as log


def _task_exception_handler(task: asyncio.Task, context: str) -> None:
    """
    Callback that handles task exceptions by logging and killing the process.
    
    Args:
        task: The asyncio Task that completed
        context: Human-readable description of what the task was doing
    """
    try:
        task.result()
    except asyncio.CancelledError:
        log.info(f"Task '{context}' was cancelled (normal shutdown)")
    except Exception as exc:
        log.critical(
            f"╔═══════════════════════════════════════════════════════════════╗\n"
            f"║ FATAL: Unhandled exception in background task '{context}'\n"
            f"║ The process will now EXIT to trigger container restart\n"
            f"╚═══════════════════════════════════════════════════════════════╝\n"
            f"\nException: {exc}\n"
            f"\nFull Traceback:\n{traceback.format_exc()}"
        )
        sys.exit(1)


def create_fail_fast_task(
    coro: Coroutine,
    *,
    name: Optional[str] = None,
) -> asyncio.Task:
    """
    Create an asyncio task with fail-fast error handling.
    
    If the task raises an unhandled exception, the entire process will exit
    with code 1, causing Docker to restart the container.
    
    Args:
        coro: The coroutine to run as a task
        name: Human-readable name for the task (used in logs)
    
    Returns:
        asyncio.Task with fail-fast callback attached
    """
    task = asyncio.create_task(coro)
    context_name = name or getattr(coro, '__name__', 'unnamed_task')
    task.add_done_callback(lambda t: _task_exception_handler(t, context_name))
    return task
