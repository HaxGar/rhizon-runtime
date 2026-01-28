import pytest
import asyncio
import os
import time
import json
import logging
import signal
import subprocess
from typing import List, Dict, Any
import nats
from nats.js.api import StreamConfig, RetentionPolicy

from rhizon_runtime.core.engine import RuntimeEngine
from rhizon_runtime.core.models import EventEnvelope
from rhizon_runtime.core.interfaces import AgentRuntimeAdapter, AgentState, HealthStatus
from rhizon_runtime.adapters.jetstream_bus import JetStreamEventBus
from rhizon_runtime.adapters.jetstream_router import JetStreamCommandRouter
from rhizon_runtime.adapters.jetstream_consumer import JetStreamConsumer
from rhizon_runtime.persistence.sqlite import SQLiteEventStore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Mock Agent ---

class CounterAdapter(AgentRuntimeAdapter):
    def __init__(self):
        self.count = 0
        self.processed_ids = []

    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        if "poison" in envelope.type:
            raise RuntimeError("Poison Pill detected!")
            
        if envelope.type == "cmd.counter.increment":
            return [
                EventEnvelope(
                    id=f"evt-inc-{envelope.id}",
                    ts=envelope.ts,
                    type="evt.counter.incremented",
                    payload={"new_count": self.count + 1}, # Optimistic/Stateless projection for event payload
                    idempotency_key=f"idemp-evt-{envelope.id}",
                    source={"agent": "counter", "adapter": "test"},
                    tenant=envelope.tenant,
                    workspace=envelope.workspace,
                    actor=envelope.actor,
                    trace_id=envelope.trace_id,
                    span_id=f"span-inc-{envelope.span_id}",
                    security_context=envelope.security_context
                )
            ]
        return []

    def apply(self, envelope: EventEnvelope) -> None:
        if envelope.type == "evt.counter.incremented":
            self.count += 1
            self.processed_ids.append(envelope.id)

    def tick(self, now: int) -> List[EventEnvelope]:
        return []

    def get_state(self) -> AgentState:
        return AgentState(version=1, data={"count": self.count, "processed": self.processed_ids}, updated_at=0)
    
    def health(self) -> HealthStatus:
        return HealthStatus.READY

# --- Infrastructure Helpers ---

@pytest.fixture(scope="module")
def nats_server():
    """Starts a NATS server subprocess with JetStream enabled."""
    server_path = os.path.join(os.getcwd(), "tmp_bin/nats-server")
    if not os.path.exists(server_path):
        server_path = os.path.join(os.getcwd(), "meshforge-runtime/tmp_bin/nats-server")
    
    if not os.path.exists(server_path):
        server_path = "nats-server"

    # Port 4223 to avoid conflict with other tests
    port = 4223
    store_dir = "/tmp/nats-jetstream-test"
    # Clean up previous run
    if os.path.exists(store_dir):
        import shutil
        shutil.rmtree(store_dir)
        
    cmd = [server_path, "-p", str(port), "-js", "-sd", store_dir]
    
    logger.info(f"Starting NATS JetStream server: {cmd}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    time.sleep(2)
    
    if proc.poll() is not None:
        out, err = proc.communicate()
        raise RuntimeError(f"NATS server failed to start: {err.decode()}")

    yield f"nats://localhost:{port}"
    
    logger.info("Stopping NATS server...")
    proc.terminate()
    proc.wait()
    if os.path.exists(store_dir):
        import shutil
        shutil.rmtree(store_dir)

class ControlledConsumer(JetStreamConsumer):
    """
    A JetStreamConsumer that allows injecting failures for testing.
    """
    def __init__(self, nc, engine, stream_name, subject_filter, durable_name, backoff_policy=None):
        super().__init__(nc, engine, stream_name, subject_filter, durable_name, backoff_policy=backoff_policy)
        self.crash_after_process_before_ack = False

    async def _process_msg(self, msg):
        # 1. Parse
        data = json.loads(msg.data.decode())
        envelope = EventEnvelope(**data)
        
        # 2. Process via Engine
        await self.engine.process_event(envelope)
        
        # FAILURE INJECTION
        if self.crash_after_process_before_ack:
            logger.warning("SIMULATING CRASH: Processed but NOT Acking (Sending NAK for fast redelivery).")
            await msg.nak()
            return # Stop here

        # 3. ACK
        await msg.ack()

@pytest.mark.asyncio
async def test_durability_crash_before_ack(nats_server, tmp_path):
    """
    Scenario:
    1. Agent receives command.
    2. Engine processes it (Store + Apply + Publish SideEffect).
    3. Consumer CRASHES before ACK (Simulated by NAK).
    4. NATS Redelivers.
    5. Agent receives command AGAIN.
    6. Engine detects Idempotency.
    7. Engine Re-publishes SideEffect (At-Least-Once).
    8. Engine returns original output.
    9. Consumer ACKs.
    10. Result: Agent State incremented ONCE. SideEffects published TWICE (idempotent downstream).
    """
    # Setup NATS
    nc = await nats.connect(nats_server)
    js = nc.jetstream()
    
    # Create Streams
    try:
        await js.add_stream(name="MESHFORGE_COMMANDS", subjects=["cmd.>"], retention=RetentionPolicy.WORK_QUEUE)
        await js.add_stream(name="MESHFORGE_EVENTS", subjects=["evt.>"], retention=RetentionPolicy.LIMITS)
    except Exception:
        pass # Already exists

    # Setup Agent
    db_path = tmp_path / "events.db"
    store = SQLiteEventStore(str(db_path))
    adapter = CounterAdapter()
    
    bus = JetStreamEventBus(nc) # Publish side effects to events stream
    engine = RuntimeEngine("counter", adapter, bus, store=store, deterministic=True, tenant="default", workspace="test")
    
    consumer = ControlledConsumer(
        nc, engine, "MESHFORGE_COMMANDS", "cmd.default.test.counter.>", "counter_consumer"
    )
    
    # 1. Inject Crash Policy
    consumer.crash_after_process_before_ack = True
    
    await consumer.start()
    
    # 2. Publish Command
    cmd = EventEnvelope(
        id="cmd-1",
        ts=1000,
        type="cmd.counter.increment",
        payload={},
        idempotency_key="idemp-1",
        source={"agent": "test", "adapter": "manual"},
        tenant="default",
        workspace="test",
        actor={"id": "user", "role": "admin"},
        trace_id="t1",
        span_id="s1",
        security_context={"principal_id": "user-1", "principal_type": "user"}
    )
    
    router = JetStreamCommandRouter(nc)
    await router.route(cmd)
    
    # 3. Wait for "Crash" (Processing + Nak)
    await asyncio.sleep(1)
    
    # Verify State: Should be 1 (Processed once)
    assert adapter.count == 1
    
    # Verify Side Effect published once (so far)
    # We can subscribe to verify, or check logs.
    # Let's verify via stream info? Or subscription.
    
    sub = await nc.subscribe("evt.>")
    # We missed the first one probably? No, durable stream.
    # But we are subscribing ephemeral.
    # Let's check idempotency handling on redelivery.
    
    # 4. Disable Crash Policy to allow recovery
    consumer.crash_after_process_before_ack = False
    
    # Since we NAK'd, NATS should redeliver immediately.
    # Wait for redelivery and success.
    await asyncio.sleep(1)
    
    # Verify State: Still 1 (Idempotent!)
    assert adapter.count == 1
    
    # Verify Engine detected duplicate
    # We can check metrics or processed keys?
    assert "idemp-1" in engine._processed_keys
    
    # Cleanup
    await consumer.stop()
    await nc.close()
    store.close()

@pytest.mark.asyncio
async def test_dlq_max_deliveries(nats_server, tmp_path):
    """
    Scenario:
    1. Consumer is configured to ALWAYS fail (simulating poison pill).
    2. Message delivered 5 times.
    3. Consumer logic detects max deliveries.
    4. Publishes to failed.>.
    5. ACKs original message.
    """
    nc = await nats.connect(nats_server)
    js = nc.jetstream()
    
    # Ensure streams (Use distinct stream/subject to avoid conflict with previous test)
    # Note: 'cmd.>' (from previous test) overlaps with 'cmd.dlq.>' if we used that.
    # So we use 'test_dlq_cmd.>' which does NOT overlap with 'cmd.>'.
    await js.add_stream(name="MESHFORGE_COMMANDS_DLQ", subjects=["test_dlq_cmd.>"], retention=RetentionPolicy.WORK_QUEUE)
    try:
        await js.add_stream(name="MESHFORGE_FAILED", subjects=["failed.>"], retention=RetentionPolicy.LIMITS)
    except Exception:
        pass

    db_path = tmp_path / "events_dlq.db"
    store = SQLiteEventStore(str(db_path))
    adapter = CounterAdapter()
    engine = RuntimeEngine("counter", adapter, None, store=store, deterministic=True, tenant="default", workspace="test")
    
    # Fast backoff: 50ms, 50ms, 50ms, 50ms (len=4, max_deliver=5) -> Use seconds (0.05s)
    fast_backoff = [0.05] * 4 

    # Use JetStreamConsumer directly (Tests the base class DLQ logic)
    consumer = JetStreamConsumer(
        nc, engine, "MESHFORGE_COMMANDS_DLQ", "test_dlq_cmd.counter.>", "counter_dlq_consumer",
        backoff_policy=fast_backoff
    )
    # consumer.crash_after_process_before_ack is not needed because the Adapter raises Exception
    
    await consumer.start()
    
    # Publish Command directly (Bypassing Router to use custom subject matching filter)
    # Filter: test_dlq_cmd.counter.>
    # Subject: test_dlq_cmd.counter.poison
    cmd = EventEnvelope(
        id="cmd-poison",
        ts=1000,
        type="test_dlq_cmd.counter.poison",
        payload={},
        idempotency_key="idemp-poison",
        source={"agent": "test", "adapter": "manual"},
        tenant="default",
        workspace="test",
        actor={"id": "user", "role": "admin"},
        trace_id="t1",
        span_id="s1",
        security_context={"principal_id": "user-1", "principal_type": "user"}
    )
    
    payload = cmd.model_dump_json().encode()
    await js.publish("test_dlq_cmd.counter.poison", payload)
    
    # Wait for retries
    # 5 retries * 50ms = 250ms minimum. Wait 2s to be safe.
    await asyncio.sleep(2)
    
    # Verify DLQ
    # Check if message is in "failed.>"
    # We can subscribe to check
    sub_dlq = await nc.subscribe("failed.>")
    
    # We might have missed it if we subscribe now?
    # Stream MESHFORGE_FAILED is durable (Limits). We can fetch from it.
    # But for simplicity, let's just pull from stream or use fetch.
    
    # Use JS Fetch on failed stream
    try:
        # Create ephemeral consumer to peek
        psub = await js.pull_subscribe("failed.>", stream="MESHFORGE_FAILED")
        msgs = await psub.fetch(1, timeout=1.0)
        assert len(msgs) == 1
        failed_msg = msgs[0]
        data = json.loads(failed_msg.data.decode())
        assert data["id"] == "cmd-poison"
        await failed_msg.ack()
    except Exception as e:
        pytest.fail(f"Did not find message in DLQ: {e}")

    # Verify original message is ACKed (removed from work queue)
    # We can check stream info
    si = await js.stream_info("MESHFORGE_COMMANDS_DLQ")
    assert si.state.messages == 0
    
    await consumer.stop()
    await nc.close()
    store.close()
