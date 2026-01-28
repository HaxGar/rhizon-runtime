## ADDED Requirements

### Requirement: Versioned Artifact Base Class
The Artifact SDK SHALL provide an abstract `Artifact` base class with immutable attributes `artifact_id`, `workspace_id`, `version`, `status`, `payload`, and `metadata`. Version increments SHALL be monotonic and derive from semantic versioning (major.minor.patch).

#### Scenario: Artifact derivation
- **WHEN** a concrete artifact subclass calls `Artifact.new_version(prev_artifact, payload)`
- **THEN** the SDK MUST increment the patch number by default and snapshot the prior artifact’s metadata into a lineage trail

### Requirement: Lifecycle State Machine
The Artifact SDK SHALL encode the lifecycle `draft → published → challenged → revised → accepted → archived` and MUST enforce valid transitions through explicit methods (e.g., `publish()`, `challenge()`, `revise()`, `accept()`, `archive()`).

#### Scenario: Invalid transition rejected
- **WHEN** a client attempts to call `accept()` on an artifact that is still `draft`
- **THEN** the SDK MUST raise `InvalidArtifactTransition` and leave the artifact unchanged

### Requirement: Artifact Integrity Proofs
The Artifact SDK SHALL compute `artifact_hash` (SHA3-256 over canonical payload+metadata) and MAY publish it alongside events. The SDK MUST verify hashes before accepting artifacts into persistent storage.

#### Scenario: Integrity verification
- **WHEN** an artifact is loaded from storage
- **THEN** the SDK MUST recompute the hash and raise `ArtifactIntegrityError` if mismatched

### Requirement: Persistence Abstraction
The Artifact SDK SHALL define a `ArtifactRepository` protocol with async methods `get`, `save`, `list_versions`, and `lock_for_update`, allowing runtime adapters to plug different stores without altering SDK code.

#### Scenario: Repository contract compliance
- **WHEN** a runtime registers a custom repository implementation
- **THEN** the SDK MUST validate method signatures and raise `InvalidRepositoryAdapter` if the contract is incomplete
