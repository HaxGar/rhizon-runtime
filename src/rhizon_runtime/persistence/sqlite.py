import sqlite3
import json
from typing import List, Optional, Dict, Any
from pathlib import Path
from rhizon_runtime.core.models import EventEnvelope
from rhizon_runtime.core.interfaces import EventStoreAdapter

class SQLiteEventStore(EventStoreAdapter):
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self):
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    ts INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    schema_version TEXT DEFAULT '1.0',
                    trace_id TEXT,
                    span_id TEXT,
                    tenant TEXT,
                    workspace TEXT,
                    actor_json TEXT,
                    payload_json TEXT,
                    idempotency_key TEXT,
                    source_json TEXT,
                    causation_id TEXT,
                    correlation_id TEXT,
                    reply_to TEXT,
                    entity_id TEXT,
                    expected_version INTEGER,
                    security_context_json TEXT,
                    created_at INTEGER DEFAULT (cast(strftime('%s','now') as int))
                )
            """)
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type)")
            # Idempotency check index
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_idempotency ON events(idempotency_key)")
            # Scoping index
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_scope ON events(tenant, workspace)")

    def append(self, event: EventEnvelope) -> None:
        with self._conn:
            self._conn.execute("""
                INSERT INTO events (id, ts, type, schema_version, trace_id, span_id, tenant, workspace, actor_json, payload_json, idempotency_key, source_json, causation_id, correlation_id, reply_to, entity_id, expected_version, security_context_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                event.id,
                event.ts,
                event.type,
                event.schema_version,
                event.trace_id,
                event.span_id,
                event.tenant,
                event.workspace,
                json.dumps(event.actor),
                json.dumps(event.payload),
                event.idempotency_key,
                json.dumps(event.source),
                event.causation_id,
                event.correlation_id,
                event.reply_to,
                event.entity_id,
                event.expected_version,
                json.dumps(event.security_context)
            ])

    def append_batch(self, events: List[EventEnvelope]) -> None:
        if not events:
            return
        
        data = []
        for e in events:
            data.append((
                e.id,
                e.ts,
                e.type,
                e.schema_version,
                e.trace_id,
                e.span_id,
                e.tenant,
                e.workspace,
                json.dumps(e.actor),
                json.dumps(e.payload),
                e.idempotency_key,
                json.dumps(e.source),
                e.causation_id,
                e.correlation_id,
                e.reply_to,
                e.entity_id,
                e.expected_version,
                json.dumps(e.security_context)
            ))
        
        try:
            with self._conn:
                self._conn.executemany("""
                    INSERT INTO events (
                        id, ts, type, schema_version, trace_id, span_id, tenant, workspace, 
                        actor_json, payload_json, idempotency_key, source_json, causation_id, correlation_id, reply_to, entity_id, expected_version, security_context_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, data)
        except sqlite3.IntegrityError as e:
            # Check for duplicate ID or idempotency key collision
            # For now, just raise generic error, caller handles logic
            raise e

    def replay(self, from_offset: int = 0, filters: Optional[Dict[str, Any]] = None) -> List[EventEnvelope]:
        # 'from_offset' in this simple store will map to LIMIT/OFFSET or TS?
        # Typically replay means "all events". 'from_offset' implies sequence number.
        # SQLite ROWID is a hidden autoinc. We can use that as offset.
        
        query = "SELECT * FROM events WHERE rowid > ?"
        params = [from_offset]
        
        # Strict Scoping Filters
        if filters:
            if "tenant" in filters:
                query += " AND tenant = ?"
                params.append(filters["tenant"])
            if "workspace" in filters:
                query += " AND workspace = ?"
                params.append(filters["workspace"])
                
        query += " ORDER BY rowid ASC"

        cursor = self._conn.execute(query, params)
        rows = cursor.fetchall()
        
        return [self._row_to_envelope(row) for row in rows]

    def get_by_idempotency_key(self, key: str, tenant: Optional[str] = None, workspace: Optional[str] = None) -> List[EventEnvelope]:
        if tenant and workspace:
            query = "SELECT * FROM events WHERE idempotency_key = ? AND tenant = ? AND workspace = ? ORDER BY rowid ASC"
            cursor = self._conn.execute(query, [key, tenant, workspace])
        else:
            query = "SELECT * FROM events WHERE idempotency_key = ? ORDER BY rowid ASC"
            cursor = self._conn.execute(query, [key])
        rows = cursor.fetchall()
        return [self._row_to_envelope(row) for row in rows]

    def _row_to_envelope(self, row) -> EventEnvelope:
        # id(0), ts(1), type(2), schema_version(3), trace(4), span(5), tenant(6), workspace(7), actor(8), payload(9), idem(10), source(11), causation(12), correlation(13), reply_to(14), entity(15), expected_version(16), security_context(17), created_at(18)
        return EventEnvelope(
            id=row[0],
            ts=row[1],
            type=row[2],
            schema_version=row[3] if len(row) > 3 and row[3] else "1.0",
            trace_id=row[4],
            span_id=row[5],
            tenant=row[6],
            workspace=row[7],
            actor=json.loads(row[8]),
            payload=json.loads(row[9]),
            idempotency_key=row[10],
            source=json.loads(row[11]),
            causation_id=row[12] if len(row) > 12 else None,
            correlation_id=row[13] if len(row) > 13 else None,
            reply_to=row[14] if len(row) > 14 else None,
            entity_id=row[15] if len(row) > 15 else None,
            expected_version=row[16] if len(row) > 16 else None,
            security_context=json.loads(row[17]) if len(row) > 17 and row[17] else {"principal_id": "unknown", "principal_type": "system"}
        )

    def close(self):
        self._conn.close()
