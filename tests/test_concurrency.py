import pytest
import asyncio
import logging
from typing import List, Dict, Any
from rhizon_runtime.core.engine import RuntimeEngine
from rhizon_runtime.core.models import EventEnvelope
from rhizon_runtime.core.interfaces import AgentRuntimeAdapter, AgentState, HealthStatus
from rhizon_runtime.persistence.sqlite import SQLiteEventStore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Mock Agent with Versioning ---

class VersionedKVAdapter(AgentRuntimeAdapter):
    def __init__(self):
        self.store = {} # id -> {value, entity_version}
        self.processed_ids = []

    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        if envelope.type == "cmd.kv.update":
            return [
                EventEnvelope(
                    id=f"evt-upd-{envelope.id}",
                    ts=envelope.ts,
                    type="evt.kv.updated",
                    payload={"id": envelope.payload["id"], "value": envelope.payload["value"]},
                    idempotency_key=f"idemp-evt-{envelope.id}",
                    source={"agent": "kv", "adapter": "test"},
                    tenant=envelope.tenant,
                    workspace=envelope.workspace,
                    actor=envelope.actor,
                    trace_id=envelope.trace_id,
                    span_id=f"span-upd-{envelope.span_id}",
                    entity_id=envelope.payload["id"],
                    security_context=envelope.security_context
                )
            ]
        return []

    def apply(self, envelope: EventEnvelope) -> None:
        if envelope.type == "evt.kv.updated":
            obj_id = envelope.payload["id"]
            if obj_id not in self.store:
                self.store[obj_id] = {"entity_version": 0, "value": 0}
            
            self.store[obj_id]["entity_version"] += 1
            self.store[obj_id]["value"] = envelope.payload["value"]
            self.processed_ids.append(envelope.id)

    def tick(self, now: int) -> List[EventEnvelope]:
        return []

    def get_state(self) -> AgentState:
        entity_versions = {k: v["entity_version"] for k, v in self.store.items()}
        # Global version is just a sum or counter, not used for concurrency checks anymore
        return AgentState(version=len(self.processed_ids), entity_versions=entity_versions, data=self.store, updated_at=0)
    
    def health(self) -> HealthStatus:
        return HealthStatus.READY

# --- Mock Bus ---
class InMemoryBus:
    def __init__(self):
        self.published = []

    async def publish(self, events: List[EventEnvelope]) -> None:
        self.published.extend(events)

# --- Tests ---

@pytest.mark.asyncio
async def test_optimistic_concurrency_success(tmp_path):
    """
    Scenario:
    1. Entity A is at version 0 (doesn't exist).
    2. Command arrives with expected_version=0 for Entity A.
    3. Success. Entity A version becomes 1.
    """
    store = SQLiteEventStore(str(tmp_path / "events.db"))
    adapter = VersionedKVAdapter()
    bus = InMemoryBus()
    # Align Engine scope with Command scope (default/test)
    engine = RuntimeEngine("kv", adapter, bus, store=store, deterministic=True, tenant="default", workspace="test")
    
    # 1. Update Entity A (expected=0)
    cmd = EventEnvelope(
        id="cmd-1", ts=1000, type="cmd.kv.update",
        payload={"id": "A", "value": 10},
        idempotency_key="idemp-1",
        expected_version=0,
        entity_id="A", # Target Entity A
        source={"agent": "test", "adapter": "manual"},
        tenant="default", workspace="test", actor={"id": "user", "role": "admin"},
        trace_id="t1", span_id="s1",
        security_context={"principal_id": "user-1", "principal_type": "user"}
    )
    
    events = await engine.process_event(cmd)
    
    assert len(events) == 1
    assert events[0].type == "evt.kv.updated"
    assert adapter.store["A"]["entity_version"] == 1

    store.close()

@pytest.mark.asyncio
async def test_entity_concurrency_isolation(tmp_path):
    """
    Scenario:
    1. Entity A updated to v1.
    2. Entity B updated to v1.
    3. Verify that updating B didn't affect A's version check.
    """
    store = SQLiteEventStore(str(tmp_path / "events_iso.db"))
    adapter = VersionedKVAdapter()
    bus = InMemoryBus()
    engine = RuntimeEngine("kv", adapter, bus, store=store, deterministic=True, tenant="d", workspace="w")
    
    # Update A (v0 -> v1)
    await engine.process_event(EventEnvelope(
        id="cmd-a", ts=1000, type="cmd.kv.update", payload={"id": "A", "value": 1},
        idempotency_key="k1", expected_version=0, entity_id="A",
        source={"agent": "test", "adapter": "manual"}, tenant="d", workspace="w", 
        actor={"id": "user", "role": "admin"}, trace_id="t1", span_id="s1",
        security_context={"principal_id": "user-1", "principal_type": "user"}
    ))
    
    # Update B (v0 -> v1)
    await engine.process_event(EventEnvelope(
        id="cmd-b", ts=1001, type="cmd.kv.update", payload={"id": "B", "value": 1},
        idempotency_key="k2", expected_version=0, entity_id="B",
        source={"agent": "test", "adapter": "manual"}, tenant="d", workspace="w", 
        actor={"id": "user", "role": "admin"}, trace_id="t2", span_id="s2",
        security_context={"principal_id": "user-1", "principal_type": "user"}
    ))
    
    assert adapter.store["A"]["entity_version"] == 1
    assert adapter.store["B"]["entity_version"] == 1
    
    # Update A again (v1 -> v2) - Should succeed despite B's update
    res = await engine.process_event(EventEnvelope(
        id="cmd-a-2", ts=1002, type="cmd.kv.update", payload={"id": "A", "value": 2},
        idempotency_key="k3", expected_version=1, entity_id="A",
        source={"agent": "test", "adapter": "manual"}, tenant="d", workspace="w", 
        actor={"id": "user", "role": "admin"}, trace_id="t3", span_id="s3",
        security_context={"principal_id": "user-1", "principal_type": "user"}
    ))
    assert res[0].type == "evt.kv.updated"
    assert adapter.store["A"]["entity_version"] == 2

    store.close()

@pytest.mark.asyncio
async def test_optimistic_concurrency_conflict(tmp_path):
    """
    Scenario:
    1. Entity A is at version 0.
    2. Command arrives for Entity A with expected_version=99.
    3. Conflict.
    """
    store = SQLiteEventStore(str(tmp_path / "events_conflict.db"))
    adapter = VersionedKVAdapter()
    bus = InMemoryBus()
    engine = RuntimeEngine("kv", adapter, bus, store=store, deterministic=True, tenant="default", workspace="test")
    
    cmd = EventEnvelope(
        id="cmd-fail", ts=1000, type="cmd.kv.update",
        payload={"id": "A", "value": 99},
        idempotency_key="idemp-fail",
        expected_version=99,
        entity_id="A",
        source={"agent": "test", "adapter": "manual"},
        tenant="default", workspace="test", actor={"id": "user", "role": "admin"},
        trace_id="t1", span_id="s1",
        security_context={"principal_id": "user-1", "principal_type": "user"}
    )
    
    events = await engine.process_event(cmd)
    
    assert len(events) == 1
    conflict = events[0]
    assert "conflict" in conflict.type
    assert conflict.type == "evt.kv.conflict" # Stable subject check
    assert conflict.payload["entity_id"] == "A"
    assert conflict.payload["expected_version"] == 99
    assert conflict.payload["current_version"] == 0
    
    store.close()


@pytest.mark.asyncio
async def test_conflict_determinism_replay(tmp_path):
    """
    Scenario:
    1. Command fails with conflict.
    2. Command is re-sent (same idempotency key).
    3. Engine detects duplicate key.
    4. Engine returns ORIGINAL conflict event (even if state theoretically changed, though here it wouldn't have).
    """
    store = SQLiteEventStore(str(tmp_path / "events_replay.db"))
    adapter = VersionedKVAdapter()
    bus = InMemoryBus()
    engine = RuntimeEngine("kv", adapter, bus, store=store, deterministic=True, tenant="default", workspace="test")
    
    cmd = EventEnvelope(
        id="cmd-conflict", ts=1000, type="cmd.kv.update",
        payload={"id": "A", "value": 5},
        idempotency_key="idemp-conflict",
        expected_version=5, # Mismatch (0)
        entity_id="A",
        source={"agent": "test", "adapter": "manual"},
        tenant="default", workspace="test", actor={"id": "user", "role": "admin"},
        trace_id="t1", span_id="s1",
        security_context={"principal_id": "user-1", "principal_type": "user"}
    )
    
    # First attempt
    events1 = await engine.process_event(cmd)
    assert events1[0].type == "evt.kv.conflict"
    
    # Second attempt (Idempotency)
    events2 = await engine.process_event(cmd)
    assert len(events2) == 1
    assert events2[0].id == events1[0].id # Exactly same event ID
    
    # Verify Re-Publication logic (Engine re-publishes side-effects on duplicate)
    # Bus should have received it twice (once from first call, once from re-publish in idempotency block)
    assert len(bus.published) == 2
    assert bus.published[0].id == bus.published[1].id
    
    store.close()

@pytest.mark.asyncio
async def test_race_condition_simulation(tmp_path):
    """
    Scenario:
    Two commands targeting version 0 of Entity A arrive "simultaneously".
    One succeeds, one fails.
    """
    store = SQLiteEventStore(str(tmp_path / "events_race.db"))
    adapter = VersionedKVAdapter()
    bus = InMemoryBus()
    engine = RuntimeEngine("kv", adapter, bus, store=store, deterministic=True, tenant="default", workspace="test")
    
    cmd1 = EventEnvelope(
        id="cmd-race-1", ts=1000, type="cmd.kv.update", 
        payload={"id": "A", "value": 1},
        idempotency_key="idemp-race-1", expected_version=0, entity_id="A",
        source={"agent": "test", "adapter": "manual"}, tenant="default", workspace="test",
        actor={"id": "user", "role": "admin"}, trace_id="t1", span_id="s1",
        security_context={"principal_id": "user-1", "principal_type": "user"}
    )
    
    cmd2 = EventEnvelope(
        id="cmd-race-2", ts=1001, type="cmd.kv.update", 
        payload={"id": "A", "value": 2},
        idempotency_key="idemp-race-2", expected_version=0, entity_id="A", # Also expecting 0
        source={"agent": "test", "adapter": "manual"}, tenant="default", workspace="test",
        actor={"id": "user", "role": "admin"}, trace_id="t2", span_id="s2",
        security_context={"principal_id": "user-1", "principal_type": "user"}
    )
    
    # Process Cmd 1 (Success)
    res1 = await engine.process_event(cmd1)
    assert res1[0].type == "evt.kv.updated"
    assert adapter.store["A"]["entity_version"] == 1
    
    # Process Cmd 2 (Fail - Version is now 1)
    res2 = await engine.process_event(cmd2)
    assert res2[0].type == "evt.kv.conflict"
    assert res2[0].payload["expected_version"] == 0
    assert res2[0].payload["current_version"] == 1
    
    store.close()
