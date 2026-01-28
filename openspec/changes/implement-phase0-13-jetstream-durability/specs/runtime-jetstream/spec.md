# Runtime JetStream Specification (Phase 0.13)

## Overview
Integration of NATS JetStream to provide **Durable**, **At-Least-Once** messaging with **Exactly-Once Effects** via persistent idempotency.

## Architecture

### Streams
Two primary streams are defined:
1. **`MESHFORGE_EVENTS`**: Subjects `evt.>`
   - Storage: File (Durable)
   - Retention: Limits/WorkQueue (depending on use case, usually Limits for events)
2. **`MESHFORGE_COMMANDS`**: Subjects `cmd.>`
   - Storage: File (Durable)
   - Retention: WorkQueue (Ensures only one worker processes a command if scaled)

### Consumers
Agents use **Durable Pull Consumers**.
- Name: `{agent_name}_consumer`
- Filter: Subject matching agent interest (e.g. `cmd.default.demo.{agent}.>`)
- AckPolicy: `Explicit`
- MaxDeliveries: 5 (then DLQ)

## Reliability & Idempotency Protocol

To guarantee **Exactly-Once Effects** despite **At-Least-Once Delivery**:

1. **Receive**: Runtime pulls message from JetStream.
2. **Deduplicate**:
   - Check `EventStore` for `idempotency_key`.
   - **IF Found**:
     - Log "Duplicate detected".
     - **ACK** immediately (Message was processed but ACK failed previously).
     - **STOP**.
3. **Persist (WAL)**:
   - Append Event/Command to Local `EventStore` (SQLite).
   - *Commit transaction*.
4. **Apply**:
   - Pass envelope to `AgentAdapter.receive()` / `apply()`.
   - Generate side-effects (outbound messages).
5. **Publish Side-Effects**:
   - Publish resulting events to JetStream.
6. **ACK**:
   - Send `Ack` to JetStream.

### Crash Scenarios

| Crash Point | Consequence | Recovery |
|---|---|---|
| Before Step 3 (Persist) | Message not in Store, not ACKed. | JetStream Redelivers. Runtime processes normally. |
| After Step 3, Before Step 6 (ACK) | Message in Store, not ACKed. | JetStream Redelivers. Runtime sees ID in Store (Step 2). ACKs immediately. No double effect. |

## Dead Letter Queue (DLQ)
Messages exceeding `MaxDeliveries` are not ACKed but terminally failed (or moved by NATS policy if configured, otherwise we implement application-level DLQ logic if needed, but NATS Terminate is preferred for bad poison pills).
- We will configure a "Failed" subject or use NATS advisory events.
- For Phase 0.13: If `MaxDeliveries` reached, NATS handles it (stops delivering). Monitoring should alert.

## Determinism
- **TraceID/SpanID** MUST be propagated.
- **Logical Timestamp**: Runtime injects `ts` if missing, but preferably respects upstream `ts`.
- **State Hash**: Calculated solely from `EventStore` content, ensuring replay yields same hash regardless of redeliveries.
