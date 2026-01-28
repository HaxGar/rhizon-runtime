import pytest
import time
from rhizon_runtime.adapters.lock_manager import LockManagerAdapter
from rhizon_runtime.core.models import EventEnvelope

@pytest.fixture
def lock_adapter():
    return LockManagerAdapter()

def create_cmd(type: str, payload: dict, ts: int = 1000) -> EventEnvelope:
    return EventEnvelope(
        id="cmd-1",
        ts=ts,
        type=type,
        payload=payload,
        idempotency_key="idemp-1",
        source={"agent": "test", "adapter": "manual"},
        tenant="default",
        workspace="test",
        actor={"id": "user", "role": "admin"},
        trace_id="t1",
        span_id="s1",
        security_context={"principal_id": "user-1", "principal_type": "user"}
    )

def test_acquire_success(lock_adapter):
    cmd = create_cmd("cmd.lock.acquire", {"resource_id": "res1", "owner_id": "agent1", "ttl_ms": 1000})
    events = lock_adapter.receive(cmd)
    
    assert len(events) == 1
    assert events[0].type == "evt.lock.acquired"
    assert events[0].payload["resource_id"] == "res1"
    assert events[0].payload["owner_id"] == "agent1"
    
    lock_adapter.apply(events[0])
    state = lock_adapter.get_state()
    assert "res1" in state.data["locks"]
    assert state.data["locks"]["res1"]["owner_id"] == "agent1"

def test_acquire_conflict(lock_adapter):
    # First acquire
    cmd1 = create_cmd("cmd.lock.acquire", {"resource_id": "res1", "owner_id": "agent1"}, ts=1000)
    evt1 = lock_adapter.receive(cmd1)[0]
    lock_adapter.apply(evt1)
    
    # Second acquire by different owner
    cmd2 = create_cmd("cmd.lock.acquire", {"resource_id": "res1", "owner_id": "agent2"}, ts=1001)
    events = lock_adapter.receive(cmd2)
    
    assert len(events) == 1
    assert events[0].type == "evt.lock.denied"
    assert events[0].payload["current_owner"] == "agent1"

def test_acquire_idempotent(lock_adapter):
    # First acquire
    cmd1 = create_cmd("cmd.lock.acquire", {"resource_id": "res1", "owner_id": "agent1"}, ts=1000)
    evt1 = lock_adapter.receive(cmd1)[0]
    lock_adapter.apply(evt1)
    
    # Same owner re-acquires (Refresh/Idempotent)
    cmd2 = create_cmd("cmd.lock.acquire", {"resource_id": "res1", "owner_id": "agent1"}, ts=1001)
    events = lock_adapter.receive(cmd2)
    
    assert len(events) == 1
    assert events[0].type == "evt.lock.acquired"
    assert events[0].payload["owner_id"] == "agent1"

def test_release_success(lock_adapter):
    # Acquire
    cmd1 = create_cmd("cmd.lock.acquire", {"resource_id": "res1", "owner_id": "agent1"}, ts=1000)
    lock_adapter.apply(lock_adapter.receive(cmd1)[0])
    
    # Release
    cmd2 = create_cmd("cmd.lock.release", {"resource_id": "res1", "owner_id": "agent1"}, ts=1001)
    events = lock_adapter.receive(cmd2)
    
    assert len(events) == 1
    assert events[0].type == "evt.lock.released"
    
    lock_adapter.apply(events[0])
    state = lock_adapter.get_state()
    assert "res1" not in state.data["locks"]

def test_release_denied_wrong_owner(lock_adapter):
    # Acquire
    cmd1 = create_cmd("cmd.lock.acquire", {"resource_id": "res1", "owner_id": "agent1"}, ts=1000)
    lock_adapter.apply(lock_adapter.receive(cmd1)[0])
    
    # Release by agent2
    cmd2 = create_cmd("cmd.lock.release", {"resource_id": "res1", "owner_id": "agent2"}, ts=1001)
    events = lock_adapter.receive(cmd2)
    
    assert len(events) == 1
    assert events[0].type == "evt.lock.denied"

def test_expiration_tick(lock_adapter):
    # Acquire at ts=1000 with ttl=1000 -> expires at 2000
    cmd1 = create_cmd("cmd.lock.acquire", {"resource_id": "res1", "owner_id": "agent1", "ttl_ms": 1000}, ts=1000)
    lock_adapter.apply(lock_adapter.receive(cmd1)[0])
    
    # Tick at 1500 (Not expired)
    evts = lock_adapter.tick(1500)
    assert len(evts) == 0
    
    # Tick at 2001 (Expired)
    evts = lock_adapter.tick(2001)
    assert len(evts) == 1
    assert evts[0].type == "evt.lock.expired"
    assert evts[0].payload["resource_id"] == "res1"
    
    lock_adapter.apply(evts[0])
    state = lock_adapter.get_state()
    assert "res1" not in state.data["locks"]
