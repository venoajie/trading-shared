# tests/trading_shared/utils/test_resource_manager.py

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from trading_shared.utils.resource_manager import managed_resources


# Mock resource classes for testing
class MockAsyncExitResource:
    def __init__(self, name="AsyncExit"):
        self.name = name
        self.__aexit__ = AsyncMock()

    def __repr__(self):
        return f"MockAsyncExitResource(name='{self.name}')"


class MockCloseableResource:
    def __init__(self, name="Closeable"):
        self.name = name
        self.close = AsyncMock()

    def __repr__(self):
        return f"MockCloseableResource(name='{self.name}')"


class MockNonCloseableResource:
    def __init__(self, name="NonCloseable"):
        self.name = name

    def __repr__(self):
        return f"MockNonCloseableResource(name='{self.name}')"


@pytest.mark.asyncio
async def test_managed_resources_closes_in_reverse_order():
    # Arrange
    resource1 = MockCloseableResource("Resource1")
    resource2 = MockAsyncExitResource("Resource2")

    # Use a manager mock to track the order of calls
    manager = MagicMock()
    manager.attach_mock(resource1.close, "res1_close")
    manager.attach_mock(resource2.__aexit__, "res2_aexit")

    # Act
    async with managed_resources([resource1, resource2]):
        pass  # Do nothing inside the context

    # Assert
    # The calls should be in reverse order of the list
    expected_calls = [
        call.res2_aexit(None, None, None),
        call.res1_close(),
    ]
    assert manager.mock_calls == expected_calls


@pytest.mark.asyncio
async def test_managed_resources_handles_mixed_resource_types():
    # Arrange
    res1 = MockCloseableResource()
    res2 = MockAsyncExitResource()
    res3 = MockNonCloseableResource()

    # Act
    async with managed_resources([res1, res2, res3]):
        pass

    # Assert
    res1.close.assert_awaited_once()
    res2.__aexit__.assert_awaited_once_with(None, None, None)
    # res3 has no close method, so it should not be called and no error raised


@pytest.mark.asyncio
async def test_managed_resources_continues_closing_if_one_fails(mocker):
    # Arrange
    res1 = MockCloseableResource("Resource1")
    res2 = MockCloseableResource("Resource2_Fails")

    # Make the second resource's close method raise an exception
    res2.close.side_effect = ValueError("Failed to close")

    # Spy on the log to ensure the error is logged
    log_spy = mocker.spy(mocker.patch("trading_shared.utils.resource_manager.log"), "exception")

    # Act
    # The context manager should suppress the exception from close()
    async with managed_resources([res1, res2]):
        pass

    # Assert
    # Both close methods should have been called
    res1.close.assert_awaited_once()
    res2.close.assert_awaited_once()

    # Verify that the exception was logged
    log_spy.assert_called_once_with("A non-critical error occurred while closing resource: 'MockCloseableResource'")


@pytest.mark.asyncio
async def test_managed_resources_propagates_exception_from_context_body():
    # Arrange
    res1 = MockCloseableResource()

    # Act & Assert
    with pytest.raises(RuntimeError, match="Error inside context"):
        async with managed_resources([res1]):
            raise RuntimeError("Error inside context")

    # The resource should still be closed even if the context body fails
    res1.close.assert_awaited_once()
