## ADDED Requirements

### Requirement: Supervisory Loop
The Manager SDK SHALL provide a supervisory loop primitive `run_supervisor()` that consumes `work.*` outputs, invokes guardrail evaluation hooks, and issues `evt.manager.*` decisions (approve/retry/escalate).

#### Scenario: Retry issued
- **WHEN** a worker signals retriable failure metadata
- **THEN** the supervisory loop MUST emit an `evt.manager.retry-requested`, enqueue a new `work.*` event with incremented attempt count, and log the decision in audit

### Requirement: Worker Lease Management
The Manager SDK SHALL track worker leases (start timestamp, TTL, lease token) to avoid duplicate work. It MUST expose `acquire_lease(command_id)` and `release_lease(lease_token)` helpers backed by the runtime persistence layer.

#### Scenario: Duplicate prevention
- **WHEN** a second worker attempts to pick the same `cmd.*`
- **THEN** `acquire_lease` MUST reject with `LeaseAlreadyClaimed` and the manager MUST emit an `obs.queue.duplicate-blocked` metric

### Requirement: Escalation Pathways
Managers SHALL define escalation policies referencing Governor agents. The SDK MUST provide `escalate_to_governor(reason, context)` which wraps the context envelope, forwards it to the Governor queue, and records the escalation.

#### Scenario: Governor escalation
- **WHEN** retries exceed configured thresholds
- **THEN** `escalate_to_governor` MUST emit `evt.manager.escalated`, push an event to the Governor topic, and include causation metadata for observability
