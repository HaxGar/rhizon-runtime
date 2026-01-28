# Phase 0.11 Freeze: Observability (OTEL)

**Status:** LOCKED 🔒
**Date:** 2026-01-03
**Version:** 0.6.0 (Runtime)

## 1. Validation "Golden" Command

### Local Environment (WSL/No-Venv workaround)
Due to system package restrictions (`externally-managed-environment`), dependencies were installed in `tmp_deps`.

```bash
export PYTHONPATH="$(pwd)/src:$(pwd)/tmp_deps" 
cd meshforge-runtime 
python3 -m pytest
```

### Standard CI/CD Environment
In a standard environment (venv or container), `tmp_deps` is NOT required. Dependencies are defined in `pyproject.toml`.

```bash
pip install ".[test]"
pytest
```

## 2. Core Integrity (Hashes)

The following files ensure the core runtime remains deterministic and correctly instrumented.

| File | SHA256 Hash | Notes |
|------|-------------|-------|
| `src/meshforge_runtime/core/engine.py` | `1477e1178391a8ad09e27c667e22e78b3e0cb136a1644aa8311d3038402eef1d` | Instrumenté OTEL (Spans/Metrics) |
| `src/meshforge_runtime/core/telemetry.py` | `71f58f528279fc3301aebb25ecf798c55def29daac02006f37c01fb847208012` | Telemetry Manager (OTLP/Console) |
| `src/meshforge_runtime/core/models.py` | `a49f3d27cccbb7a8ba5c5404fae9b03710711acea56cdca16e7218f8bac270be` | EventEnvelope V1.1 (Multi-Agent) |

## 3. Dependency Note (tmp_deps)
The `tmp_deps` folder is a **local artifact** to bypass `pip install` restrictions on the host. It should **NOT** be committed to git (it is likely gitignored).
CI pipelines must install dependencies from `pyproject.toml` natively.

## 4. Key Achievements
- **Full OTEL Instrumentation:** `process_event` is the root span. Child spans for `adapter.receive`, `store.append`, `bus.publish`.
- **Determinism Guaranteed:** Metrics and Traces do not leak into `AgentState` hash.
- **No-Op Default:** Runtime works without crashing if no telemetry is configured.
