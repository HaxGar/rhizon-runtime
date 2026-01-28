## ADDED Requirements

### Requirement: Canonical Event Envelope Fields
The runtime event envelope SHALL contain the following mandatory fields: `workspace_id`, `tenant_id`, `message_id`, `type`, `version`, `correlation_id`, `causation_id`, `timestamp`, `payload_hash`, `payload`, `actor_id`.

#### Scenario: Envelope validation success
- **WHEN** an event passes through the runtime bus
- **THEN** validation MUST confirm all required fields exist, with `timestamp` in RFC3339 format and `message_id` UUIDv7

### Requirement: Payload Hash Semantics
`payload_hash` SHALL be computed via SHA3-256 over canonical JSON (sorted keys, UTF-8, no whitespace). Envelopes MUST include `payload_hash` for integrity, and runtime consumers MUST discard events whose hash does not match the payload.

#### Scenario: Hash mismatch rejection
- **WHEN** a consumer detects a mismatched `payload_hash`
- **THEN** it MUST reject the event, log an audit entry with severity `high`, and emit `evt.guardrail.payload-tamper`

### Requirement: Correlation & Causation Rules
`correlation_id` SHALL remain constant for the entire workflow initiated by a `cmd.*` event. `causation_id` SHALL reference the immediate predecessor event’s `message_id`. Gateways MUST initialize both IDs for ingress events.

#### Scenario: Chain propagation
- **WHEN** a manager emits an `evt.*` in response to `work.*`
- **THEN** it MUST preserve `correlation_id` and set `causation_id` to the originating `work.*` `message_id`

### Requirement: Version Semantics
`version` SHALL represent the event schema version (semver). Producers MUST bump `version` when payload shape changes. Runtime MUST reject events with versions not declared in workspace contracts.

#### Scenario: Unsupported version rejection
- **WHEN** a worker receives an event with `version` not listed in the workspace `contracts.yaml`
- **THEN** it MUST raise `UnsupportedEventVersion` and emit `evt.guardrail.contract-violation`
