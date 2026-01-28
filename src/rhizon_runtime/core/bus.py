from typing import List, Dict, Callable, Awaitable
import asyncio
from rhizon_runtime.core.models import EventEnvelope
from rhizon_runtime.core.interfaces import EventBus

class InMemoryBus:
    """
    V0 In-Memory Bus implementation for local dev and testing.
    Synchronous execution of subscribers for determinism in tests.
    """
    def __init__(self):
        self._subscribers: List[Callable[[EventEnvelope], Awaitable[None]]] = []
        self.published_events: List[EventEnvelope] = [] # For introspection/replay verification

    async def publish(self, events: List[EventEnvelope]) -> None:
        for event in events:
            self.published_events.append(event)
            # Naive broadcast for V0
            for callback in self._subscribers:
                await callback(event)

    def subscribe(self, callback: Callable[[EventEnvelope], Awaitable[None]]) -> None:
        self._subscribers.append(callback)
    
    def clear(self):
        self.published_events.clear()
