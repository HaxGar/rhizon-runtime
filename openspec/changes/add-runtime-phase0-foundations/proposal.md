# Change: MeshForge Runtime Phase 0 Foundations

## Why
MeshForge requires a hardened runtime substrate before any workspace can exist. Phase 0 establishes the SDK contracts, event envelope, artifact lifecycle, contract enforcement, observability, and simulation capabilities that every workspace must adopt.

## What Changes
- Introduce Python-first SDK contracts for events, artifacts, and agent archetypes.
- Define the canonical event envelope and namespaces (`cmd.*`, `evt.*`, `work.*`, `obs.*`).
- Specify the versioned artifact base class and lifecycle transitions.
- Describe the contract validation engine (JSON Schema, blocking semantics, version pinning).
- Establish audit logging, telemetry metrics, and correlation primitives.
- Provide a minimal simulator spec covering compliance scenarios.

## Impact
- Specs added: `event-sdk`, `artifact-sdk`, `agent-sdk`, `manager-sdk`, `governor-sdk`, `event-envelope`, `artifact-lifecycle`, `contract-engine`, `audit-telemetry`, `simulation-harness`
- Code impact: future runtime packages under `src/meshforge_runtime/**`
