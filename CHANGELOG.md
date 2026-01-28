# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.15.1] - 2026-01-28

### 🔒 SECURITY FIXES

#### **CRITICAL**
- **Fixed multi-tenant idempotency scoping** - Added tenant/workspace filtering to prevent cross-tenant duplicate detection
- **Fixed SQLite schema completeness** - Added missing EventEnvelope fields (causation_id, correlation_id, reply_to, entity_id, expected_version, schema_version)
- **Fixed AgentState mutable default** - Use Field(default_factory=dict) to prevent state pollution between instances

#### **HIGH**
- **Fixed tick() isolation** - Enforce tenant/workspace scoping on all tick() events to prevent cross-tenant leakage
- **Fixed LockManager idempotency** - Use same idempotency key as command for proper crash-recovery behavior

#### **MEDIUM**
- **Fixed violation spam** - Mark original command as processed when scope violation occurs to prevent repeated violation events

### 🏗️ TECHNICAL IMPROVEMENTS

- **Enhanced SQLite persistence** - Complete EventEnvelope serialization with backward compatibility
- **Improved isolation enforcement** - RuntimeEngine now overrides tenant/workspace on all adapter outputs
- **Better idempotency handling** - Scoped keys prevent cross-tenant interference
- **Stronger security boundaries** - Multi-tenant isolation now enforced at all levels

### 🧪 TESTING

- **Updated test expectations** - Tests now validate scoped idempotency and complete EventEnvelope persistence
- **Enhanced security tests** - Multi-tenant isolation validation across all code paths

### 📚 DOCUMENTATION

- **Updated security model** - Documented multi-tenant isolation guarantees
- **Enhanced troubleshooting guide** - Added common multi-tenant issues and solutions

## [0.15.0] - 2026-01-04

### Added
- **Security & Multi-Tenant Boundaries** - Phase 0.15 completed
- Security context enforcement in EventEnvelope
- Strict tenant/workspace isolation at runtime level
- Security violation events for audit logging
- Comprehensive security documentation

### Changed
- RuntimeEngine now validates ingress and enforces egress scoping
- SQLiteEventStore implements tenant/workspace filtering
- All adapters updated to propagate security context
- Database schema updated with security_context_json column

### Fixed
- Security context validation in EventEnvelope
- Tenant isolation in event replay
- Cross-tenant access prevention

### Security
- Mandatory security_context in all events
- Tenant/workspace boundary enforcement
- Audit trail for security violations
- Multi-tenancy guarantees validated

### Testing
- Added comprehensive security test suite (42/42 tests passing)
- Updated all existing tests for compliance
- Integration tests with security context validation

### Documentation
- `docs/SECURITY_AND_TENANCY.md` - Complete security model
- `docs/RUNTIME_INVARIANTS.md` - System guarantees
- `docs/PUBLIC_RELEASE_MANIFESTO.md` - Open source positioning

## [0.14.0] - 2025-12-15

### Added
- **Concurrency & Locking** - Phase 0.14 completed
- Event-sourced optimistic concurrency control
- Entity-level versioning system
- LockManager system agent for cooperative locking
- Conflict detection and resolution

### Changed
- RuntimeEngine implements optimistic concurrency checks
- GenericCRUDManagerAdapter tracks entity_versions
- Conflict events normalized to `evt.<agent>.conflict`
- Removed global agent_version in favor of entity-level tracking

### Fixed
- Concurrent modification detection
- Entity isolation in concurrent operations
- Version consistency across agents

### Testing
- Concurrency test suite with multi-agent scenarios
- Smoke test for conflict detection
- Integration tests with persistent volumes

## [0.13.0] - 2025-11-20

### Added
- **JetStream Durability** - Phase 0.13 completed
- NATS JetStream for both command routing and event bus
- "At-Least-Once -> Exactly-Once Effect" protocol
- Idempotency key as source of truth
- Client-side Dead Letter Queue implementation

### Changed
- RuntimeEngine re-publishes side-effects for duplicate commands
- Event store implements JetStream persistence
- Consumers handle retry logic and DLQ

### Fixed
- "Crash after Store, before Publish" scenarios
- Duplicate command processing
- Event delivery guarantees

### Testing
- Integration tests with named Docker volumes
- Durability validation under crash scenarios
- JetStream configuration testing

## [0.12.0] - 2025-10-25

### Added
- **Event Sourcing Architecture** - Phase 0.8A completed
- Agent separation into `receive()` and `apply()` methods
- RuntimeEngine handles persistence and replay
- SQLiteEventStore as default persistent store
- Strict sequential processing with asyncio.Lock

### Changed
- AgentRuntimeAdapter protocol updated
- RuntimeEngine implements event sourcing pattern
- Idempotency handled via processed_keys tracking

### Fixed
- State consistency across restarts
- Event ordering guarantees
- Idempotent command processing

## [0.11.0] - 2025-09-30

### Added
- **Synchronous Gateway Integration** - Phase 0.7 completed
- RuntimeEngine.process_event returns emitted events
- Request/Response pattern over HTTP
- GenericCRUDManagerAdapter with idempotent CRUD logic

### Changed
- Gateway integration simplified for V0
- Agent state management improved
- Error handling in gateway layer

### Fixed
- HTTP response handling
- Agent state synchronization
- Error propagation to gateway

## [0.10.0] - 2025-09-01

### Added
- **Multi-Agent Architecture** - Initial multi-agent support
- Causation and correlation ID propagation
- Multi-agent event routing
- Agent coordination primitives

### Changed
- EventEnvelope extended with multi-agent fields
- Runtime routing updated for multi-agent scenarios
- Agent discovery and registration

## [0.1.0] - 2025-07-15

### Added
- **Initial Release** - Core runtime engine
- Deterministic event processing
- Basic agent adapter protocol
- Event envelope model
- Runtime invariants implementation

### Changed
- Initial architecture established
- Core abstractions defined
- Development environment setup

---

## Version History Summary

### Phase 0.15: Security & Multi-Tenant Boundaries ✅
- **Status**: COMPLETED
- **Focus**: Enterprise-grade security and isolation
- **Outcome**: OPEN SOURCE READY

### Phase 0.14: Concurrency & Locking ✅
- **Status**: COMPLETED  
- **Focus**: Multi-agent coordination and conflict resolution
- **Outcome**: Optimistic concurrency control implemented

### Phase 0.13: JetStream Durability ✅
- **Status**: COMPLETED
- **Focus**: Reliable event delivery and persistence
- **Outcome**: Exactly-once effect guarantees

### Phase 0.8A: Event Sourcing ✅
- **Status**: COMPLETED
- **Focus**: Immutable event log and state replay
- **Outcome**: Event-sourced architecture foundation

### Phase 0.7: Synchronous Gateway ✅
- **Status**: COMPLETED
- **Focus**: HTTP integration and request/response
- **Outcome**: Simplified UI integration path

---

## Roadmap

### [1.0.0] - Planned Q2 2026
- Public open source release
- Performance optimizations
- Extended adapter ecosystem
- Community contributions integration

### [1.1.0] - Planned Q3 2026
- Advanced monitoring and observability
- Performance profiling tools
- Extended documentation
- Developer experience improvements

### [2.0.0] - Planned Q4 2026
- Distributed runtime capabilities
- Advanced security features
- Enterprise connectors
- Cloud-native deployment options
