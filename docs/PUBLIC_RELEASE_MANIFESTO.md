# Public Release Manifesto & Positioning

**Date**: 2026-01-04
**Scope**: MeshForge Runtime V1.0 Preparation

## 1. Core Positioning
**MeshForge is a deterministic, event-driven runtime for orchestrating autonomous components in distributed systems.**

It provides the necessary invariants (determinism, isolation, idempotency, durability) to build reliable distributed applications.
*   **Not just for AI**: While it is an ideal substrate for Multi-Agent Systems (MAS), it is equally powerful for microservices orchestration, human-in-the-loop workflows, and deterministic state machines.
*   **"Agent" Redefined**: In MeshForge, an **Agent** is defined strictly as an **Autonomous Component**. It can be:
    *   An LLM-driven process.
    *   A deterministic algorithm.
    *   A human operator interface.
    *   A legacy service wrapper.
    *   A standard microservice.

## 2. Terminology & Naming
*   **Repo Name**: `meshforge-runtime` is validated as the public repository name. It correctly describes the artifact: a runtime engine for the MeshForge ecosystem.
*   **Agent**: Retained as a technical term in the code (`AgentRuntimeAdapter`, `AgentState`), but documented as a generic wrapper for any isolated stateful entity.
*   **LLM Neutrality**: The runtime core contains **zero** dependencies on LLMs, prompts, or generative AI. It treats all processing logic as "black box" decisions.

## 3. Architecture Sanity Check
The current architecture (Post-Phase 0.15) supports the following generic distributed patterns without AI dependency:
*   **Event-Driven Orchestration**: Via `EventEnvelope` and `RuntimeEngine` processing loop.
*   **Distributed Sagas**: Via `EventBus` (JetStream), `CorrelationID`, and `CausationID` propagation.
*   **Coordination**: Via `LockManager` (cooperative leases) and Optimistic Concurrency Control (`expected_version`).
*   **Security & Multi-Tenancy**: Via strict `Tenant/Workspace` isolation at Ingress/Egress/Storage layers.

## 4. Release Boundary (Phase 0.15)
Phase 0.15 "Security & Multi-Tenant Boundaries" marks the completion of the Open Source Runtime Core.

**Out of Scope for `meshforge-runtime` (Platform/Paid features):**
*   LLM Routing & Model Gateways.
*   Agent Marketplaces.
*   Advanced Protocol Adapters (MCP beyond basics).
*   "Smart" Capabilities (RAG, Memory embedding, etc.).
*   User Interfaces (Console, Dashboards).

## 5. Readiness Status
*   **Code**: Frozen & Tested (42/42 Passing).
*   **Docs**: Updated to reflect generic positioning.
*   **Invariants**: Validated via integration tests.

**MeshForge Runtime is ready for public release as a foundational distributed systems primitive.**
