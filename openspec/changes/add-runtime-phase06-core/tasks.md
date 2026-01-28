# Tasks: DF-006 Runtime Phase 0.6 (Alpha)

**Definition of Done Checklist**

- [x] **Spec Validation**
  - [x] Validated `proposal.md` against requirements.
  - [x] Confirmed `runtime_core` isolation strategy.

- [x] **Core Implementation**
  - [x] Define `EventEnvelope` Pydantic model with V1 constraints.
  - [x] Define `AgentRuntimeAdapter` (ARA) Protocol.
  - [x] Implement `InMemoryBus` (V0).
  - [x] Implement `RuntimeEngine` (The loop calling `receive`/`tick`).

- [x] **Adapters**
  - [x] Implement `VanillaPythonAdapter` (Default reference implementation).

- [x] **Testing & QA**
  - [x] `test_adapter_contract_compliance`
  - [x] `test_replay_idempotency`
  - [x] `test_deterministic_hash_runtime`
  - [x] `test_no_framework_dependency_in_runtime_core`
