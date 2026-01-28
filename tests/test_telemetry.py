import pytest
import asyncio
import json
import hashlib
from typing import List
from unittest.mock import MagicMock

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from rhizon_runtime.core.engine import RuntimeEngine
from rhizon_runtime.core.models import EventEnvelope
from rhizon_runtime.core.interfaces import AgentRuntimeAdapter, AgentState, HealthStatus
from rhizon_runtime.core.bus import InMemoryBus

# --- Mock Adapter ---
class CounterAdapter(AgentRuntimeAdapter):
    def __init__(self):
        self.count = 0

    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        return [
            EventEnvelope(
                id=f"evt-{envelope.id}-1",
                ts=envelope.ts + 1,
                type="evt.count.incremented",
                trace_id=envelope.trace_id,
                span_id=envelope.span_id,
                tenant=envelope.tenant,
                workspace=envelope.workspace,
                actor=envelope.actor,
                payload={"new_count": self.count + 1},
                idempotency_key=f"out-{envelope.idempotency_key}",
                source={"agent": "counter", "adapter": "test"},
                security_context=envelope.security_context
            )
        ]

    def apply(self, envelope: EventEnvelope) -> None:
        if envelope.type == "evt.count.incremented":
            self.count = envelope.payload["new_count"]

    def tick(self, now: int) -> List[EventEnvelope]:
        return []

    def get_state(self) -> AgentState:
        return AgentState(version=1, data={"count": self.count}, updated_at=0)

    def health(self) -> HealthStatus:
        return HealthStatus.READY

# --- Telemetry Fixtures ---
@pytest.fixture
def telemetry_setup():
    # Setup Memory Exporters
    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    
    # Create isolated providers
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    
    # Retrieve tracer and meter from these isolated providers
    tracer = tracer_provider.get_tracer("test_tracer")
    meter = meter_provider.get_meter("test_meter")
    
    yield span_exporter, metric_reader, tracer, meter

@pytest.mark.asyncio
async def test_telemetry_instrumentation(telemetry_setup):
    span_exporter, metric_reader, tracer, meter = telemetry_setup
    
    bus = InMemoryBus()
    adapter = CounterAdapter()
    # Inject isolated tracer/meter, align scope with envelope
    engine = RuntimeEngine("test_agent_otel", adapter, bus, tracer=tracer, meter=meter, tenant="default", workspace="demo")
    
    # Send Event
    envelope = EventEnvelope(
        id="evt-1",
        ts=1000,
        type="cmd.increment",
        trace_id="trace-1",
        span_id="span-1",
        tenant="default",
        workspace="demo",
        actor={"id": "user-1", "role": "admin"},
        payload={},
        idempotency_key="key-1",
        source={"agent": "user", "adapter": "http"},
        security_context={"principal_id": "user-1", "principal_type": "user"}
    )
    
    await engine.process_event(envelope)
    
    # Verify Spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) >= 1
    
    # Find root span
    process_span = next((s for s in spans if s.name == "process_event"), None)
    assert process_span is not None, "Root process_event span not found"
    
    assert process_span.attributes["agent.id"] == "test_agent_otel"
    assert process_span.attributes["event.type"] == "cmd.increment"
    assert process_span.attributes["events.emitted_count"] == 1
    
    # Verify child spans exist
    child_names = [s.name for s in spans]
    assert "adapter.receive" in child_names
    assert "adapter.apply_batch" in child_names
    
    # Verify Metrics
    metrics_data = metric_reader.get_metrics_data()
    assert metrics_data is not None
    
    # Check for specific metrics (structure is deeply nested in OTEL SDK)
    resource_metrics = metrics_data.resource_metrics
    found_received = False
    found_emitted = False
    found_duration = False
    
    for rm in resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == "events_received_total":
                    found_received = True
                    # Check value
                    for point in metric.data.data_points:
                        assert point.value == 1
                        assert point.attributes["agent"] == "test_agent_otel"
                elif metric.name == "events_emitted_total":
                    found_emitted = True
                    for point in metric.data.data_points:
                        assert point.value == 1
                        assert point.attributes["agent"] == "test_agent_otel"
                elif metric.name == "event_processing_duration_ms":
                    found_duration = True
    
    assert found_received, "events_received_total metric not found"
    assert found_emitted, "events_emitted_total metric not found"
    assert found_duration, "event_processing_duration_ms metric not found"

@pytest.mark.asyncio
async def test_telemetry_determinism(telemetry_setup):
    """
    Ensure telemetry does NOT affect the deterministic state hash.
    We compare the hash of an engine with telemetry enabled vs disabled (or simply verify it matches expected).
    Since OTEL is always 'on' in code but might have different providers, 
    the core requirement is that `get_state_hash` only looks at `adapter.get_state()`.
    """
    span_exporter, metric_reader, tracer, meter = telemetry_setup
    
    bus = InMemoryBus()
    adapter = CounterAdapter()
    # Inject isolated tracer/meter, align scope
    engine = RuntimeEngine("test_agent_det", adapter, bus, deterministic=True, tracer=tracer, meter=meter, tenant="default", workspace="demo")
    
    # Initial Hash
    hash1 = engine.get_state_hash()
    
    # Process Event
    envelope = EventEnvelope(
        id="evt-1",
        ts=1000,
        type="cmd.increment",
        trace_id="trace-1",
        span_id="span-1",
        tenant="default",
        workspace="demo",
        actor={"id": "user-1", "role": "admin"},
        payload={},
        idempotency_key="key-1",
        source={"agent": "user", "adapter": "http"},
        security_context={"principal_id": "user-1", "principal_type": "user"}
    )
    await engine.process_event(envelope)
    
    hash2 = engine.get_state_hash()
    
    # Expected state data: {"count": 1}
    expected_data = {"count": 1}
    # Manually compute hash
    import json
    # AgentState structure: version, data, updated_at, last_processed_event_id, entity_versions
    # The engine uses adapter.get_state() which uses default None for last_processed_event_id
    state_dict = {
        "version": 1, 
        "data": expected_data, 
        "updated_at": 0,
        "last_processed_event_id": None,
        "entity_versions": {}
    }
    json_str = json.dumps(state_dict, sort_keys=True)
    expected_hash = hashlib.sha256(json_str.encode()).hexdigest()
    
    assert hash2 == expected_hash
    assert hash1 != hash2
    
    # Verify traces didn't leak into state
    spans = span_exporter.get_finished_spans()
    assert len(spans) >= 1
    # Check that no span ID or trace ID ends up in the state (unless explicitly put there by adapter, which CounterAdapter doesn't)
    state_data = adapter.get_state().data
    assert "trace_id" not in state_data

@pytest.mark.asyncio
async def test_telemetry_default_noop():
    """
    Verify that RuntimeEngine works without any telemetry configuration (No-Op default).
    """
    bus = InMemoryBus()
    adapter = CounterAdapter()
    # No tracer/meter injected, usage of default global (which is NoOp if not set)
    # Align scope
    engine = RuntimeEngine("test_agent_noop", adapter, bus, tenant="default", workspace="demo")
    
    envelope = EventEnvelope(
        id="evt-noop-1",
        ts=1000,
        type="cmd.increment",
        trace_id="trace-1",
        span_id="span-1",
        tenant="default",
        workspace="demo",
        actor={"id": "user-1", "role": "admin"},
        payload={},
        idempotency_key="key-noop",
        source={"agent": "user", "adapter": "http"},
        security_context={"principal_id": "user-1", "principal_type": "user"}
    )
    
    # Should not raise error
    output = await engine.process_event(envelope)
    assert len(output) == 1
    assert output[0].type == "evt.count.incremented"

