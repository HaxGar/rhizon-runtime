# Tasks - Phase 0.13: JetStream & Durability

## Implementation
- [x] Implement `JetStreamEventBus` (Publish to JetStream subjects) <!-- id: 0 -->
- [x] Implement `JetStreamCommandRouter` (Publish to JetStream subjects) <!-- id: 1 -->
- [x] Update `RuntimeEngine` to support "At-Least-Once" protocol:
    - [x] Check Idempotency (EventStore) before processing. <!-- id: 2 -->
    - [x] Store event BEFORE Apply. <!-- id: 3 -->
    - [x] ACK after Apply + Side-Effects. <!-- id: 4 -->
- [x] Configure JetStream Streams (`MESHFORGE_EVENTS`, `MESHFORGE_COMMANDS`) in initialization. <!-- id: 5 -->

## Testing
- [x] `tests/test_durability_jetstream.py`:
    - [x] Test Crash before ACK (Redelivery handled idempotently). <!-- id: 6 -->
    - [x] Test Crash after Publish/before Store. <!-- id: 7 -->
    - [x] Test Restart/Replay hash consistency. <!-- id: 8 -->
- [x] `docker-compose.jetstream.yml` with NATS JetStream enabled. <!-- id: 9 -->

# Tasks - Phase 0.14: Concurrency & Locking

## Core: Optimistic Concurrency
- [x] Define `evt.<entity>.conflict` in Core Models. <!-- id: 10 -->
- [x] Update `EventEnvelope` / Command to support `expected_version` and `entity_id`. <!-- id: 11 -->
- [x] Implement `RuntimeEngine` entity-level version check (Anti-Double Write). <!-- id: 12 -->
    - [x] Retrieve current entity version from Adapter State (`entity_versions`).
    - [x] Compare with `expected_version`.
    - [x] Reject if mismatch & publish conflict event (`evt.<agent>.conflict`).

## Runtime Module: LockManager (Optional)
- [x] Create `LockManagerAdapter` (System Agent). <!-- id: 13 -->
- [x] Implement `cmd.lock.acquire` logic with TTL. <!-- id: 14 -->
- [x] Implement `cmd.lock.release` logic. <!-- id: 15 -->
- [x] Implement `cmd.lock.refresh` logic. <!-- id: 16 -->
- [x] Add `evt.lock.*` events. <!-- id: 17 -->

## Factory & Integration
- [x] Add `lock_manager` toggle to Factory Profiles. <!-- id: 18 -->
- [x] Wire `LockManagerAdapter` in `RuntimeGenerator` if enabled. <!-- id: 19 -->
- [x] Create `tests/test_concurrency.py` (Unit/Integration). <!-- id: 20 -->
- [x] Create `tests/test_lock_manager.py`. <!-- id: 21 -->
- [x] Smoke Test in `meshforge-env-*` demonstrating concurrency conflict. <!-- id: 22 -->

# Tasks - Phase 0.15: Security & Multi-Tenant Boundaries

## Core: Security & Isolation
- [x] Update `EventEnvelope` to include `security_context` (principal_id, principal_type). <!-- id: 23 -->
- [x] Implement strict `tenant` / `workspace` validation in `RuntimeEngine`. <!-- id: 24 -->
- [x] Implement `security_context` validation in `RuntimeEngine`. <!-- id: 25 -->
- [x] Define and implement `evt.security.violation` for context failures. <!-- id: 26 -->

## Scoping & Boundaries
- [x] Verify/Enforce `SQLiteEventStore` strict scoping by Tenant/Workspace. <!-- id: 27 -->
- [x] Enforce JetStream Subject strict scoping (already structured, verify enforcement). <!-- id: 28 -->

## Testing & Documentation
- [x] Create `tests/test_security_tenancy.py` (Isolation tests). <!-- id: 29 -->
- [x] Create `docs/SECURITY_AND_TENANCY.md`. <!-- id: 30 -->
- [x] Create `docs/RUNTIME_INVARIANTS.md`. <!-- id: 31 -->
- [x] Generate `PHASE15_FREEZE.md`. <!-- id: 32 -->
