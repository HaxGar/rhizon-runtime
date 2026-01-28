## ADDED Requirements

### Requirement: Append-Only Audit Log
The runtime SHALL provide an append-only audit log service storing JSON entries with fields: `audit_id`, `timestamp`, `actor_id`, `workspace_id`, `action`, `correlation_id`, `causation_id`, `run_id`, `payload_hash`, `details`. Entries MUST be immutable once written.

#### Scenario: Audit write success
- **WHEN** any agent performs a privileged action (publish artifact, escalate, override guardrail)
- **THEN** the audit service MUST persist an entry containing the `run_id` of the execution context, replicate it to the workspace's audit store, and expose it via `audit_client.query(filters)`

### Requirement: Structured Logging
All logs SHALL include correlation metadata (`correlation_id`, `run_id`, `tenant_id`). The SDK MUST wrap logging libraries (e.g., structlog) to enforce this schema and reject attempts missing metadata.

#### Scenario: Missing metadata rejection
- **WHEN** a developer attempts to log without `correlation_id` or `run_id`
- **THEN** the logging wrapper MUST raise `MissingCorrelationContext` and avoid emitting partial logs

### Requirement: Standard Metrics
The runtime telemetry subsystem SHALL emit metrics for:
- Latency (p50, p95, p99) per agent and per event type
- Errors per agent and per event type
- Queue depth per bus
- Token cost per agent invocation

Metrics MUST be pushed to the workspaces monitoring backend with tags `workspace_id`, `tenant_id`, `agent_role`.

#### Scenario: Latency metric recorded
- **WHEN** a worker invocation finishes
- **THEN** the telemetry client MUST record timings, update p95/p99 aggregates, and emit `obs.latency.worker` datapoints

### Requirement: Telemetry Correlation
Telemetry events (obs.*) MUST include `correlation_id`, `causation_id`, and `run_id`. Observability dashboards SHALL allow filtering by these IDs to trace end-to-end executions.

#### Scenario: Correlated telemetry
- **WHEN** a queue depth alert is emitted
- **THEN** it MUST include the `correlation_id` and `run_id` of the flow that triggered sustained depth increases

### Requirement: Access Scope & Governance
Audit and telemetry queries MUST be scoped by `workspace_id` by default.
Cross-workspace access (Super Admin) SHALL only be granted:
- Explicitly by the Workspace Admin.
- With mandatory audit logging of the access itself.

#### Scenario: Unauthorized cross-workspace query
- **WHEN** a user attempts to query audit logs for a workspace they do not belong to
- **THEN** the request MUST be rejected with `AccessDenied` and the attempt logged.

### Requirement: Data Responsibility Separation
The runtime SHALL strictly enforce the following separation of concerns:
- **Audit Logs**: Immutable, append-only records of sensitive decisions and governance actions.
- **Application Logs**: Diagnostic data for debugging and execution tracing.
- **Telemetry**: Aggregated time-series metrics and trends.
