## ADDED Requirements

### Requirement: Lifecycle Definition
Artifacts SHALL progress through the states `draft`, `published`, `challenged`, `revised`, `accepted`, `archived`. No other statuses are permitted in Phase 0.
The `archived` state SHALL indicate termination of an artifact lifecycle and SHALL NOT imply rejection.

#### Scenario: Happy path progression
- **WHEN** an artifact is created
- **THEN** it MUST start in `draft`, MAY transition to `published`, MAY be `challenged`, and MUST eventually reach either `accepted` or `archived`

### Requirement: Transition Authorization
Each lifecycle transition SHALL be restricted to specific agent roles:
- `publish()` MAY only be invoked by a WorkerAgent
- `challenge()` MAY only be invoked by a ManagerAgent
- `revise()` MAY only be invoked by a WorkerAgent
- `accept()` MAY only be invoked by the Governor
- `archive()` MAY be invoked by a ManagerAgent or the Governor

The runtime MUST reject transitions invoked by unauthorized roles.

#### Scenario: Unauthorized transition blocked
- **WHEN** a WorkerAgent attempts to `accept()` an artifact
- **THEN** the runtime MUST reject the transition with `UnauthorizedRole`

### Requirement: Transition Guardrails
Each state transition SHALL be implemented via explicit SDK methods that validate prerequisites:
- `publish()` requires contract validation
- `challenge()` requires an evidence payload (JSON object) included in the event, hashed via `payload_hash`, and immutable (any correction requires a new `challenge()` invocation)
- `revise()` requires referencing the challenged artifact
- `accept()` requires governor clearance
- `archive()` requires explicit invocation by a ManagerAgent OR Governor (both audit logged)

#### Scenario: Invalid transition blocked
- **WHEN** a component attempts to `revise()` an artifact that is not `challenged`
- **THEN** the runtime MUST raise `InvalidLifecycleTransition` and emit `evt.guardrail.artifact-lifecycle`

### Requirement: Revision Lineage
Artifacts in state `revised` MUST reference a `parent_artifact_id`.
The referenced parent artifact MUST be in state `challenged`.

#### Scenario: Lineage enforcement
- **WHEN** `revise()` is called
- **THEN** the SDK MUST verify the parent is `challenged` and link the new artifact to it

### Requirement: Auditability of Lifecycle Moves
Every transition SHALL emit an `obs.artifact.lifecycle` event containing actor metadata, timestamps, previous/next states, and artifact hashes.

#### Scenario: Lifecycle audit event created
- **WHEN** `publish()` succeeds
- **THEN** the runtime MUST emit `obs.artifact.lifecycle` with `transition=publish`, `actor_id`, `artifact_id`, and `payload_hash`
