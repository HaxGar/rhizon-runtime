# Phase 0.6 Runtime Core Freeze

This document certifies the state of the MeshForge Runtime Core at the completion of Phase 0.6.
It serves as the V0 reference for the Runtime Core.

## Frozen Artifacts

The following files constitute the immutable Runtime Core V0.
Base path: `src/meshforge_runtime/core/`

| File | SHA256 Hash |
|------|-------------|
| `__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `bus.py` | `9567c83d545ca7dee7f669b01bff1b6b14ba731c5c02f4e3cbc52f1491ca608a` |
| `engine.py` | `677b074ac2d1b768d1710f24936c6b26631e301743dd0dcd02a25e5298c7dddb` |
| `interfaces.py` | `9c40c7763b06eceb4689d508fdfc7db9da64a71b85b221b43bdbe72f92b10dbe` |
| `models.py` | `f2ba79afa848150e25e01a9d301953f34dacea0c94ef25174b7ea43be92cfc8f` |

## Verification Command

To verify the integrity of the runtime core and run the compliance tests:

```bash
export PYTHONPATH=$(pwd)/src
python3 -m pytest -q tests/test_runtime_phase06.py
```

## Release Notes

- **Version**: Phase 0.6 (Runtime Alpha)
- **Status**: Frozen / Stable
- **Capabilities**:
  - EventEnvelope V1 (Pydantic, Deterministic Serialization)
  - Agent Runtime Adapter (ARA) Protocol
  - InMemory Event Bus
  - Deterministic Runtime Engine (Time injection, Idempotency)
  - No external framework dependencies (Pure Python)

## Integration Strategy

This core is **vendored** into `meshforge-factory`. It is NOT installed via pip from a remote registry yet.
The Factory copies these exact files into generated workspaces.
