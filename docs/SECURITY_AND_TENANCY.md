# Security & Multi-Tenancy in MeshForge Runtime

> **Note**: In this document, "Agent" refers to any **Autonomous Component** (Service, Algorithm, AI, or Human Interface) managed by the Runtime.

Phase 0.15 establishes strict security boundaries and multi-tenancy invariants for the MeshForge Runtime. This document details the architecture, invariants, and implementation of these security features.

## 1. Multi-Tenancy Model

MeshForge Runtime uses a hierarchical isolation model:
*   **Tenant**: The highest level of isolation (e.g., Organization, Company).
*   **Workspace**: A logical partition within a Tenant (e.g., Environment, Project).

### Invariants
1.  **Total Isolation**: A Runtime Engine instance is strictly bound to a single `(Tenant, Workspace)` pair.
2.  **No Cross-Talk**: It is technically impossible for an Engine to process, replay, or emit events belonging to a different Tenant or Workspace.
3.  **Scope Enforcement**: The Runtime enforces scope at both Ingress (validation) and Egress (overwrite).

## 2. Security Context

The Runtime does **not** handle Authentication (AuthN) or Authorization (AuthZ) business logic (e.g., RBAC). It delegates identity assertion to the upstream Platform/Gateway but enforces the presence of a structured **Security Context** in every event.

### Event Envelope Structure
Every `EventEnvelope` MUST contain a `security_context` field:

```json
{
  "security_context": {
    "principal_id": "user-123",
    "principal_type": "user" // or "service", "agent", "system"
  }
}
```

*   **principal_id**: Opaque identifier of the actor (User ID, Service Account ID).
*   **principal_type**: Category of the actor. Valid values: `user`, `service`, `agent`, `system`.

### Validation
The RuntimeEngine rejects any command that:
*   Lacks a `security_context`.
*   Has an invalid `principal_type`.
*   Has a `tenant` or `workspace` that does not match the Engine's configured scope.

Rejected commands result in a `evt.security.violation` event, which is persisted for audit but not processed by the Agent.

## 3. Implementation Details

### Runtime Engine Enforcement
*   **Ingress (Input)**: Before processing, the Engine checks `envelope.tenant` and `envelope.workspace`. Mismatches trigger an immediate security violation.
*   **Egress (Output)**: All events emitted by an Adapter are forcibly overwritten with the Engine's configured `tenant` and `workspace`. This prevents compromised or buggy Adapters from "spoofing" events into other scopes.

### Event Store Scoping
*   **Replay**: The `SQLiteEventStore` (and future stores) enforces strict filtering by `tenant` and `workspace` during replay. An Engine cannot load events from another scope, even if they share the same physical database.
*   **Indices**: Database schemas include indices on `(tenant, workspace)` to ensure performant scoped queries.

### Audit & Immutability
*   **Immutability**: All events, including security violations, are immutable and append-only.
*   **Audit Trail**: `evt.security.violation` events contain detailed metadata about the attempted violation (source, attempted scope, engine scope) and are preserved in the event stream for audit purposes.

## 4. Non-Goals (Out of Scope)
The Runtime explicitly does **NOT** handle:
*   User Login / Identity Provider integration (OIDC, OAuth).
*   Role-Based Access Control (RBAC) rules (e.g., "Can User A create Order?"). This is the Agent's domain.
*   API Key management.
*   Encryption at Rest (managed by infrastructure/store layer).

The Runtime provides the **structural guarantees** that allow higher layers to implement these features securely.
