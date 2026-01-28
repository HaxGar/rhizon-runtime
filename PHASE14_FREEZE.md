# Phase 0.14 Freeze: Concurrency & Locking

**Status**: Frozen ❄️
**Date**: Jan 4, 2026
**Version**: 0.14.0

## 1. Overview
This phase introduces robust concurrency controls to MeshForge Runtime, enabling safe distributed state management without blocking locks in the core path.

## 2. Key Features

### 2.1. Optimistic Concurrency (Anti-Double Write)
- **Granularity**: **Entity-Level**. Updates to one entity do not block or conflict with others handled by the same agent.
- **Mechanism**:
    - Commands sending `expected_version` + `entity_id` trigger a check against the *current entity version*.
    - Mismatches reject the command and emit a conflict event.
- **Protocol**:
    - **Command**: Includes `expected_version` (int) and `entity_id` (str).
    - **Success**: `evt.<agent>.<action>` (e.g., `evt.inventory.updated`). Payload includes new `entity_version`.
    - **Failure**: `evt.<agent>.conflict`. Payload includes `expected_version`, `current_version`, `reason`.

### 2.2. System Lock Manager
- **Role**: Distributed cooperative locking for external resources or long-running sagas.
- **Agent**: `sys_lock_manager`.
- **Capabilities**: `acquire` (with TTL), `release`, `refresh`.
- **Events**: `evt.lock.acquired`, `evt.lock.denied`, `evt.lock.released`, `evt.lock.expired`.

## 3. Breaking Changes & Standards

### 3.1. Versioning Terminology
- **REMOVED**: `agent_version` (Global sequence number) is no longer exposed or used for concurrency.
- **ADDED**: `entity_version` (Per-entity sequence number).
- **Payloads**: CRUD events (`created`, `updated`) now strictly return `entity_version`.

### 3.2. Event Subjects
- **Conflict Events**: Normalized to `evt.<agent_name>.conflict` (e.g., `evt.inventory.conflict`).
    - *Previous behavior (fixed)*: `evt.<entity_uuid>.conflict`.

### 3.3. Docker Compose
- Removed obsolete `version: '3.x'` keys to comply with Docker Compose V2 standards.

## 4. Validation
- **Unit Tests**: `tests/test_concurrency.py` covers isolation and conflict logic.
- **Integration**: `smoke_test_concurrency.py` validates end-to-end NATS flow and Lock Manager.

## 5. Next Steps (Phase 0.15)
- **Saga Orchestrator**: Leveraging `entity_version` and locks to drive complex transactions.
