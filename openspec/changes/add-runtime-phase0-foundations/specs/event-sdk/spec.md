## ADDED Requirements

### Requirement: Event Envelope Builder
The Event SDK SHALL expose a pure function uild_event_envelope(data: EventPayload, meta: EventMeta) that returns an immutable event envelope conforming to the runtime event contract.
It MUST generate valid UUIDv7 for message_id and un_id if not provided.

#### Scenario: Build envelope success
- **WHEN** a workspace component calls uild_event_envelope with valid metadata
- **THEN** the SDK MUST normalize field casing, inject missing defaults (e.g., ersion, 	imestamp, un_id), and return an object that passes the Event Envelope spec validation

### Requirement: Event Signature & Hashing
The Event SDK SHALL compute payload_hash using SHA3-256 over the canonical JSON serialization of payload, and MUST expose erify_payload_hash(envelope) to assert integrity before dispatch/consumption.

#### Scenario: Hash verification succeeds
- **WHEN** a consumer receives an event built by the SDK
- **THEN** calling erify_payload_hash MUST return True and MUST raise a PayloadTamperError if the digest mismatches

### Requirement: Event Type Registry
The Event SDK SHALL enforce that event 	ype fields follow the namespace prefixes cmd.*, evt.*, work.*, or obs.*, and MUST reject unknown namespaces before publishing.

#### Scenario: Reject unsupported namespace
- **WHEN** an agent attempts to emit an event whose type does not start with the allowed prefixes
- **THEN** the SDK MUST raise a InvalidEventTypeError and prevent publication

### Requirement: Correlation Utilities
The Event SDK SHALL provide helpers to generate and propagate correlation_id, causation_id, and un_id chains, guaranteeing deterministic propagation across Worker  Manager  Gateway flows.

#### Scenario: Propagate correlation identifiers
- **WHEN** a Worker agent emits a work.* event derived from a cmd.* input
- **THEN** the SDK MUST reuse the input correlation_id, propagate the input un_id (unless explicitly forking), set causation_id to the triggering message_id, and surface all three in the emitted envelope

### Requirement: Transport-Agnostic Interfaces
The Event SDK SHALL remain transport-agnostic by relying on abstract EventBus interfaces (publish, subscribe, ack) that runtime adapters (e.g., NATS, Kafka) implement without embedding vendor code in the SDK.

#### Scenario: Adapter contract enforcement
- **WHEN** a runtime component registers a new bus adapter
- **THEN** the SDK MUST verify the adapter implements the EventBus protocol (publish, subscribe, ack, nack) before activation
