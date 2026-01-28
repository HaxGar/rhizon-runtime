# Rhizon Runtime

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)
[![Documentation](https://img.shields.io/badge/docs-latest-brightgreen.svg)](docs/)

> **Rhizon Runtime - The root of deterministic systems**

🌱 **Rhizon Runtime** is the world's first deterministic, event-driven runtime for orchestrating autonomous components in distributed systems. Like the underground root system that nourishes a forest, Rhizon provides the invisible foundation that guarantees mathematical certainty for distributed coordination.

Built on the principle that **autonomous systems deserve deterministic foundations**, Rhizon Runtime ensures that every event, every decision, every interaction follows mathematical guarantees of consistency, reliability, and auditability.

## 🚀 Key Features

- **🎯 Deterministic by Design**: Given the same inputs, the system produces the same outputs - mathematical guarantee
- **🔒 Enterprise-Grade Security**: Multi-tenant isolation with strict boundary enforcement
- **⚡ Event-Driven Architecture**: Loose coupling, infinite scalability, fault tolerance
- **🔄 Exactly-Once Processing**: Idempotency guarantees with no duplicate side effects
- **🏛️ Optimistic Concurrency**: Entity-level versioning with conflict detection
- **📊 Built-in Observability**: OpenTelemetry integration and comprehensive audit trails
- **🔧 Platform Agnostic**: Zero dependency on specific LLMs, frameworks, or cloud providers

## 🏆 Why Rhizon Runtime?

**Unlike traditional runtimes, Rhizon provides mathematical guarantees:**

| Feature | Traditional Runtimes | Rhizon Runtime |
|---------|-------------------|------------------|
| **Determinism** | ❌ Non-deterministic | ✅ Mathematically guaranteed |
| **Concurrency** | ❌ Race conditions | ✅ Optimistic locking |
| **Isolation** | ❌ Tenant leakage | ✅ Strict boundaries |
| **Processing** | ❌ At-least-once | ✅ Exactly-once effect |
| **Audit Trail** | ❌ Limited visibility | ✅ Complete event sourcing |

## Core Philosophy

*   **Deterministic Foundation**: Given the same inputs, the system must produce the same outputs.
*   **"Agent" as Autonomous Component**: An Agent is any isolated entity with state and behavior (AI, Service, Tool, Human Interface).
*   **Platform Agnostic**: Zero dependency on specific LLMs, frameworks, or cloud providers in the core.
*   **Strict Isolation**: Multi-tenant by design with enforced boundaries at the runtime level.

## Scope & Non-Goals

-   **Included:** Runtime Engine, Event Envelopes, Concurrency Control (Optimistic Locking), Event Sourcing, Telemetry (OTEL), and Security Context enforcement.
-   **Excluded:** Domain-specific business logic, UI, User Management, or "Smart" AI capabilities (RAG, Prompt Engineering). These belong in higher layers or specific agent implementations.

## Directory Structure

| Path | Usage |
| --- | --- |
| `src/rhizon_runtime/core` | The pure, framework-agnostic runtime kernel. |
| `src/rhizon_runtime/adapters` | Connectors for infrastructure (NATS, SQLite, etc.). |
| `openspec/` | Authoritative specifications and change management. |
| `docs/` | Architecture decision records and invariants. |
| `tests/` | Comprehensive integration and contract tests. |

## Architecture: Kernel vs Adapters

To ensure the runtime remains lightweight and agnostic, we distinguish between the **Core Kernel** and **Adapters**.

### 1. The Kernel (`src/rhizon_runtime/core`)
**Status**: Frozen & Mandatory.
The pure, deterministic heart of the system. It contains:
*   **RuntimeEngine**: The orchestration loop (Ingress -> Process -> Egress).
*   **Models**: `EventEnvelope`, `SecurityContext`.
*   **Interfaces**: Protocols for `EventBus`, `EventStore`, `Router`.
*   **Invariants**: Determinism, Idempotency, Tenancy enforcement.
*   **Dependencies**: Zero I/O, pure Python.

### 2. Official Adapters (`src/rhizon_runtime/adapters`, `persistence`)
**Status**: Bundled "Batteries Included".
Production-grade implementations of the Kernel interfaces provided for immediate use.
*   **Transport**: NATS JetStream (`JetStreamEventBus`, `JetStreamRouter`).
*   **Persistence**: SQLite (`SQLiteEventStore`).
*   **System Agents**: Lock Manager (`LockManagerAdapter`).

### 3. Reference Implementations (`src/rhizon_runtime/gateway`, `managers`)
**Status**: Examples / Starter Kits.
These components demonstrate how to integrate with the runtime but are **optional** and swappable.
*   **HTTP Gateway**: `fastapi_app.py` (Reference implementation of an HTTP Ingress).
*   **CRUD Manager**: `crud.py` (Reference implementation of a Stateful Entity adapter).
*   **Framework Integrations**: `maf.py` (Example adapter for Rhizon Agent Framework).

## Workflow Guardrails

1.  **Spec-Driven:** Every change starts with `openspec/changes/<change-id>/`.
2.  **Python-First:** Targets Python 3.11+, strict typing, and explicit dependency pinning.
3.  **No Business Logic:** Runtime agents expose SDK abstractions only; business behavior lives in workspace repos.
4.  **Isolation:** One workspace = one stack. Never share queues, databases, or credentials across boundaries.

## 🚀 Quick Start

### Installation

```bash
# Using Poetry (recommended)
poetry add rhizon-runtime

# Using pip
pip install rhizon-runtime
```

### Basic Usage

```python
from rhizon_runtime.core.engine import RuntimeEngine
from rhizon_runtime.core.models import EventEnvelope
from rhizon_runtime.adapters.jetstream_bus import JetStreamEventBus
from rhizon_runtime.adapters.sqlite_store import SQLiteEventStore

# Create your agent
class MyAgent:
    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        # Process incoming event
        return [
            EventEnvelope(
                type="evt.response.success",
                payload={"result": "processed"},
                # ... other required fields
            )
        ]
    
    def apply(self, envelope: EventEnvelope) -> None:
        # Apply event to state
        pass
    
    def get_state(self) -> AgentState:
        return AgentState(version=1, data={})

# Initialize runtime
engine = RuntimeEngine(
    agent_id="my-agent",
    adapter=MyAgent(),
    bus=JetStreamEventBus(),
    store=SQLiteEventStore("events.db"),
    deterministic=True
)

# Process events
events = engine.process_event(incoming_event)
```

### Development Setup

```bash
# Clone the repository
git clone https://github.com/rhizon/rhizon-runtime.git
cd rhizon-runtime

# Set up development environment
poetry install
poetry run pytest

# Run integration tests
docker-compose up -d
poetry run pytest tests/integration/
```

## 📚 Documentation

- **[Architecture Guide](docs/ARCHITECTURE.md)** - Deep dive into runtime architecture
- **[Invariants & Guarantees](docs/RUNTIME_INVARIANTS.md)** - Mathematical guarantees explained
- **[Security & Tenancy](docs/SECURITY_AND_TENANCY.md)** - Multi-tenant security model

*📝 More documentation coming soon as the community grows!*

## 🏗️ Architecture

Rhizon Runtime follows a strict separation between **Core** and **Adapters**:

### Core (`src/rhizon_runtime/core`)
The pure, deterministic heart of the system:
- **RuntimeEngine**: Main orchestration loop
- **EventEnvelope**: Standardized event format
- **Interfaces**: Protocol definitions
- **Invariants**: Mathematical guarantees

### Adapters (`src/rhizon_runtime/adapters`)
Production-grade implementations:
- **NATS JetStream**: Event bus and routing
- **SQLite**: Event store implementation  
- **LockManager**: Cooperative locking system

## 🔧 Use Cases

### AI Agent Orchestration
```python
# Coordinate multiple AI agents with deterministic guarantees
class AgentOrchestrator:
    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        # Coordinate between LLM agents, tools, and human interfaces
        return orchestrate_agents(envelope.payload)
```

### Microservices Coordination
```python
# Reliable microservice communication with exactly-once processing
class ServiceCoordinator:
    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        # Handle service-to-service communication
        return process_service_request(envelope.payload)
```

### Human-in-the-Loop Workflows
```python
# Deterministic workflow automation with human approval steps
class WorkflowEngine:
    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        # Manage complex business workflows
        return advance_workflow(envelope.payload)
```

## 🧪 Testing

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=rhizon_runtime

# Run integration tests (requires Docker)
docker-compose up -d
poetry run pytest tests/integration/

# Run property-based tests
poetry run pytest tests/property/
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Workflow
1. Fork the repository
2. Create a feature branch
3. Write tests for your changes
4. Ensure all tests pass
5. Submit a pull request

### Areas for Contribution
- **New Adapters**: Kafka, Redis, PostgreSQL, etc.
- **Performance**: Optimization and benchmarking
- **Documentation**: Examples, tutorials, API docs
- **Tools**: CLI tools, monitoring dashboards

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **NATS Project**: For the excellent JetStream messaging system
- **Event Sourcing Community**: For the foundational patterns
- **OpenTelemetry**: For observability standards
- **Our Contributors**: For making this project possible

## 📞 Get Help

- **[GitHub Issues](https://github.com/rhizon/rhizon-runtime/issues)**: Report bugs or request features
- **[GitHub Discussions](https://github.com/rhizon/rhizon-runtime/discussions)**: Ask questions and share ideas

*📝 Community channels coming soon as the project grows!*

---

**Built with ❤️ by the Rhizon team**

*Rhizon Runtime: Deterministic foundations for autonomous systems*
