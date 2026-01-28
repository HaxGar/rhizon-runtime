import pytest
import asyncio
import hashlib
from typing import List, Any
from pydantic import ValidationError

from rhizon_runtime.core.models import EventEnvelope
from rhizon_runtime.core.interfaces import AgentRuntimeAdapter, AgentState, HealthStatus
from rhizon_runtime.core.bus import InMemoryBus
from rhizon_runtime.core.engine import RuntimeEngine

# --- 1. Vanilla Adapter for Testing ---
class VanillaCounterAdapter:
    """
    A simple reference implementation of ARA.
    State: {'count': int}
    Logic: Increment count on 'cmd.increment'. Emit 'evt.incremented'.
    """
    def __init__(self):
        self.state = {"count": 0}
        self.last_id = None
        self.updated_at = 0

    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        if envelope.type == "cmd.increment":
            # Pure decision: Do NOT mutate state here.
            # Just return the event that, when applied, will mutate state.
            
            new_count = self.state["count"] + 1
            
            # Return outgoing event
            return [EventEnvelope(
                id=f"evt-{envelope.id}",
                ts=envelope.ts, 
                type="evt.incremented",
                trace_id=envelope.trace_id,
                span_id=envelope.span_id,
                tenant=envelope.tenant,
                workspace=envelope.workspace,
                actor=envelope.actor,
                payload={"new_count": new_count},
                idempotency_key=f"out-{envelope.idempotency_key}",
                source={"agent": "counter", "adapter": "vanilla"},
                security_context=envelope.security_context
            )]
        return []

    def apply(self, envelope: EventEnvelope) -> None:
        """
        Apply committed event to state.
        """
        if envelope.type == "evt.incremented":
            self.state["count"] = envelope.payload["new_count"]
            # self.last_id = envelope.id # ID of the event applied? Or trigger? 
            # Usually we track last *processed* command ID for idempotency, but here we just track state.
            
    def tick(self, now: int) -> List[EventEnvelope]:
        self.updated_at = now
        return []

    def get_state(self) -> AgentState:
        return AgentState(
            version=1,
            data=self.state,
            last_processed_event_id=self.last_id,
            updated_at=self.updated_at
        )

    def health(self) -> HealthStatus:
        return HealthStatus.READY

# --- 2. Tests ---

def test_no_framework_dependency_in_runtime_core():
    """Verify strictly no imports of external agent frameworks in core (isolated)."""
    import subprocess
    import sys
    
    code = """
import sys
# Ensure src is in path
import os
sys.path.insert(0, os.path.abspath('src'))

try:
    import rhizon_runtime.core.engine
    import rhizon_runtime.core.models
    import rhizon_runtime.core.bus
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

banned = ["langchain", "autogen", "crewai", "maf"]
loaded = [m for m in sys.modules if any(m == b or m.startswith(b + ".") for b in banned)]

if loaded:
    print(f"Banned modules loaded: {loaded}")
    sys.exit(1)
print("Clean")
"""
    # Run in subprocess
    # We assume CWD is meshforge-runtime root (where pytest is run)
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, f"Core Purity Check Failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"

    # Check file contents (naive scan) as secondary check
    from pathlib import Path
    import rhizon_runtime.core.engine
    
    banned = ["langchain", "autogen", "crewai", "maf"]
    core_dir = Path(rhizon_runtime.core.engine.__file__).parent
    for py_file in core_dir.glob("*.py"):
        content = py_file.read_text()
        for ban in banned:
            assert f"import {ban}" not in content, f"Import of {ban} found in {py_file}"
            assert f"from {ban}" not in content, f"From import of {ban} found in {py_file}"

def test_event_envelope_validation():
    """Verify V1 constraints."""
    # Missing mandatory field
    with pytest.raises(ValidationError):
        EventEnvelope(
            id="1", ts=100, type="test",
            # missing trace_id etc
        )
        
    # Valid envelope
    env = EventEnvelope(
        id="1", ts=100, type="cmd.test", schema_version="1.0",
        trace_id="t1", span_id="s1", tenant="def", workspace="ws1",
        actor={"id": "u1", "role": "user"},
        payload={"foo": "bar"},
        idempotency_key="ik1",
        source={"agent": "a1", "adapter": "ad1"},
        security_context={"principal_id": "u1", "principal_type": "user"}
    )
    assert env.id == "1"

@pytest.mark.asyncio
async def test_adapter_contract_compliance():
    """Verify ARA works with RuntimeEngine."""
    adapter = VanillaCounterAdapter()
    bus = InMemoryBus()
    # Align Engine scope with Envelope (t/w)
    engine = RuntimeEngine("agent-1", adapter, bus, deterministic=True, tenant="t", workspace="w")
    
    env = EventEnvelope(
        id="e1", ts=1234567890000, type="cmd.increment",
        trace_id="t1", span_id="s1", tenant="t", workspace="w",
        actor={"id": "u", "role": "r"},
        payload={},
        idempotency_key="key-1",
        source={"agent": "src", "adapter": "test"},
        security_context={"principal_id": "u", "principal_type": "user"}
    )
    
    await engine.process_event(env)
    
    state = adapter.get_state()
    assert state.data["count"] == 1
    assert len(bus.published_events) == 1
    assert bus.published_events[0].type == "evt.incremented"

@pytest.mark.asyncio
async def test_replay_idempotency():
    """Verify idempotency key prevents double processing."""
    adapter = VanillaCounterAdapter()
    bus = InMemoryBus()
    # Align Engine scope with Envelope (t/w)
    engine = RuntimeEngine("agent-1", adapter, bus, deterministic=True, tenant="t", workspace="w")
    
    env = EventEnvelope(
        id="e1", ts=1234567890000, type="cmd.increment",
        trace_id="t1", span_id="s1", tenant="t", workspace="w",
        actor={"id": "u", "role": "r"},
        payload={},
        idempotency_key="unique-key-1", # Same key
        source={"agent": "src", "adapter": "test"},
        security_context={"principal_id": "u", "principal_type": "user"}
    )
    
    # First process
    await engine.process_event(env)
    assert adapter.get_state().data["count"] == 1
    assert len(bus.published_events) == 1
    
    # Second process (Duplicate)
    await engine.process_event(env)
    assert adapter.get_state().data["count"] == 1 # Should NOT increment
    assert len(bus.published_events) == 1 # Should NOT publish new event

@pytest.mark.asyncio
async def test_deterministic_hash_runtime():
    """Verify bit-for-bit stability across runs."""
    
    async def run_sequence():
        adapter = VanillaCounterAdapter()
        bus = InMemoryBus()
        # Align Engine scope with Envelope (t/w)
        engine = RuntimeEngine("agent-1", adapter, bus, deterministic=True, tenant="t", workspace="w")
        
        # Sequence of 3 increments
        for i in range(3):
            env = EventEnvelope(
                id=f"e{i}", ts=1234567890000, type="cmd.increment",
                trace_id="t1", span_id="s1", tenant="t", workspace="w",
                actor={"id": "u", "role": "r"},
                payload={},
                idempotency_key=f"key-{i}",
                source={"agent": "src", "adapter": "test"},
                security_context={"principal_id": "u", "principal_type": "user"}
            )
            await engine.process_event(env)
            
        return engine.get_state_hash()

    hash1 = await run_sequence()
    hash2 = await run_sequence()
    
    print(f"Hash1: {hash1}")
    print(f"Hash2: {hash2}")
    
    assert hash1 == hash2
    assert len(hash1) == 64 # SHA256 length
