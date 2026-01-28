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
                    trace_id TEXT,
                    span_id TEXT,
                    tenant TEXT,
                    workspace TEXT,
                    actor_json TEXT,
                    payload_json TEXT,
                    idempotency_key TEXT,
                    source_json TEXT,
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
        self.append_batch([event])

    def append_batch(self, events: List[EventEnvelope]) -> None:
        if not events:
            return
        
        data = []
        for e in events:
            data.append((
                e.id,
                e.ts,
                e.type,
                e.trace_id,
                e.span_id,
                e.tenant,
                e.workspace,
                json.dumps(e.actor),
                json.dumps(e.payload),
                e.idempotency_key,
                json.dumps(e.source),
                json.dumps(e.security_context)
            ))
        
        try:
            with self._conn:
                self._conn.executemany("""
                    INSERT INTO events (
                        id, ts, type, trace_id, span_id, tenant, workspace, 
                        actor_json, payload_json, idempotency_key, source_json, security_context_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    def get_by_idempotency_key(self, key: str) -> List[EventEnvelope]:
        query = "SELECT * FROM events WHERE idempotency_key = ? ORDER BY rowid ASC"
        cursor = self._conn.execute(query, [key])
        rows = cursor.fetchall()
        return [self._row_to_envelope(row) for row in rows]

    def _row_to_envelope(self, row) -> EventEnvelope:
        # id(0), ts(1), type(2), trace(3), span(4), tenant(5), workspace(6), actor(7), payload(8), idem(9), source(10), security_context(11), created_at(12)
        # Note: If database was created before security_context_json, this might fail if we don't migrate.
        # Assuming fresh DB for now as per dev workflow.
        
        # Handle backward compatibility if column count < 13? 
        # But we changed the table definition.
        
        return EventEnvelope(
            id=row[0],
            ts=row[1],
            type=row[2],
            schema_version="1.0",
            trace_id=row[3],
            span_id=row[4],
            tenant=row[5],
            workspace=row[6],
            actor=json.loads(row[7]),
            payload=json.loads(row[8]),
            idempotency_key=row[9],
            source=json.loads(row[10]),
            security_context=json.loads(row[11]) if len(row) > 11 and row[11] else {"principal_id": "unknown", "principal_type": "system"} # Fallback/Migration
        )

    def close(self):
        self._conn.close()
