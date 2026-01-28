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

# --- Mock Agent ---
class EchoAdapter(AgentRuntimeAdapter):
    def __init__(self):
        self.processed = []

    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        return [
            EventEnvelope(
                id=f"evt-{envelope.id}",
                ts=envelope.ts,
                type="evt.echoed",
                payload=envelope.payload,
                idempotency_key=f"idemp-{envelope.id}",
                source={"agent": "echo", "adapter": "test"},
                tenant=envelope.tenant,
                workspace=envelope.workspace,
                actor=envelope.actor,
                trace_id=envelope.trace_id,
                span_id=envelope.span_id,
                security_context=envelope.security_context
            )
        ]

    def apply(self, envelope: EventEnvelope) -> None:
        self.processed.append(envelope)

    def tick(self, now: int) -> List[EventEnvelope]:
        return []

    def get_state(self) -> AgentState:
        return AgentState(version=1, data={}, updated_at=0)
    
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
async def test_strict_tenant_isolation(tmp_path):
    """
    Verify that an engine scoped to Tenant A rejects events from Tenant B.
    """
    store = SQLiteEventStore(str(tmp_path / "events_sec.db"))
    adapter = EchoAdapter()
    bus = InMemoryBus()
    
    # Engine scoped to Tenant A / Workspace A
    engine = RuntimeEngine(
        "echo", adapter, bus, store=store, 
        tenant="tenant-A", workspace="workspace-A"
    )
    
    # 1. Valid Request (Tenant A)
    cmd_valid = EventEnvelope(
        id="cmd-valid", ts=1000, type="cmd.test",
        payload={"msg": "hello"},
        idempotency_key="idemp-1",
        source={"agent": "test", "adapter": "manual"},
        tenant="tenant-A", 
        workspace="workspace-A", 
        actor={"id": "user", "role": "admin"},
        trace_id="t1", span_id="s1",
        security_context={"principal_id": "u1", "principal_type": "user"}
    )
    
    res = await engine.process_event(cmd_valid)
    assert len(res) == 1
    assert res[0].type == "evt.echoed"
    
    # 2. Invalid Tenant (Tenant B)
    cmd_invalid_tenant = EventEnvelope(
        id="cmd-invalid-tenant", ts=1001, type="cmd.test",
        payload={"msg": "intruder"},
        idempotency_key="idemp-2",
        source={"agent": "test", "adapter": "manual"},
        tenant="tenant-B", # WRONG
        workspace="workspace-A", 
        actor={"id": "user", "role": "admin"},
        trace_id="t2", span_id="s2",
        security_context={"principal_id": "u2", "principal_type": "user"}
    )
    
    res_inv = await engine.process_event(cmd_invalid_tenant)
    assert len(res_inv) == 1
    assert res_inv[0].type == "evt.security.violation"
    assert res_inv[0].payload["attempted_tenant"] == "tenant-B"
    assert res_inv[0].payload["engine_tenant"] == "tenant-A"
    
    # Verify persistence of violation
    stored = store.replay()
    # Should have: 1 echoed event, 1 violation event. 
    # The echo adapter applies the echoed event. The engine persists the violation.
    # Note: store.replay() by default filters by engine scope? 
    # Wait, engine.recover() calls store.replay(filters=...).
    # store.replay() called directly returns everything in DB unless filtered.
    assert len(stored) >= 2
    violations = [e for e in stored if e.type == "evt.security.violation"]
    assert len(violations) == 1

@pytest.mark.asyncio
async def test_strict_workspace_isolation(tmp_path):
    """
    Verify that an engine scoped to Workspace A rejects events from Workspace B (same tenant).
    """
    store = SQLiteEventStore(str(tmp_path / "events_ws.db"))
    adapter = EchoAdapter()
    bus = InMemoryBus()
    
    engine = RuntimeEngine(
        "echo", adapter, bus, store=store, 
        tenant="tenant-A", workspace="workspace-A"
    )
    
    # Invalid Workspace
    cmd_invalid_ws = EventEnvelope(
        id="cmd-invalid-ws", ts=1000, type="cmd.test",
        payload={"msg": "wrong room"},
        idempotency_key="idemp-3",
        source={"agent": "test", "adapter": "manual"},
        tenant="tenant-A", 
        workspace="workspace-B", # WRONG
        actor={"id": "user", "role": "admin"},
        trace_id="t3", span_id="s3",
        security_context={"principal_id": "u3", "principal_type": "user"}
    )
    
    res = await engine.process_event(cmd_invalid_ws)
    assert len(res) == 1
    assert res[0].type == "evt.security.violation"
    assert res[0].payload["attempted_workspace"] == "workspace-B"
    
@pytest.mark.asyncio
async def test_store_scoping_on_replay(tmp_path):
    """
    Verify that recovering an engine only loads events for its scope.
    """
    store = SQLiteEventStore(str(tmp_path / "events_mix.db"))
    
    # Insert mixed events directly into store
    e1 = EventEnvelope(
        id="evt-1", ts=100, type="evt.test", payload={}, idempotency_key="k1",
        source={"agent": "a", "adapter": "b"}, tenant="T1", workspace="W1",
        actor={"id": "u", "role": "r"}, trace_id="t", span_id="s",
        security_context={"principal_id": "p", "principal_type": "system"}
    )
    e2 = EventEnvelope(
        id="evt-2", ts=101, type="evt.test", payload={}, idempotency_key="k2",
        source={"agent": "a", "adapter": "b"}, tenant="T1", workspace="W2", # Different WS
        actor={"id": "u", "role": "r"}, trace_id="t", span_id="s",
        security_context={"principal_id": "p", "principal_type": "system"}
    )
    e3 = EventEnvelope(
        id="evt-3", ts=102, type="evt.test", payload={}, idempotency_key="k3",
        source={"agent": "a", "adapter": "b"}, tenant="T2", workspace="W1", # Different Tenant
        actor={"id": "u", "role": "r"}, trace_id="t", span_id="s",
        security_context={"principal_id": "p", "principal_type": "system"}
    )
    
    store.append_batch([e1, e2, e3])
    
    # Setup Engine for T1/W1
    adapter = EchoAdapter()
    bus = InMemoryBus()
    engine = RuntimeEngine(
        "echo", adapter, bus, store=store, 
        tenant="T1", workspace="W1"
    )
    
    # Recover
    engine.recover()
    
    # Adapter should have only processed e1
    assert len(adapter.processed) == 1
    assert adapter.processed[0].id == "evt-1"
    
    store.close()

@pytest.mark.asyncio
async def test_security_context_propagation(tmp_path):
    """
    Verify that security context is propagated to output events.
    """
    store = SQLiteEventStore(str(tmp_path / "events_ctx.db"))
    adapter = EchoAdapter()
    bus = InMemoryBus()
    engine = RuntimeEngine("echo", adapter, bus, store=store, tenant="T1", workspace="W1")
    
    ctx = {"principal_id": "user-007", "principal_type": "user"}
    
    cmd = EventEnvelope(
        id="cmd-sec", ts=1000, type="cmd.test",
        payload={}, idempotency_key="k-sec",
        source={"agent": "test", "adapter": "manual"},
        tenant="T1", workspace="W1",
        actor={"id": "u", "role": "r"}, trace_id="t", span_id="s",
        security_context=ctx
    )
    
    res = await engine.process_event(cmd)
    
    assert res[0].security_context == ctx
    # Also check stored event
    stored = store.get_by_idempotency_key("idemp-cmd-sec")
    # Wait, the engine returns the echoed event, which has a NEW idempotency key in EchoAdapter
    # EchoAdapter: idempotency_key=f"idemp-{envelope.id}" -> "idemp-cmd-sec"
    
    assert stored[0].security_context == ctx

