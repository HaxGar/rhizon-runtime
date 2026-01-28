# MeshForge Runtime Invariants

> **Note**: In this document, "Agent" refers to any **Autonomous Component** (Service, Algorithm, AI, or Human Interface) managed by the Runtime.

This document defines the core technical invariants that MeshForge Runtime guarantees. These invariants are non-negotiable and form the foundation of the system's reliability, security, and determinism.

## 1. Determinism
*   **Definition**: Given the same initial state and the same sequence of input events, an Agent MUST always produce the exact same sequence of output events and internal state.
*   **Mechanism**:
    *   Logical Time injection (Engine controls `now`).
    *   No side-effects allowed in `Agent.receive()` (pure decision).
    *   Strict ordering of event processing.
*   **Verification**: State Hash checks in test suites (`test_deterministic_hash_runtime`).

## 2. Idempotency (Exactly-Once Effect)
*   **Definition**: Processing the same command multiple times MUST result in the same state change and side-effects as processing it once.
*   **Mechanism**:
    *   `idempotency_key` tracking in `EventStore`.
    *   RuntimeEngine checks `processed_keys` before invoking Adapter.
    *   Duplicate commands trigger re-publication of previous side-effects (handling "Crash after Store, before Publish") without re-executing logic.
*   **Verification**: `test_replay_idempotency` and `test_durability_jetstream`.

## 3. Isolation (Multi-Tenancy)
*   **Definition**: Resources and events belonging to one Tenant/Workspace MUST NOT be accessible or mutable by another.
*   **Mechanism**:
    *   Strict Scoping in `RuntimeEngine` (Ingress validation, Egress enforcement).
    *   Scoped Replay in `EventStore`.
    *   Security Context propagation.
*   **Verification**: `test_security_tenancy`.

## 4. Durability (At-Least-Once Delivery)
*   **Definition**: Once an event is acknowledged by the system, it MUST NOT be lost, even in the event of a crash.
*   **Mechanism**:
    *   NATS JetStream (Durable Streams/Consumers).
    *   Write-Ahead Log (WAL) pattern: Store -> Apply -> Publish -> Ack.
    *   Client-side Dead Letter Queue (DLQ) for poison pills.
*   **Verification**: `test_durability_crash_before_ack`.

## 5. Concurrency (Anti-Double Write)
*   **Definition**: Concurrent modifications to the same Entity MUST be serialized or detected as conflicts.
*   **Mechanism**:
    *   Optimistic Concurrency Control (OCC) via `expected_version`.
    *   Entity-level version tracking.
    *   `RuntimeEngine` serializes processing via `asyncio.Lock` (per instance).
*   **Verification**: `test_concurrency` and `smoke_test_concurrency`.

## 6. Auditability
*   **Definition**: Every state change MUST be traceable to a specific Event, Actor, and Cause.
*   **Mechanism**:
    *   Event Sourcing (State is a derivation of Events).
    *   Immutable Event Log.
    *   `causation_id`, `correlation_id`, and `trace_id` propagation.
    *   Mandatory `security_context`.

---

## Non-Goals (Runtime Layer)
The Runtime strictly avoids:
*   **Business Logic**: No baked-in workflows or domain rules.
*   **UI/Presentation**: Headless operation only.
*   **User Management**: No auth databases or user tables.
*   **External Connectors**: No direct DB/API calls from Core (handled by specialized Adapters).
