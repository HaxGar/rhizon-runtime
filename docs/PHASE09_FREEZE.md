# Phase 0.9 Freeze - MAF Adapter Integration

**Date:** 2026-01-03
**Status:** Frozen
**Version:** 0.9.0

## 1. Core Purity
The Runtime Core remains strictly isolated from external framework dependencies.

- **Verification Command:**
  ```bash
  cd meshforge-runtime && grep -RInE "maf|MAF|langchain|langgraph|autogen|crewai" src/meshforge_runtime/core || true
  ```
- **Result:** ✅ Clean (No occurrences found).
- **Automated Check:** `tests/core/test_purity.py` (AST Analysis of source files) and `tests/test_runtime_phase06.py` (Subprocess Module Scan).

### Core Files Fingerprint (SHA256)
```text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  src/meshforge_runtime/core/__init__.py
9567c83d545ca7dee7f669b01bff1b6b14ba731c5c02f4e3cbc52f1491ca608a  src/meshforge_runtime/core/bus.py
90085f5af401f524cb844064ddc0097fe4f95419d3ca97651ab66c0e6994c577  src/meshforge_runtime/core/engine.py
9f5f37716e85d56e612fdb5c35c4a336a73676f3845a31debcb256209cc5e4b9  src/meshforge_runtime/core/interfaces.py
f2ba79afa848150e25e01a9d301953f34dacea0c94ef25174b7ea43be92cfc8f  src/meshforge_runtime/core/models.py
```

## 2. Adapter Isolation
Support for MAF (MeshForge Agent Framework) is implemented via a dedicated Adapter, adhering to the `AgentRuntimeAdapter` protocol.

- **File:** `src/meshforge_runtime/adapters/maf.py`
- **Isolation:** Core imports `adapters` but NOT `maf`. The adapter imports `maf` only if available.
- **Tests:** `tests/adapters/test_maf.py` validates:
  - Contract Compliance (Pure `receive` / State mutating `apply`)
  - Determinism (ID generation)
  - Replay/Recovery

## 3. Test Suite Status
The test suite is green and configured to exclude temporary dependencies.

- **Golden Command:**
  ```bash
  cd meshforge-runtime && python3 -m pytest -q
  ```
- **Result:** ✅ All 17 tests passed.
- **Configuration:** `pyproject.toml` configured to ignore `tmp_deps/`, `venv/`, etc., and adds `src` to PYTHONPATH.

## 4. Factory Integration
The Factory now supports generating MAF-enabled runtimes.

- **Profile:** `python-fastapi-maf`
- **Features:**
  - `component_toggles.maf: true`
  - Bootstraps `MAFAdapter` in `main.py`
  - Adds `maf` to `requirements.txt`
- **Verified By:** `tmp_scripts/test_maf_generation.py`
