# OpenSpec Proposal: DF-006 Runtime Phase 0.6 (Alpha)

**Status:** DRAFT
**Author:** MeshForge Factory Agent
**Date:** 2026-01-02

## 1. Runtime Core Invariants (Non-Negotiable)

To guarantee the "Hexagonal" and "Agnostic" nature of the MeshForge Runtime:

1.  **No Framework Dependencies**: The `runtime_core/` package MUST NOT import or depend on any third-party agent framework (LangChain, AutoGen, CrewAI, MAF).
2.  **Adapter Pattern**: All agentic behaviors (LLM, Graph, etc.) MUST be encapsulated behind the `AgentRuntimeAdapter` (ARA) interface.
3.  **Determinism**:
    *   No calls to system time (`time.now()`) inside core logic; timestamps are injected.
    *   No generation of non-deterministic UUIDs during replay.
    *   Stable key ordering in all serialized outputs (JSON/YAML).

## 2. Agent Runtime Adapter (ARA) Contract

The `AgentRuntimeAdapter` is the sole interface between the Runtime Core and specific agent implementations.

```python
class AgentRuntimeAdapter(Protocol):
    """
    Protocol defining the contract for any Agent running in MeshForge.
    Must be pure/deterministic given the inputs.
    """
    
    def receive(self, envelope: EventEnvelope) -> list[EventEnvelope]:
        """
        Process a single incoming event and return resulting events.
        MUST be idempotent based on envelope.idempotency_key.
        MUST NOT emit side effects directly (only returns events).
        """
        ...

    def tick(self, now: int) -> list[EventEnvelope]:
        """
        Periodic tick for time-based logic (retries, timeouts).
        'now' is provided by the Runtime (injected).
        """
        ...

    def get_state(self) -> AgentState:
        """
        Return the current internal state of the agent.
        MUST be JSON-serializable and stable.
        """
        ...

    def health(self) -> HealthStatus:
        """
        Report agent health (READY, DEGRADED, FAILED) with reasons.
        """
        ...
```

**AgentState Schema (Minimal):**
```python
class AgentState(BaseModel):
    version: int
    data: dict[str, Any]  # The framework-specific state (e.g., LangGraph checkpoint)
    last_processed_event_id: str
    updated_at: int
```

## 3. EventEnvelope V1

Strict schema for all messages on the Bus.

**Mandatory Fields:**

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `str` | Unique Event ID. Stable/Derivable in deterministic mode. |
| `ts` | `int` | Unix Timestamp (ms). Injected by Runtime or 0 in deterministic mode. |
| `type` | `str` | Event Type (e.g., `cmd.order.submit`, `evt.order.created`). |
| `schema_version` | `str` | Version of the envelope schema (fixed: `1.0`). |
| `trace_id` | `str` | OpenTelemetry Trace ID. |
| `span_id` | `str` | OpenTelemetry Span ID. |
| `tenant` | `str` | Multi-tenancy isolation key. |
| `workspace` | `str` | Workspace isolation key. |
| `actor` | `dict` | `{ "id": str, "role": str }` (User or Agent). |
| `payload` | `dict` | The actual business data. |
| `idempotency_key` | `str` | **Critical**. Used for de-duplication and replay. |
| `source` | `dict` | `{ "agent": str, "adapter": str }`. |

**Naming Conventions:**
- `cmd.*`: Command (Intent) - e.g., `cmd.payment.process`
- `evt.*`: Event (Fact) - e.g., `evt.payment.processed`
- `qry.*`: Query (Read) - e.g., `qry.order.get` (Optional, sync/async pattern)
- `res.*`: Response (Answer) - e.g., `res.order.data` (Optional)

**Stability Rules:**
- JSON serialization MUST use sorted keys.
- Unknown fields MUST be preserved during transit but NOT inferred/invented.

## 4. Delivery Semantics

1.  **At-Least-Once**: The Runtime guarantees delivery. Consumers must handle duplicates.
2.  **Idempotence**:
    *   The Runtime tracks processed `idempotency_key`s.
    *   If a duplicate key is received, the Runtime MUST NOT invoke `receive()` again.
    *   It MAY return the previously emitted events (cached) or ack directly.
3.  **Replay Policy**:
    *   Replaying an event stream from offset 0 MUST result in the exact same final `AgentState`.
    *   Emitted events during replay are marked as `duplicate` or filtered by the Bus if already published.
4.  **Error Handling**:
    *   System failures emit `evt.runtime.error`.
    *   **Fields**: `error_code`, `message`, `stack_trace` (debug only), `original_event_id`.

## 5. Bus Specification

**Interface (Abstract):**
```python
class EventBus(Protocol):
    async def publish(self, events: list[EventEnvelope]) -> None: ...
    async def subscribe(self, pattern: str, callback: Callable) -> None: ...
```

**Implementations:**
1.  **V0: InMemoryBus**: For local dev, testing, and deterministic replay.
2.  **V1: NATSJetStreamBus**: (Optional) For distributed production.
    *   The Runtime Core knows only `EventBus`. NATS implementation lives in `infrastructure/`.

## 6. Observability Hooks (DF-008 Compatible)

The Runtime MUST emit telemetry for every `receive()` / `tick()` cycle.

**Metrics:**
- `events_received_total{type, agent, status}`
- `events_emitted_total{type, agent}`
- `event_processing_duration_ms{type, agent}`

**Tracing:**
- Every `EventEnvelope` processed starts a new Span (linked to `trace_id` in envelope).
- Logs MUST be structured JSON and include `trace_id`, `span_id`, `agent_id`.

## 7. Required Tests

The implementation plan MUST include the following verification tests:

- [ ] `test_adapter_contract_compliance`: Verify ARA raises error if signatures mismatch.
- [ ] `test_replay_idempotency`: Send same event twice -> `receive()` called once -> State unchanged.
- [ ] `test_deterministic_hash_runtime`: Run sequence A -> Hash state. Reset. Run sequence A -> Hash state. Assert Hash1 == Hash2.
- [ ] `test_no_framework_dependency_in_runtime_core`: Static analysis to ban `langchain`, `autogen` imports in `runtime_core/`.
