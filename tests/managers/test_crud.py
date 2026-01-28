import pytest
import time
from rhizon_runtime.core.models import EventEnvelope
from rhizon_runtime.managers.crud import GenericCRUDManagerAdapter

def make_envelope(type: str, payload: dict, key: str = "key1", id: str = "evt1") -> EventEnvelope:
    return EventEnvelope(
        id=id,
        ts=int(time.time() * 1000),
        type=type,
        schema_version="1.0",
        trace_id="trace1",
        span_id="span1",
        tenant="t1",
        workspace="w1",
        actor={"id": "user1", "role": "admin"},
        payload=payload,
        idempotency_key=key,
        source={"agent": "test", "adapter": "pytest"},
        security_context={"principal_id": "user1", "principal_type": "user"}
    )

class TestGenericCRUDManager:
    
    @pytest.fixture
    def manager(self):
        return GenericCRUDManagerAdapter("User")

    def _process_command(self, manager, cmd):
        """Helper to process command and apply resulting events to state."""
        events = manager.receive(cmd)
        for evt in events:
            manager.apply(evt)
        return events

    def test_create_success(self, manager):
        cmd = make_envelope("cmd.user.create", {"id": "u1", "data": {"name": "Alice"}})
        events = self._process_command(manager, cmd)
        
        assert len(events) == 1
        evt = events[0]
        assert evt.type == "evt.user.created"
        assert evt.payload["id"] == "u1"
        assert evt.payload["entity_version"] == 1
        assert evt.payload["data"]["name"] == "Alice"

    def test_create_conflict(self, manager):
        # Create first
        cmd1 = make_envelope("cmd.user.create", {"id": "u1", "data": {"name": "Alice"}}, key="k1")
        self._process_command(manager, cmd1)
        
        # Create duplicate ID, different key
        cmd2 = make_envelope("cmd.user.create", {"id": "u1", "data": {"name": "Bob"}}, key="k2")
        events = self._process_command(manager, cmd2)
        
        assert len(events) == 1
        assert events[0].type == "evt.error"
        assert events[0].payload["code"] == "conflict"

    def test_create_idempotent(self, manager):
        # Create first
        cmd1 = make_envelope("cmd.user.create", {"id": "u1", "data": {"name": "Alice"}}, key="k1")
        events1 = self._process_command(manager, cmd1)
        
        # Replay same command
        cmd2 = make_envelope("cmd.user.create", {"id": "u1", "data": {"name": "Alice"}}, key="k1")
        events2 = self._process_command(manager, cmd2)
        
        assert len(events2) == 1
        assert events2[0].type == "evt.user.created"
        # Ideally should be same content
        assert events2[0].payload == events1[0].payload

    def test_update_success(self, manager):
        self._process_command(manager, make_envelope("cmd.user.create", {"id": "u1", "data": {"name": "Alice"}}, key="k1"))
        
        cmd = make_envelope("cmd.user.update", {"id": "u1", "data": {"name": "Alice Cooper"}}, key="k2")
        events = self._process_command(manager, cmd)
        
        assert len(events) == 1
        assert events[0].type == "evt.user.updated"
        assert events[0].payload["entity_version"] == 2
        assert events[0].payload["data"]["name"] == "Alice Cooper"

    def test_update_not_found(self, manager):
        cmd = make_envelope("cmd.user.update", {"id": "u99", "data": {}}, key="k_missing")
        events = self._process_command(manager, cmd)
        
        assert len(events) == 1
        assert events[0].type == "evt.error"
        assert events[0].payload["code"] == "not_found"

    def test_update_optimistic_lock(self, manager):
        self._process_command(manager, make_envelope("cmd.user.create", {"id": "u1", "data": {"name": "Alice"}}, key="k1"))
        
        # Expect version 99 (mismatch)
        cmd = make_envelope("cmd.user.update", {"id": "u1", "data": {"name": "X"}, "expected_version": 99}, key="k2")
        events = self._process_command(manager, cmd)
        
        assert len(events) == 1
        assert events[0].type == "evt.error"
        assert events[0].payload["code"] == "conflict"

    def test_delete_success(self, manager):
        self._process_command(manager, make_envelope("cmd.user.create", {"id": "u1", "data": {"name": "Alice"}}, key="k1"))
        
        cmd = make_envelope("cmd.user.delete", {"id": "u1"}, key="k2")
        events = self._process_command(manager, cmd)
        
        assert len(events) == 1
        assert events[0].type == "evt.user.deleted"
        assert events[0].payload["id"] == "u1"
        
        # Verify gone
        get_cmd = make_envelope("cmd.user.get", {"id": "u1"}, key="k3")
        events_get = self._process_command(manager, get_cmd)
        assert events_get[0].type == "evt.error"
        assert events_get[0].payload["code"] == "not_found"

    def test_list_deterministic(self, manager):
        # Insert unordered
        self._process_command(manager, make_envelope("cmd.user.create", {"id": "B", "data": {}}, key="k1"))
        self._process_command(manager, make_envelope("cmd.user.create", {"id": "A", "data": {}}, key="k2"))
        self._process_command(manager, make_envelope("cmd.user.create", {"id": "C", "data": {}}, key="k3"))
        
        cmd = make_envelope("cmd.user.list", {}, key="k4")
        events = self._process_command(manager, cmd)
        
        assert len(events) == 1
        items = events[0].payload["items"]
        assert len(items) == 3
        # Check sort order A, B, C
        assert items[0]["id"] == "A"
        assert items[1]["id"] == "B"
        assert items[2]["id"] == "C"
