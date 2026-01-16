# tests/trading_shared/utils/test_fail_fast.py

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from trading_shared.utils.fail_fast import _task_exception_handler, create_fail_fast_task


class TestTaskExceptionHandler:
    """Tests for _task_exception_handler function."""

    def test_cancelled_task_logs_info(self):
        task = MagicMock(spec=asyncio.Task)
        task.result.side_effect = asyncio.CancelledError()

        with patch("trading_shared.utils.fail_fast.log") as mock_log:
            _task_exception_handler(task, "test_task")
            mock_log.info.assert_called_once()
            assert "cancelled" in mock_log.info.call_args[0][0].lower()

    def test_exception_logs_critical_and_exits(self):
        task = MagicMock(spec=asyncio.Task)
        test_exception = ValueError("Test error")
        task.result.side_effect = test_exception

        with patch("trading_shared.utils.fail_fast.log") as mock_log:
            with patch("sys.exit") as mock_exit:
                _task_exception_handler(task, "test_task")
                mock_log.critical.assert_called_once()
                mock_exit.assert_called_once_with(1)

    def test_successful_task_no_action(self):
        task = MagicMock(spec=asyncio.Task)
        task.result.return_value = "success"

        with patch("trading_shared.utils.fail_fast.log") as mock_log:
            with patch("sys.exit") as mock_exit:
                _task_exception_handler(task, "test_task")
                mock_log.critical.assert_not_called()
                mock_exit.assert_not_called()


class TestCreateFailFastTask:
    """Tests for create_fail_fast_task function."""

    @pytest.mark.asyncio
    async def test_creates_task_with_callback(self):
        async def dummy_coro():
            await asyncio.sleep(0.01)
            return "done"

        task = create_fail_fast_task(dummy_coro(), name="test_task")
        assert isinstance(task, asyncio.Task)
        assert len(task._callbacks) > 0
        result = await task
        assert result == "done"

    @pytest.mark.asyncio
    async def test_task_name_from_parameter(self):
        async def my_coroutine():
            await asyncio.sleep(0.01)

        task = create_fail_fast_task(my_coroutine(), name="custom_name")
        assert isinstance(task, asyncio.Task)
        await task

    @pytest.mark.asyncio
    async def test_task_name_from_coroutine_when_not_provided(self):
        async def named_coroutine():
            await asyncio.sleep(0.01)

        task = create_fail_fast_task(named_coroutine())
        assert isinstance(task, asyncio.Task)
        await task

    @pytest.mark.asyncio
    async def test_exception_in_task_triggers_exit(self):
        async def failing_coro():
            await asyncio.sleep(0.01)
            raise ValueError("Intentional failure")

        with patch("sys.exit") as mock_exit:
            with patch("trading_shared.utils.fail_fast.log"):
                task = create_fail_fast_task(failing_coro(), name="failing_task")
                with pytest.raises(ValueError):
                    await task
                await asyncio.sleep(0.05)
                mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_cancelled_task_does_not_exit(self):
        async def long_running_coro():
            await asyncio.sleep(10)

        with patch("sys.exit") as mock_exit:
            with patch("trading_shared.utils.fail_fast.log"):
                task = create_fail_fast_task(long_running_coro(), name="cancelled_task")
                await asyncio.sleep(0.01)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                await asyncio.sleep(0.05)
                mock_exit.assert_not_called()
