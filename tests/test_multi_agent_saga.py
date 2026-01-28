import pytest
import asyncio
from typing import List, Dict, Any
from rhizon_runtime.core.models import EventEnvelope
from rhizon_runtime.core.interfaces import AgentRuntimeAdapter, AgentState, HealthStatus
from rhizon_runtime.core.bus import InMemoryBus
from rhizon_runtime.core.engine import RuntimeEngine
from rhizon_runtime.core.router import InProcessRouter

# --- Mock Agents ---

class OrderAgent:
    def __init__(self):
        self.state = {"orders": {}}
        
    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        if envelope.type == "cmd.order.create":
            order_id = envelope.payload["id"]
            # Decision: Create Order AND Reserve Inventory
            
            # 1. Event: Order Created
            evt_created = EventEnvelope(
                id=f"evt-{envelope.id}-1",
                ts=envelope.ts,
                type="evt.order.created",
                trace_id=envelope.trace_id,
                span_id=envelope.span_id,
                tenant=envelope.tenant,
                workspace=envelope.workspace,
                actor=envelope.actor,
                payload={"id": order_id, "status": "PENDING"},
                idempotency_key=f"out-{envelope.idempotency_key}-1",
                source={"agent": "order", "adapter": "mock"},
                causation_id=envelope.id,
                correlation_id=envelope.correlation_id or envelope.id,
                security_context=envelope.security_context
            )
            
            # 2. Command: Reserve Inventory (Multi-Agent call)
            cmd_reserve = EventEnvelope(
                id=f"cmd-{envelope.id}-2",
                ts=envelope.ts,
                type="cmd.inventory.reserve", # Targeted at Inventory Agent
                trace_id=envelope.trace_id,
                span_id=envelope.span_id,
                tenant=envelope.tenant,
                workspace=envelope.workspace,
                actor=envelope.actor,
                payload={"order_id": order_id, "items": envelope.payload["items"]},
                idempotency_key=f"out-{envelope.idempotency_key}-2",
                source={"agent": "order", "adapter": "mock"},
                causation_id=envelope.id,
                correlation_id=envelope.correlation_id or envelope.id,
                reply_to="order", # Expect reply?
                security_context=envelope.security_context
            )
            
            return [evt_created, cmd_reserve]
            
        return []

    def apply(self, envelope: EventEnvelope) -> None:
        if envelope.type == "evt.order.created":
            self.state["orders"][envelope.payload["id"]] = envelope.payload
            
    def tick(self, now: int) -> List[EventEnvelope]:
        return []
        
    def get_state(self) -> AgentState:
        return AgentState(version=1, data=self.state, updated_at=0)
        
    def health(self) -> HealthStatus:
        return HealthStatus.READY

class InventoryAgent:
    def __init__(self):
        self.state = {"reservations": {}}
        
    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        if envelope.type == "cmd.inventory.reserve":
            order_id = envelope.payload["order_id"]
            
            # Decision: Reserve
            evt_reserved = EventEnvelope(
                id=f"evt-{envelope.id}",
                ts=envelope.ts,
                type="evt.inventory.reserved",
                trace_id=envelope.trace_id,
                span_id=envelope.span_id,
                tenant=envelope.tenant,
                workspace=envelope.workspace,
                actor=envelope.actor,
                payload={"order_id": order_id, "items": envelope.payload["items"]},
                idempotency_key=f"out-{envelope.idempotency_key}",
                source={"agent": "inventory", "adapter": "mock"},
                causation_id=envelope.id,
                correlation_id=envelope.correlation_id,
                security_context=envelope.security_context
            )
            return [evt_reserved]
            
        return []

    def apply(self, envelope: EventEnvelope) -> None:
        if envelope.type == "evt.inventory.reserved":
            self.state["reservations"][envelope.payload["order_id"]] = "RESERVED"

    def tick(self, now: int) -> List[EventEnvelope]:
        return []

    def get_state(self) -> AgentState:
        return AgentState(version=1, data=self.state, updated_at=0)

    def health(self) -> HealthStatus:
        return HealthStatus.READY

# --- Tests ---

@pytest.mark.asyncio
async def test_saga_flow_in_process():
    """
    Verify Order -> Inventory flow using InProcessRouter.
    """
    bus = InMemoryBus()
    router = InProcessRouter()
    
    # 1. Setup Agents
    order_agent = OrderAgent()
    inventory_agent = InventoryAgent()
    
    # 2. Setup Engines with Router
    order_engine = RuntimeEngine("order", order_agent, bus, router=router, deterministic=True, tenant="t1", workspace="w1")
    inventory_engine = RuntimeEngine("inventory", inventory_agent, bus, router=router, deterministic=True, tenant="t1", workspace="w1")
    
    # 3. Register Routes
    router.register("order", order_engine)
    router.register("inventory", inventory_engine)
    
    # 4. Trigger Saga
    trigger = EventEnvelope(
        id="trigger-1",
        ts=1000,
        type="cmd.order.create",
        trace_id="trace-1",
        span_id="span-1",
        tenant="t1",
        workspace="w1",
        actor={"id": "u1", "role": "user"},
        payload={"id": "ord-1", "items": ["item-A"]},
        idempotency_key="key-1",
        source={"agent": "test", "adapter": "pytest"},
        security_context={"principal_id": "u1", "principal_type": "user"}
    )
    
    # Send to Order Engine
    await order_engine.process_event(trigger)
    
    # 5. Verify Outcome
    
    # Check Order State
    assert "ord-1" in order_agent.state["orders"]
    assert order_agent.state["orders"]["ord-1"]["status"] == "PENDING"
    
    # Check Inventory State (Should have been called via Router)
    # Since InProcessRouter awaits the destination engine, this should be consistent immediately.
    assert "ord-1" in inventory_agent.state["reservations"]
    assert inventory_agent.state["reservations"]["ord-1"] == "RESERVED"
    
    # Check Bus Events
    # Expected: 
    # 1. evt.order.created
    # 2. evt.inventory.reserved
    assert len(bus.published_events) == 2
    
    evt1 = bus.published_events[0]
    assert evt1.type == "evt.order.created"
    assert evt1.causation_id == "trigger-1"
    
    evt2 = bus.published_events[1]
    assert evt2.type == "evt.inventory.reserved"
    # Its causation should be the command sent by OrderAgent
    # OrderAgent generated command id: f"cmd-{envelope.id}-2" -> "cmd-trigger-1-2"
    assert evt2.causation_id == "cmd-trigger-1-2"
    assert evt2.correlation_id == "trigger-1" # Propagated

@pytest.mark.asyncio
async def test_cross_agent_idempotency():
    """
    Verify that replaying the initial trigger does NOT re-trigger side effects on the second agent
    if the first agent handles idempotency correctly.
    """
    bus = InMemoryBus()
    router = InProcessRouter()
    
    order_agent = OrderAgent()
    inventory_agent = InventoryAgent()
    
    order_engine = RuntimeEngine("order", order_agent, bus, router=router, deterministic=True, tenant="t1", workspace="w1")
    inventory_engine = RuntimeEngine("inventory", inventory_agent, bus, router=router, deterministic=True, tenant="t1", workspace="w1")
    
    router.register("order", order_engine)
    router.register("inventory", inventory_engine)
    
    trigger = EventEnvelope(
        id="trigger-1",
        ts=1000,
        type="cmd.order.create",
        trace_id="trace-1",
        span_id="span-1",
        tenant="t1",
        workspace="w1",
        actor={"id": "u1", "role": "user"},
        payload={"id": "ord-1", "items": ["item-A"]},
        idempotency_key="key-1",
        source={"agent": "test", "adapter": "pytest"},
        security_context={"principal_id": "u1", "principal_type": "user"}
    )
    
    # First Run
    await order_engine.process_event(trigger)
    assert len(bus.published_events) == 2
    
    # Reset Bus to clearly see new events
    bus.clear()
    
    # Second Run (Duplicate Trigger)
    await order_engine.process_event(trigger)
    
    # Expectation:
    # Order Engine detects duplicate key-1 -> Returns []
    # No calls to OrderAgent.receive -> No outgoing commands
    # Inventory Engine is NOT called.
    
    assert len(bus.published_events) == 0

@pytest.mark.asyncio
async def test_multi_agent_determinism():
    """
    Verify bit-for-bit stability of multi-agent execution across runs.
    """
    async def run_sequence():
        bus = InMemoryBus()
        router = InProcessRouter()
        
        order_agent = OrderAgent()
        inventory_agent = InventoryAgent()
        
        order_engine = RuntimeEngine("order", order_agent, bus, router=router, deterministic=True, tenant="t1", workspace="w1")
        inventory_engine = RuntimeEngine("inventory", inventory_agent, bus, router=router, deterministic=True, tenant="t1", workspace="w1")
        
        router.register("order", order_engine)
        router.register("inventory", inventory_engine)
        
        # Trigger
        trigger = EventEnvelope(
            id="trigger-1",
            ts=1000,
            type="cmd.order.create",
            trace_id="trace-1",
            span_id="span-1",
            tenant="t1",
            workspace="w1",
            actor={"id": "u1", "role": "user"},
            payload={"id": "ord-1", "items": ["item-A"]},
            idempotency_key="key-1",
            source={"agent": "test", "adapter": "pytest"},
            security_context={"principal_id": "u1", "principal_type": "user"}
        )
        
        await order_engine.process_event(trigger)
        
        # Combine hashes
        hash_combined = order_engine.get_state_hash() + inventory_engine.get_state_hash()
        return hash_combined

    hash1 = await run_sequence()
    hash2 = await run_sequence()
    
    assert hash1 == hash2

