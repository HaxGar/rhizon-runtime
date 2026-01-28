from typing import List, Dict, Any, Optional
from rhizon_runtime.core.interfaces import AgentRuntimeAdapter, HealthStatus, AgentState
from rhizon_runtime.core.models import EventEnvelope
import logging

logger = logging.getLogger("meshforge.managers.crud")

class GenericCRUDManagerAdapter:
    """
    A generic, framework-agnostic CRUD Manager.
    Manages state for a specific object type (e.g., 'User', 'Order').
    Deterministic and Event-Sourced compatible (in-memory for V0).
    """

    def __init__(self, object_name: str):
        self.object_name = object_name
        # State: id -> {id, version, data, last_idempotency_key}
        self._state: Dict[str, Dict[str, Any]] = {} 
        self._processed_keys: Dict[str, str] = {}
        self._version = 0 # Global Agent State Version

    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        """
        Process incoming commands. Pure function relative to current state.
        """
        msg_type = envelope.type
        obj_name = self.object_name.lower()
        
        # Loose check: must contain object name and start with cmd.
        if "cmd." not in msg_type or obj_name not in msg_type:
            return []

        # Extract command (last part)
        command = msg_type.split(".")[-1]
        
        try:
            if command == "create":
                return self._handle_create(envelope)
            elif command == "update":
                return self._handle_update(envelope)
            elif command == "delete":
                return self._handle_delete(envelope)
            elif command == "get":
                return self._handle_get(envelope)
            elif command == "list":
                return self._handle_list(envelope)
            else:
                return [self._error(envelope, "unknown_command", f"Command '{command}' not supported.")]
        except Exception as e:
            logger.exception(f"Error processing {msg_type}")
            return [self._error(envelope, "internal_error", str(e))]

    def apply(self, envelope: EventEnvelope) -> None:
        """
        Apply committed event to state.
        """
        # Only interested in events for this object
        prefix = f"evt.{self.object_name.lower()}"
        if not envelope.type.startswith(prefix):
            return

        evt_type = envelope.type[len(prefix)+1:] # created, updated, deleted...
        payload = envelope.payload
        obj_id = payload.get("id")
        
        if not obj_id:
            return

        # Increment global state version on any modification
        self._version += 1

        if evt_type == "created":
            # For created, the payload IS the entity structure usually, or contains data
            # In receive(), we returned the full entity structure as payload
            self._state[obj_id] = payload.copy()
            
        elif evt_type == "updated":
            # Payload is the full updated entity
            self._state[obj_id] = payload.copy()
            
        elif evt_type == "deleted":
            if obj_id in self._state:
                del self._state[obj_id]

    def tick(self, now: int) -> List[EventEnvelope]:
        return []

    def get_state(self) -> AgentState:
        # Construct entity_versions map
        entity_versions = {
            obj_id: data["entity_version"] 
            for obj_id, data in self._state.items()
        }
        
        return AgentState(
            version=self._version, 
            entity_versions=entity_versions,
            data={"count": len(self._state)}, # Don't dump everything by default
            updated_at=0 # Todo: track time
        )

    def health(self) -> HealthStatus:
        return HealthStatus.READY

    # --- Handlers (Pure Decisions) ---

    def _handle_create(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        payload = envelope.payload
        obj_id = payload.get("id")
        key = envelope.idempotency_key
        
        if not obj_id:
            return [self._error(envelope, "validation_error", "Missing 'id' in payload.")]

        existing = self._state.get(obj_id)
        if existing:
            # Check idempotency based on the stored state's last key
            # In a full ES system we might check the event store, but here state is sufficient
            if existing.get("last_idempotency_key") == key:
                return [self._event(envelope, "created", existing)]
            else:
                return [self._error(envelope, "conflict", f"Entity {obj_id} already exists.")]

        # Create
        entity = {
            "id": obj_id,
            "entity_version": 1,
            "data": payload.get("data", {}),
            "last_idempotency_key": key
        }
        # self._state[obj_id] = entity  <-- REMOVED MUTATION
        
        return [self._event(envelope, "created", entity)]

    def _handle_update(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        payload = envelope.payload
        obj_id = payload.get("id")
        key = envelope.idempotency_key
        expected_version = payload.get("expected_version")
        
        if not obj_id:
            return [self._error(envelope, "validation_error", "Missing 'id' in payload.")]

        existing = self._state.get(obj_id)
        if not existing:
            return [self._error(envelope, "not_found", f"Entity {obj_id} not found.")]

        if existing.get("last_idempotency_key") == key:
             return [self._event(envelope, "updated", existing)]

        # Note: RuntimeEngine performs the CORE concurrency check (Agent Version).
        # This adapter-level check is for Entity Version (if we wanted fine-grained).
        # For V0, since RuntimeEngine checks global version, this check might be redundant 
        # OR it checks the internal entity version. 
        # Let's keep it but ensure we understand the difference.
        # If the user passed expected_version for the AGENT, RuntimeEngine checked it.
        # If they passed it for the ENTITY, we check it here.
        # But payload key is the same.
        # Let's assume expected_version in payload is for Entity, expected_version in Envelope is for Agent.
        # But our test puts it in both or Envelope maps to Payload?
        # EventEnvelope has expected_version field. Payload has it too?
        # Let's assume Envelope.expected_version is what Runtime checks.
        
        if expected_version is not None and existing["entity_version"] != expected_version:
             # This is checking ENTITY version mismatch
             return [self._error(envelope, "conflict", f"Entity Version mismatch. Expected {expected_version}, got {existing['entity_version']}.")]

        # Apply Update
        new_data = existing["data"].copy()
        new_data.update(payload.get("data", {}))
        
        updated_entity = {
            "id": obj_id,
            "entity_version": existing["entity_version"] + 1,
            "data": new_data,
            "last_idempotency_key": key
        }
        # self._state[obj_id] = updated_entity <-- REMOVED MUTATION
        
        return [self._event(envelope, "updated", updated_entity)]

    def _handle_delete(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        obj_id = envelope.payload.get("id")
        # key = envelope.idempotency_key # Unused for delete decision usually
        
        if not obj_id:
             return [self._error(envelope, "validation_error", "Missing 'id' in payload.")]

        # If not exists, it's already deleted (idempotent), but maybe we want to return "not found" or "deleted"?
        # Usually idempotent delete returns success.
        
        # self._state check?
        # If we strictly want to emit "deleted" only if it existed:
        if obj_id not in self._state:
             # Already gone. 
             # Should we emit "deleted" again? Or nothing?
             # If we emit nothing, the caller might think it failed if they expect an event.
             # Let's emit "deleted" to confirm.
             pass

        # del self._state[obj_id] <-- REMOVED MUTATION
        
        return [self._event(envelope, "deleted", {"id": obj_id})]

    def _handle_get(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        obj_id = envelope.payload.get("id")
        if not obj_id:
             return [self._error(envelope, "validation_error", "Missing 'id' in payload.")]
             
        existing = self._state.get(obj_id)
        if not existing:
             return [self._error(envelope, "not_found", f"Entity {obj_id} not found.")]
             
        return [self._event(envelope, "found", existing)]

    def _handle_list(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        # Deterministic sort by ID
        items = sorted(self._state.values(), key=lambda x: x["id"])
        
        # Todo: Pagination
        limit = envelope.payload.get("limit", 100)
        offset = envelope.payload.get("offset", 0)
        
        paged_items = items[offset : offset + limit]
        
        return [self._event(envelope, "list", {
            "items": paged_items,
            "total": len(items)
        })]

    # --- Helpers ---

    def _event(self, trigger: EventEnvelope, suffix: str, payload: Dict[str, Any]) -> EventEnvelope:
        """Helper to create a response event."""
        # Use simple ID generation for now (in real system, might be deterministic hash)
        # Note: We can't easily access 'now' here unless passed down or injected. 
        # For this adapter, we might just reuse the trigger timestamp + epsilon or 0 if pure logic.
        # But EventEnvelope requires 'ts'.
        # Let's rely on the engine or use trigger.ts
        
        return EventEnvelope(
            id=f"{trigger.id}_{suffix}", # Deterministic-ish ID derived from trigger
            ts=trigger.ts, # Echo timestamp (logical time)
            type=f"evt.{self.object_name.lower()}.{suffix}",
            trace_id=trigger.trace_id,
            span_id=trigger.span_id,
            tenant=trigger.tenant,
            workspace=trigger.workspace,
            actor=trigger.actor,
            payload=payload,
            idempotency_key=trigger.idempotency_key, # Link back
            source={"agent": f"{self.object_name}Manager", "adapter": "GenericCRUD"},
            security_context=trigger.security_context
        )

    def _error(self, trigger: EventEnvelope, code: str, message: str) -> EventEnvelope:
        return EventEnvelope(
            id=f"{trigger.id}_error",
            ts=trigger.ts,
            type="evt.error",
            trace_id=trigger.trace_id,
            span_id=trigger.span_id,
            tenant=trigger.tenant,
            workspace=trigger.workspace,
            actor=trigger.actor,
            payload={"code": code, "message": message, "context": {"command": trigger.type}},
            idempotency_key=trigger.idempotency_key,
            source={"agent": f"{self.object_name}Manager", "adapter": "GenericCRUD"},
            security_context=trigger.security_context
        )
