# Generic CRUD Manager Contract

## 1. Overview
This spec defines the contract for a Generic CRUD Manager in the MeshForge Runtime.
The goal is to provide a framework-agnostic, deterministic way to manage state for any entity defined in the PRD/EnvSpec.

## 2. State Shape
The internal state of a Manager MUST be serializable and deterministic.

```python
State = Dict[str, EntityState]

class EntityState(TypedDict):
    id: str
    version: int  # Optimistic concurrency control
    data: Dict[str, Any]  # The actual entity attributes
    # No system timestamps (created_at/updated_at) unless passed in command payload.
```

- **Persistence**: The state is effectively an event-sourced projection or a snapshot. For Phase 0.7, we assume in-memory state initialized from empty or snapshot.

## 3. Event Contracts
All interactions are via Event Envelopes.

### 3.1. Standard Commands

#### `cmd.<object>.create`
Create a new instance of an object.
- **Payload**:
  - `id`: str (Client generated UUID recommended for idempotency, or server generated deterministically if needed. We prefer client-generated).
  - `data`: Dict[str, Any] (Attributes)
  - `idempotency_key`: str (Required)
- **Behavior**:
  - If `id` already exists:
    - If `idempotency_key` matches existing: Return success (Idempotent).
    - If `idempotency_key` differs: Return `evt.error` (Conflict).
  - If `id` new: Store object with `version=1`.

#### `cmd.<object>.update`
Update an existing instance.
- **Payload**:
  - `id`: str
  - `data`: Dict[str, Any] (Partial update / Patch)
  - `expected_version`: Optional[int] (For optimistic lock)
  - `idempotency_key`: str
- **Behavior**:
  - If `id` not found: Return `evt.error` (NotFound).
  - If `expected_version` provided and != current version: Return `evt.error` (Conflict).
  - Apply updates. Increment version.

#### `cmd.<object>.delete`
Delete an instance.
- **Payload**:
  - `id`: str
  - `idempotency_key`: str
- **Behavior**:
  - If `id` not found: Return success (Idempotent) or Error depending on strictness. (We prefer Idempotent success usually, but for explicit delete command, standard HTTP semantics say 200/204 even if gone, or 404. Let's go with: If already deleted/not found -> Success).

#### `cmd.<object>.get`
Retrieve a single instance.
- **Payload**:
  - `id`: str
- **Response**: `evt.<object>.found` or `evt.error`.

#### `cmd.<object>.list`
List instances.
- **Payload**:
  - `filters`: Optional[Dict]
  - `limit`: Optional[int]
  - `offset`: Optional[int]
- **Response**: `evt.<object>.list`

### 3.2. Standard Events (Responses)

#### `evt.<object>.created`
- **Payload**: `EntityState`

#### `evt.<object>.updated`
- **Payload**: `EntityState`

#### `evt.<object>.deleted`
- **Payload**: `{ "id": "..." }`

#### `evt.<object>.found`
- **Payload**: `EntityState`

#### `evt.<object>.list`
- **Payload**:
  - `items`: List[EntityState] (Sorted by ID for determinism)
  - `total`: int

#### `evt.error`
- **Payload**:
  - `code`: str (e.g., "not_found", "conflict", "validation_error")
  - `message`: str
  - `context`: Dict

## 4. Determinism Rules
1. **Collections**: Always sorted by ID before return.
2. **Time**: Never use `datetime.now()`. If a timestamp is needed, it must come from the Command or the Engine's logical clock (if available). For 0.7, we assume no timestamps in Core.
3. **Randomness**: No `uuid.uuid4()` inside the logic. IDs must be provided in Command.

## 5. Implementation Strategy
- **`GenericCRUDManagerAdapter`**: A Python class in `meshforge_runtime.managers` (not core, but standard lib).
- It implements the `Agent` interface (implicitly via `receive` method).
- It maps `cmd.*` to internal methods.
