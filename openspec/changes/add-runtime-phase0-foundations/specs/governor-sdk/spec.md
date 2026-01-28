## ADDED Requirements

### Requirement: Guardrail Policy Engine
The Governor SDK SHALL load guardrail policies from versioned artifacts and evaluate them against telemetry streams. Policies MUST express conditions (latency, error rate, cost) and remediation actions (pause, throttle, alert).

#### Scenario: Policy evaluation
- **WHEN** `obs.*` metrics exceed a configured threshold
- **THEN** the SDK MUST run the matching policy, trigger the remediation action, and emit `evt.guardrail.policy-fired`

### Requirement: Enforcement Channels
Governors SHALL communicate enforcement decisions to managers, workers, and gateways through dedicated `evt.guardrail.*` events. The SDK MUST provide helper methods `notify_manager`, `notify_worker`, `notify_gateway`.

#### Scenario: Notify manager
- **WHEN** a governor decides to pause a workflow
- **THEN** `notify_manager` MUST send an event referencing the correlation_id, include severity, and block further `work.*` emissions until cleared

### Requirement: Audit Hooks
Every guardrail evaluation MUST append audit entries with full context (policy id, inputs, outputs, actors). The SDK SHALL integrate with the Audit & Telemetry subsystem via `audit_client.log_guardrail_event`.

#### Scenario: Audit entry created
- **WHEN** any guardrail fires
- **THEN** the SDK MUST create an audit record before returning control to the caller
