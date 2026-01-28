import sys
import pytest
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any

# Mock 'maf' library before importing the adapter
mock_maf = MagicMock()
sys.modules["maf"] = mock_maf

from rhizon_runtime.core.models import EventEnvelope
from rhizon_runtime.adapters.maf import MAFAdapter
from rhizon_runtime.core.engine import RuntimeEngine
from rhizon_runtime.core.bus import InMemoryBus
from rhizon_runtime.persistence.sqlite import SQLiteEventStore

# Mock MAF Agent
class MockMAFAgent:
    def __init__(self, name="test"):
        self.name = name
        self.state = {"count": 0}
        
    def process(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Simple deterministic logic: echo payload + type
        cmd_type = payload.get("type", "unknown")
        
        if cmd_type == "increment":
            # Pure decision: emit 'incremented'
            return [{"type": "evt.maf.incremented", "payload": {"amount": payload.get("amount", 1)}}]
        return []

    def apply(self, payload: Dict[str, Any]):
        # State mutation
        if "amount" in payload:
            self.state["count"] += payload["amount"]
            
    def get_state(self):
        return self.state

@pytest.fixture
def mock_agent():
    return MockMAFAgent()

@pytest.fixture
def adapter(mock_agent):
    # MAFAdapter requires a MAFAgent instance
    return MAFAdapter(mock_agent)

def test_maf_adapter_contract(adapter):
    """
    Verify MAFAdapter implements ARA receive() correctly.
    Pure decision: Input Envelope -> Output Envelopes.
    """
    # 1. Create Input Envelope
    envelope = EventEnvelope(
        id="evt_1",
        ts=1000,
        type="cmd.maf.increment",
        trace_id="t1",
        span_id="s1",
        tenant="default",
        workspace="default",
        actor={"id": "user", "role": "tester"},
        payload={"type": "increment", "amount": 5},
        idempotency_key="key_1",
        source={"agent": "test", "adapter": "pytest"},
        security_context={"principal_id": "user", "principal_type": "user"}
    )
    
    # 2. Call receive
    output_events = adapter.receive(envelope)
    
    # 3. Verify Output
    assert len(output_events) == 1
    evt = output_events[0]
    assert evt.type == "evt.maf.incremented"
    assert evt.payload["amount"] == 5
    # Verify deterministic ID derivation
    assert evt.id == "evt_1_0"
    # Verify linkage
    assert evt.ts == 1000
    assert evt.trace_id == "t1"
    
    # 4. Verify No Side Effect on Agent State (Pure Decision)
    # The MockMAFAgent.process does NOT mutate state.
    assert adapter.agent.state["count"] == 0

def test_maf_adapter_apply(adapter):
    """
    Verify MAFAdapter implements ARA apply() correctly.
    State mutation.
    """
    # 1. Create Event to Apply
    evt = EventEnvelope(
        id="evt_res_1",
        ts=1000,
        type="evt.maf.incremented",
        trace_id="t1",
        span_id="s1",
        tenant="default",
        workspace="default",
        actor={"id": "user", "role": "tester"},
        payload={"amount": 5},
        idempotency_key="key_1",
        source={"agent": "maf", "adapter": "maf"},
        security_context={"principal_id": "user", "principal_type": "user"}
    )
    
    # 2. Call apply
    adapter.apply(evt)
    
    # 3. Verify State Mutation
    assert adapter.agent.state["count"] == 5

@pytest.mark.asyncio
async def test_replay_with_maf_adapter(tmp_path):
    """
    Verify Crash/Restart Replay with MAFAdapter via RuntimeEngine.
    """
    db_path = tmp_path / "events.db"
    store = SQLiteEventStore(str(db_path))
    bus = InMemoryBus()
    
    # --- RUN 1 ---
    agent1 = MockMAFAgent("agent1")
    adapter1 = MAFAdapter(agent1)
    # Fix: Align Engine scope with Command scope (d/w)
    engine1 = RuntimeEngine("maf_engine", adapter1, bus, store=store, deterministic=True, tenant="d", workspace="w")
    
    # Command
    cmd = EventEnvelope(
        id="cmd_1",
        ts=1000,
        type="cmd.maf.increment",
        trace_id="t1",
        span_id="s1",
        tenant="d",
        workspace="w",
        actor={"id": "u", "role": "tester"},
        payload={"type": "increment", "amount": 10},
        idempotency_key="idem_1",
        source={"agent": "test", "adapter": "pytest"},
        security_context={"principal_id": "user", "principal_type": "user"}
    )
    
    # Process
    await engine1.process_event(cmd)
    
    # Verify State
    assert agent1.state["count"] == 10
    state_hash_1 = engine1.get_state_hash()
    
    # Close Store
    store.close()
    
    # --- RUN 2 (Crash/Restart) ---
    store2 = SQLiteEventStore(str(db_path)) # Reopen same DB
    agent2 = MockMAFAgent("agent1") # Fresh agent, state=0
    adapter2 = MAFAdapter(agent2)
    # Fix: Align Engine scope with Command scope (d/w)
    engine2 = RuntimeEngine("maf_engine", adapter2, bus, store=store2, deterministic=True, tenant="d", workspace="w")
    
    # Verify initial state is 0
    assert agent2.state["count"] == 0
    
    # Recover
    engine2.recover()
    
    # Verify State Restored
    assert agent2.state["count"] == 10
    
    # Verify Hashes Match
    state_hash_2 = engine2.get_state_hash()
    assert state_hash_1 == state_hash_2
    
    store2.close()
