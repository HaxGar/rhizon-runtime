## ADDED Requirements

### Requirement: Worker Agent Contract
The Agent SDK SHALL expose a `WorkerAgent` abstract class that handles `cmd.*` inputs, emits `work.*` events, and enforces deterministic step functions (`handle_command`, `emit_work`). Workers MUST be stateless between invocations except for explicit artifact references.

#### Scenario: Command handling envelope
- **WHEN** a worker receives a `cmd.*` event via `handle_command`
- **THEN** the SDK MUST pass a normalized event envelope, scoped logger, contract validator handle, and artifact repository references

### Requirement: Manager Agent Contract
The Agent SDK SHALL expose a `ManagerAgent` base class that supervises workers, orchestrates retries, and emits `evt.*` lifecycle events. Managers MUST be able to spawn worker tasks declaratively (`schedule_work(work_descriptor)`).

#### Scenario: Supervisory decision
- **WHEN** a manager receives a `work.*` completion event
- **THEN** it MUST evaluate guardrails, optionally trigger retries, and emit a correlated `evt.manager.*` status update via the Event SDK

### Requirement: Gateway Agent Contract
The Agent SDK SHALL define `GatewayAgent` for ingress/egress translation. Gateways MUST validate inbound events against workspace contracts before relaying them to workers and MUST sanitize outbound payloads before exiting the workspace boundary.

#### Scenario: Contract enforcement
- **WHEN** a gateway ingests user input
- **THEN** it MUST run the `contract_engine.validate("ingress", payload)` hook before constructing a `cmd.*` event

### Requirement: Governor Agent Contract
The Agent SDK SHALL define `GovernorAgent` for guardrail enforcement. Governors MUST subscribe to `obs.*` telemetry streams and emit `evt.guardrail.*` violations with actionable remediation data.

#### Scenario: Guardrail violation
- **WHEN** a governor detects a correlation_id triggering p99 latency thresholds
- **THEN** it MUST emit an `evt.guardrail.latency-breach` with offending run metadata and recommended throttling action

### Requirement: Shared Agent Services
The Agent SDK SHALL provide shared utilities: `AgentContext` (event, logger, metrics, repositories), deterministic random seeds, and token-cost accounting hooks. All agent subclasses MUST receive `AgentContext` via dependency injection.

#### Scenario: Context injection
- **WHEN** the runtime instantiates any agent
- **THEN** it MUST construct an `AgentContext` object and pass it to the agent constructor; failure MUST raise `AgentContextMissing`
