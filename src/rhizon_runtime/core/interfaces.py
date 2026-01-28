from typing import Protocol, List, Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel
from rhizon_runtime.core.models import EventEnvelope

class HealthStatus(str, Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"

class AgentState(BaseModel):
    """
    Minimal Agent State schema.
    Must be JSON-serializable and stable.
    """
    version: int
    entity_versions: Dict[str, int] = {}
    data: Dict[str, Any]
    last_processed_event_id: Optional[str] = None
    updated_at: int

class AgentRuntimeAdapter(Protocol):
    """
    Protocol defining the contract for any Agent running in MeshForge.
    Must be pure/deterministic given the inputs.
    """
    
    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        """
        Process a single incoming event (Command) and return resulting events.
        MUST be idempotent based on envelope.idempotency_key.
        Should NOT mutate state directly if using Event Sourcing (use apply instead),
        but for V0 simple agents, it might.
        """
        ...

    def apply(self, envelope: EventEnvelope) -> None:
        """
        Apply a committed event to the agent's state.
        Used for:
        1. State updates after successful command processing.
        2. Replaying state from Event Store.
        """
        ...

    def tick(self, now: int) -> List[EventEnvelope]:
        """
        Periodic tick for time-based logic (retries, timeouts).
        'now' is provided by the Runtime (injected).
        """
        ...

    def get_state(self) -> AgentState:
        """
        Return the current internal state of the agent.
        MUST be JSON-serializable and stable.
        """
        ...

    def health(self) -> HealthStatus:
        """
        Report agent health (READY, DEGRADED, FAILED) with reasons.
        """
        ...

class EventBus(Protocol):
    """
    Abstract Interface for the Event Bus.
    """
    async def publish(self, events: List[EventEnvelope]) -> None: ...
    # async def subscribe(self, pattern: str, callback: Callable) -> None: ... # Omitted for V0 minimal

class EventStoreAdapter(Protocol):
    """
    Protocol for Event Sourcing Persistence.
    """
    def append(self, event: EventEnvelope) -> None:
        """
        Append a single event to the store.
        """
        ...

    def append_batch(self, events: List[EventEnvelope]) -> None:
        """
        Append a batch of events transactionally.
        MUST guarantee strict ordering and idempotence via idempotency_key.
        """
        ...

    def replay(self, from_offset: int = 0, filters: Optional[Dict[str, Any]] = None) -> List[EventEnvelope]:
        """
        Replay events from a global offset.
        Useful for restoring state.
        """
        ...

    def get_by_idempotency_key(self, key: str) -> List[EventEnvelope]:
        """
        Retrieve events associated with a specific idempotency key.
        Used for handling duplicate commands (returning original result).
        """
        ...

class Router(Protocol):
    """
    Protocol for routing commands between agents.
    """
    async def route(self, envelope: EventEnvelope) -> None:
        """
        Route a command envelope to the appropriate destination (Agent/Engine).
        """
        ...

