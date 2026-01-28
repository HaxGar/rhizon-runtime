# Runtime Core Specification

**ID:** RUNTIME-CORE-001
**Type:** Component Specification
**Status:** DRAFT

## ADDED Requirements

### Requirement: Runtime Core Invariants
The Runtime Core MUST maintain strict isolation and determinism.

#### Scenario: No Framework Dependencies
Given the `runtime_core` package
When I inspect the import statements
Then I should NOT see any references to `langchain`, `autogen`, `crewai`, or `maf`
And I should only see standard library or internal `meshforge` imports.

#### Scenario: Deterministic Execution
Given the Runtime is running in `--deterministic` mode
When I execute a sequence of events
Then no system time functions (e.g., `time.time()`) should be called directly
And timestamps should be injected by the runtime engine
And UUIDs should be generated using a deterministic seed.

### Requirement: Agent Runtime Adapter (ARA) Contract
All agents MUST implement the ARA Protocol.

#### Scenario: Pure Receive Function
Given an agent implementing ARA
When `receive(envelope)` is called
Then it should return a list of `EventEnvelope`
And it should NOT emit events to the bus directly
And it should NOT modify external state directly.

#### Scenario: Health Check
Given an agent
When `health()` is called
Then it should return a `HealthStatus` (READY, DEGRADED, FAILED)
And include a list of reasons if not READY.

### Requirement: EventEnvelope V1 Schema
All bus messages MUST conform to V1 Schema.

#### Scenario: Mandatory Fields
Given an `EventEnvelope`
Then it MUST contain `id`, `ts`, `type`, `schema_version`, `idempotency_key`
And `source` MUST contain `agent` and `adapter` identifiers.

#### Scenario: Stable Serialization
Given an `EventEnvelope`
When it is serialized to JSON
Then keys MUST be sorted alphabetically
And the output MUST be bit-for-bit identical for the same content.

### Requirement: Delivery Semantics
The Runtime MUST ensure at-least-once delivery and idempotence.

#### Scenario: Idempotency Check
Given the Runtime has processed an envelope with key "IDEM-123"
When the same envelope "IDEM-123" is received again
Then the agent's `receive` method MUST NOT be invoked
And the Runtime MAY return cached outgoing events or ACK.

#### Scenario: Replay Determinism
Given a recorded stream of inputs
When the stream is replayed to an agent from clean state
Then the final `AgentState` MUST be identical to the original run.

### Requirement: Bus Specification
The Runtime MUST rely on an abstract EventBus interface.

#### Scenario: InMemoryBus Operation
Given an `InMemoryBus`
When `publish` is called with events
Then all subscribers matching the pattern should be invoked synchronously (or awaited).

### Requirement: Observability Hooks
The Runtime MUST emit telemetry.

#### Scenario: Metrics Emission
Given the Runtime is processing an event
Then it MUST increment `events_received_total`
And it MUST measure `event_processing_duration_ms`
And it MUST increment `events_emitted_total` for output events.
