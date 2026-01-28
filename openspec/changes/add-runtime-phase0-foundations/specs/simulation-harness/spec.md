## ADDED Requirements

### Requirement: Deterministic Scenario Runner
The simulation harness SHALL provide a deterministic runner that replays scripted event sequences (ingress → worker → manager → governor) using recorded PRD specs. The runner MUST seed RNG, freeze clocks, and capture all emitted events for comparison.

#### Scenario: Deterministic replay
- **WHEN** the same scenario is executed twice
- **THEN** the harness MUST produce identical event timelines (message_ids excluded) and flag any divergence

### Requirement: Contract Compliance Checks
The harness SHALL validate every emitted event and artifact transition against the Contract Engine during simulation. Failures MUST abort the run and produce a detailed diff for remediation.

#### Scenario: Contract failure report
- **WHEN** a simulated worker emits a payload violating schema
- **THEN** the harness MUST halt, emit `simulation.report` with the contract error, and mark the run as failed

### Requirement: Infinite Loop Detection
The harness SHALL detect loops by tracking correlation_id + type sequences. If a flow exceeds configurable repetition or duration thresholds, the harness MUST stop execution and report the suspected loop.

#### Scenario: Loop detected
- **WHEN** a workflow emits more than N identical `work.*` events for the same correlation_id
- **THEN** the harness MUST terminate the run and emit `simulation.loop-detected`

### Requirement: Compliance Report
After each run the harness SHALL produce a compliance report containing:
- Event validation summary
- Contract validation results
- Guardrail outcomes
- Metrics snapshot (latency, error counts)

#### Scenario: Report generation
- **WHEN** a scenario finishes without fatal errors
- **THEN** the harness MUST output `reports/<scenario>.json` and mark the run as `passed`
