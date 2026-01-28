# MeshForge Runtime — Phase 0 Backlog

| ID | Scope | Description | Status |
| --- | --- | --- | --- |
| RT-001 | OpenSpec | Finalize `add-runtime-phase0-foundations` specs and run `openspec validate --strict`. | 🔄 In progress |
| RT-002 | SDK | Scaffold Python packages for Event/Artifact/Agent SDKs once specs approved. | ⏳ Blocked (wait specs) |
| RT-003 | Observability | Implement audit & telemetry plumbing per spec (latency, errors, queue, tokens). | ⏳ Blocked |
| RT-004 | Simulator | Build deterministic simulation harness covering envelope + contract compliance. | ⏳ Blocked |

## Notes
- All work must originate from OpenSpec changes.
- No business/domain logic allowed in runtime.
