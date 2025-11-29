# src\trading_shared\exchange\websockets\base.py

from abc import ABC, abstractmethod


class AbstractWsClient(ABC):
    """An abstract base class for exchange WebSocket clients."""

    @abstractmethod
    async def connect(self):
        raise NotImplementedError

    @abstractmethod
    async def process_messages(self):
        raise NotImplementedError

    @abstractmethod
    async def close(self):
        raise NotImplementedError
