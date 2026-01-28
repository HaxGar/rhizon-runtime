import pytest
import asyncio
import subprocess
import os
import time
import json
import logging
from typing import List, Dict, Any
import nats
from nats.errors import ConnectionClosedError, TimeoutError, NoRespondersError

from rhizon_runtime.core.engine import RuntimeEngine
from rhizon_runtime.core.models import EventEnvelope
from rhizon_runtime.core.interfaces import AgentRuntimeAdapter, AgentState, HealthStatus
from rhizon_runtime.adapters.nats_bus import NatsEventBus
from rhizon_runtime.adapters.nats_router import NatsRouter
from rhizon_runtime.core.bus import InMemoryBus # For fallback if needed, but we verify NATS here

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# --- Mock Agents ---

class OrderAdapter(AgentRuntimeAdapter):
    def __init__(self):
        self.state = {"status": "created", "step": 0}

    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        if envelope.type == "trigger.create_order":
            return [
                EventEnvelope(
                    id=f"evt-order-created-{envelope.id}",
                    ts=envelope.ts,
                    type="evt.order.created",
                    payload={"order_id": "123"},
                    idempotency_key=f"idemp-evt-{envelope.id}",
                    source={"agent": "order", "adapter": "test"},
                    tenant=envelope.tenant,
                    workspace=envelope.workspace,
                    actor=envelope.actor,
                    trace_id=envelope.trace_id,
                    span_id=f"span-order-{envelope.span_id}",
                    security_context=envelope.security_context
                ),
                EventEnvelope(
                    id=f"cmd-inv-reserve-{envelope.id}",
                    ts=envelope.ts,
                    type="cmd.inventory.reserve",
                    payload={"item": "widget", "qty": 1},
                    idempotency_key=f"idemp-cmd-{envelope.id}",
                    source={"agent": "order", "adapter": "test"},
                    tenant=envelope.tenant,
                    workspace=envelope.workspace,
                    actor=envelope.actor,
                    trace_id=envelope.trace_id,
                    span_id=f"span-order-cmd-{envelope.span_id}",
                    security_context=envelope.security_context
                )
            ]
        elif envelope.type == "evt.inventory.reserved":
            return [
                EventEnvelope(
                    id=f"evt-order-finalized-{envelope.id}",
                    ts=envelope.ts,
                    type="evt.order.finalized",
                    payload={"status": "done"},
                    idempotency_key=f"idemp-final-{envelope.id}",
                    source={"agent": "order", "adapter": "test"},
                    tenant=envelope.tenant,
                    workspace=envelope.workspace,
                    actor=envelope.actor,
                    trace_id=envelope.trace_id,
                    span_id=f"span-order-final-{envelope.span_id}",
                    security_context=envelope.security_context
                )
            ]
        return []

    def apply(self, envelope: EventEnvelope) -> None:
        if envelope.type == "evt.order.finalized":
            self.state["status"] = "finalized"
            self.state["step"] += 1

    def tick(self, now: int) -> List[EventEnvelope]:
        return []

    def get_state(self) -> AgentState:
        return AgentState(version=1, data=self.state, updated_at=0)
    
    def health(self) -> HealthStatus:
        return HealthStatus.READY

class InventoryAdapter(AgentRuntimeAdapter):
    def __init__(self):
        self.stock = 100
        self.reservations = []

    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        if envelope.type == "cmd.inventory.reserve":
            return [
                EventEnvelope(
                    id=f"evt-inv-reserved-{envelope.id}",
                    ts=envelope.ts,
                    type="evt.inventory.reserved",
                    payload={"reservation_id": "res-1"},
                    idempotency_key=f"idemp-inv-{envelope.id}",
                    source={"agent": "inventory", "adapter": "test"},
                    tenant=envelope.tenant,
                    workspace=envelope.workspace,
                    actor=envelope.actor,
                    trace_id=envelope.trace_id,
                    span_id=f"span-inv-{envelope.span_id}",
                    security_context=envelope.security_context
                )
            ]
        return []

    def apply(self, envelope: EventEnvelope) -> None:
        if envelope.type == "evt.inventory.reserved":
            self.stock -= 1
            self.reservations.append(envelope.id)

    def tick(self, now: int) -> List[EventEnvelope]:
        return []

    def get_state(self) -> AgentState:
        return AgentState(version=1, data={"stock": self.stock, "reservations": self.reservations}, updated_at=0)

    def health(self) -> HealthStatus:
        return HealthStatus.READY

# --- Infrastructure Helpers ---

@pytest.fixture(scope="module")
def nats_server():
    """Starts a NATS server subprocess."""
    # Find nats-server in tmp_bin or path
    # Check relative to cwd (if inside meshforge-runtime)
    server_path = os.path.join(os.getcwd(), "tmp_bin/nats-server")
    if not os.path.exists(server_path):
        # Check if we are at project root
        server_path = os.path.join(os.getcwd(), "meshforge-runtime/tmp_bin/nats-server")
    
    if not os.path.exists(server_path):
        server_path = "nats-server" # System path fallback

    port = 4222
    cmd = [server_path, "-p", str(port)]
    
    logger.info(f"Starting NATS server: {cmd}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for start
    time.sleep(2)
    
    if proc.poll() is not None:
        out, err = proc.communicate()
        raise RuntimeError(f"NATS server failed to start: {err.decode()}")

    yield f"nats://localhost:{port}"
    
    logger.info("Stopping NATS server...")
    proc.terminate()
    proc.wait()

class AsyncAgentRunner:
    """
    Simulates a running agent process.
    Connects to NATS, subscribes to subjects, runs the Engine.
    """
    def __init__(self, name: str, adapter: AgentRuntimeAdapter, nats_url: str):
        self.name = name
        self.adapter = adapter
        self.nats_url = nats_url
        self.nc = None
        self.engine = None
        self.subs = []

    async def start(self):
        self.nc = await nats.connect(self.nats_url)
        
        bus = NatsEventBus(self.nc)
        router = NatsRouter(self.nc)
        # Fix: Align Engine scope with Test scope (default/demo)
        self.engine = RuntimeEngine(self.name, self.adapter, bus, router=router, deterministic=True, tenant="default", workspace="demo")
        
        # Subscribe to Commands targeting this agent
        # cmd.{tenant}.{workspace}.{target_agent}.{name}
        # We assume tenant=default, workspace=demo for tests
        cmd_subj = f"cmd.default.demo.{self.name}.>"
        sub_cmd = await self.nc.subscribe(cmd_subj, cb=self._on_msg)
        self.subs.append(sub_cmd)
        
        # Subscribe to Events this agent is interested in
        # For Order agent: evt.default.demo.inventory.>
        if self.name == "order":
            evt_subj = "evt.default.demo.inventory.>"
            sub_evt = await self.nc.subscribe(evt_subj, cb=self._on_msg)
            self.subs.append(sub_evt)

    async def stop(self):
        for sub in self.subs:
            await sub.unsubscribe()
        await self.nc.close()

    async def _on_msg(self, msg):
        try:
            data = json.loads(msg.data.decode())
            envelope = EventEnvelope(**data)
            logger.info(f"[{self.name}] Received {envelope.type}")
            
            await self.engine.process_event(envelope)
            
        except Exception as e:
            logger.error(f"[{self.name}] Error processing message: {e}")

@pytest.mark.asyncio
async def test_distributed_saga_flow(nats_server):
    """
    Full Saga: Trigger -> Order -> Inventory -> Order (Finalize)
    Verifies NATS communication between two isolated engines.
    """
    # 1. Setup Runners
    order_adapter = OrderAdapter()
    inv_adapter = InventoryAdapter()
    
    runner_order = AsyncAgentRunner("order", order_adapter, nats_server)
    runner_inv = AsyncAgentRunner("inventory", inv_adapter, nats_server)
    
    await runner_order.start()
    await runner_inv.start()
    
    # 2. Trigger the Saga
    # Manually inject the trigger into Order Engine
    trigger = EventEnvelope(
        id="trig-1",
        ts=1000,
        type="trigger.create_order",
        payload={},
        idempotency_key="key-1",
        source={"agent": "test_driver", "adapter": "manual"},
        tenant="default",
        workspace="demo",
        actor={"id": "user", "role": "admin"},
        trace_id="trace-1",
        span_id="span-1",
        security_context={"principal_id": "user-1", "principal_type": "user"}
    )
    
    # We call process_event directly on the Order Engine to start the chain
    await runner_order.engine.process_event(trigger)
    
    # 3. Wait for Async Processing
    # The saga is asynchronous over NATS. We wait for state convergence.
    # Order -> emits cmd.inventory.reserve -> NATS -> Inventory -> emits evt.inventory.reserved -> NATS -> Order -> updates state
    
    # Poll for Order state
    max_retries = 20
    success = False
    for _ in range(max_retries):
        state = order_adapter.get_state().data
        if state["status"] == "finalized":
            success = True
            break
        await asyncio.sleep(0.1)
        
    assert success, f"Order did not finalize. State: {order_adapter.get_state().data}"
    
    # Check Inventory State
    inv_state = inv_adapter.get_state().data
    assert inv_state["stock"] == 99
    assert len(inv_state["reservations"]) == 1
    
    # 4. Cleanup
    await runner_order.stop()
    await runner_inv.stop()

@pytest.mark.asyncio
async def test_idempotency_over_nats(nats_server):
    """
    Verify that receiving the same command twice via NATS results in only one state change.
    """
    inv_adapter = InventoryAdapter()
    runner_inv = AsyncAgentRunner("inventory", inv_adapter, nats_server)
    await runner_inv.start()
    
    # Create a command
    cmd = EventEnvelope(
        id="cmd-100",
        ts=1000,
        type="cmd.inventory.reserve",
        payload={"item": "widget", "qty": 1},
        idempotency_key="unique-key-100",
        source={"agent": "order", "adapter": "test"},
        tenant="default",
        workspace="demo",
        actor={"id": "user", "role": "admin"},
        trace_id="trace-100",
        span_id="span-100",
        security_context={"principal_id": "user-1", "principal_type": "user"}
    )
    
    # Publish via NATS (simulating sender)
    nc = await nats.connect(nats_server)
    subject = "cmd.default.demo.inventory.reserve"
    payload = cmd.model_dump_json().encode()
    
    # Send twice
    await nc.publish(subject, payload)
    await nc.publish(subject, payload)
    await nc.flush()
    
    # Wait for processing
    await asyncio.sleep(1) # Simple wait
    
    # Check State: should decrease by 1, not 2
    state = inv_adapter.get_state().data
    assert state["stock"] == 99 # Started at 100
    assert len(state["reservations"]) == 1 # Just 1 reservation record (idempotency in Engine should skip 2nd apply)
    
    await nc.close()
    await runner_inv.stop()
