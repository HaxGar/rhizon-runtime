from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from rhizon_runtime.core.interfaces import AgentRuntimeAdapter, AgentState, HealthStatus
from rhizon_runtime.core.models import EventEnvelope

import logging

logger = logging.getLogger(__name__)

class LockState(BaseModel):
    owner_id: str
    expires_at: int
    acquired_at: int

class LockManagerAdapter(AgentRuntimeAdapter):
    """
    A System Agent that provides cooperative locking via Lease mechanism.
    Event-Sourced, Deterministic, and strictly Non-Blocking.
    """
    def __init__(self):
        # State: resource_id -> LockState
        self.locks: Dict[str, LockState] = {}
        self.version = 0
        self.last_processed_id = None

    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        # Loose check for lock commands
        msg_type = envelope.type
        logger.info(f"LockManager received: {msg_type} (id={envelope.id})")
        
        # Check for command verb at the end
        if msg_type.endswith(".acquire"):
            logger.info("Processing acquire command")
            return self._handle_acquire(envelope)
        elif msg_type.endswith(".release"):
            logger.info("Processing release command")
            return self._handle_release(envelope)
        elif msg_type.endswith(".refresh"):
            logger.info("Processing refresh command")
            return self._handle_refresh(envelope)
            
        logger.warning(f"LockManager ignored unknown command type: {msg_type}")
        return []

    def _handle_acquire(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        payload = envelope.payload
        resource_id = payload.get("resource_id")
        owner_id = payload.get("owner_id")
        ttl_ms = payload.get("ttl_ms", 5000) # Default 5s

        if not resource_id or not owner_id:
            return [] # Invalid command, maybe log?

        now = envelope.ts
        current_lock = self.locks.get(resource_id)

        # Check if locked and valid
        if current_lock and current_lock.expires_at > now:
            # Already locked
            if current_lock.owner_id == owner_id:
                # Idempotent re-acquire or refresh
                return [self._create_event(envelope, "evt.lock.acquired", {
                    "resource_id": resource_id,
                    "owner_id": owner_id,
                    "expires_at": now + ttl_ms
                })]
            else:
                # Denied
                return [self._create_event(envelope, "evt.lock.denied", {
                    "resource_id": resource_id,
                    "requested_by": owner_id,
                    "current_owner": current_lock.owner_id,
                    "reason": "Already locked by another owner"
                })]
        
        # Free or Expired -> Acquire
        return [self._create_event(envelope, "evt.lock.acquired", {
            "resource_id": resource_id,
            "owner_id": owner_id,
            "expires_at": now + ttl_ms
        })]

    def _handle_release(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        payload = envelope.payload
        resource_id = payload.get("resource_id")
        owner_id = payload.get("owner_id")

        current_lock = self.locks.get(resource_id)

        if not current_lock:
             # Already free, treat as success (idempotent)
             return [self._create_event(envelope, "evt.lock.released", {
                "resource_id": resource_id,
                "owner_id": owner_id
            })]

        if current_lock.owner_id != owner_id:
            # Not the owner
            return [self._create_event(envelope, "evt.lock.denied", {
                "resource_id": resource_id,
                "requested_by": owner_id,
                "current_owner": current_lock.owner_id,
                "reason": "Cannot release lock owned by another"
            })]

        # Success
        return [self._create_event(envelope, "evt.lock.released", {
            "resource_id": resource_id,
            "owner_id": owner_id
        })]

    def _handle_refresh(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        payload = envelope.payload
        resource_id = payload.get("resource_id")
        owner_id = payload.get("owner_id")
        ttl_ms = payload.get("ttl_ms", 5000)

        current_lock = self.locks.get(resource_id)
        now = envelope.ts

        if not current_lock or current_lock.expires_at <= now:
             return [self._create_event(envelope, "evt.lock.denied", {
                "resource_id": resource_id,
                "requested_by": owner_id,
                "reason": "Lock not held or expired"
            })]
            
        if current_lock.owner_id != owner_id:
             return [self._create_event(envelope, "evt.lock.denied", {
                "resource_id": resource_id,
                "requested_by": owner_id,
                "current_owner": current_lock.owner_id,
                "reason": "Lock held by another"
            })]

        return [self._create_event(envelope, "evt.lock.acquired", {
            "resource_id": resource_id,
            "owner_id": owner_id,
            "expires_at": now + ttl_ms
        })]

    def apply(self, envelope: EventEnvelope) -> None:
        self.version += 1
        self.last_processed_id = envelope.id
        
        payload = envelope.payload
        resource_id = payload.get("resource_id")
        
        if envelope.type == "evt.lock.acquired":
            self.locks[resource_id] = LockState(
                owner_id=payload["owner_id"],
                expires_at=payload["expires_at"],
                acquired_at=envelope.ts
            )
        elif envelope.type == "evt.lock.released":
             if resource_id in self.locks:
                 del self.locks[resource_id]
        elif envelope.type == "evt.lock.expired":
             if resource_id in self.locks:
                 del self.locks[resource_id]

    def tick(self, now: int) -> List[EventEnvelope]:
        # Check for expired locks but DON'T delete them here
        # State mutation should only happen in apply() for Event Sourcing compliance
        expired_events = []
        
        # Snapshot keys to avoid runtime error during iteration
        for resource_id, state in list(self.locks.items()):
            if state.expires_at <= now:
                # Generate expiration event with proper tenant/workspace context
                # Note: For system-level locks, we use the engine's tenant/workspace
                evt = EventEnvelope(
                    id=f"evt-expired-{resource_id}-{now}",
                    ts=now,
                    type="evt.lock.expired",
                    payload={"resource_id": resource_id},
                    idempotency_key=f"lock-expired-{resource_id}-{now}",  # Unique key for tick events
                    source={"agent": "lock_manager", "adapter": "default"},
                    tenant="system",  # LockManager is usually system-level
                    workspace="shared",
                    actor={"id": "system", "role": "lock_manager"},
                    trace_id="",  # New trace?
                    span_id="",
                    causation_id=None,
                    correlation_id=None,
                    reply_to=None,
                    entity_id=resource_id,
                    expected_version=None,
                    security_context={"principal_id": "system", "principal_type": "system"}
                )
                expired_events.append(evt)
                # NOTE: Don't delete lock here - let apply() handle it
        
        return expired_events

    def get_state(self) -> AgentState:
        # Serialize locks
        locks_data = {
            k: v.model_dump() for k, v in self.locks.items()
        }
        return AgentState(
            version=self.version,
            data={"locks": locks_data},
            last_processed_event_id=self.last_processed_id,
            updated_at=0 # TODO: Track last update time
        )

    def health(self) -> HealthStatus:
        return HealthStatus.READY

    def _create_event(self, cmd: EventEnvelope, type: str, payload: Dict[str, Any]) -> EventEnvelope:
        return EventEnvelope(
            id=f"evt-{cmd.id}-{type.split('.')[-1]}",
            ts=cmd.ts,
            type=type,
            payload=payload,
            idempotency_key=cmd.idempotency_key,  # Use same key as command for proper idempotency
            source={"agent": "lock_manager", "adapter": "default"},
            tenant=cmd.tenant,
            workspace=cmd.workspace,
            actor=cmd.actor,
            trace_id=cmd.trace_id,
            span_id=cmd.span_id,
            causation_id=cmd.id,
            correlation_id=cmd.correlation_id,
            security_context=cmd.security_context
        )
