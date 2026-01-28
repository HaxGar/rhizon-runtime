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
            # Check if we need to migrate from old schema
            cursor = self._conn.execute("PRAGMA table_info(events)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # If table doesn't exist, create it with full schema
            if not columns:
                self._conn.execute("""
                    CREATE TABLE events (
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
            else:
                # Check if we need to add new columns (migration)
                new_columns = {
                    'schema_version': 'TEXT DEFAULT \'1.0\'',
                    'causation_id': 'TEXT',
                    'correlation_id': 'TEXT',
                    'reply_to': 'TEXT',
                    'entity_id': 'TEXT',
                    'expected_version': 'INTEGER'
                }
                
                for col_name, col_def in new_columns.items():
                    if col_name not in columns:
                        try:
                            self._conn.execute(f"ALTER TABLE events ADD COLUMN {col_name} {col_def}")
                        except sqlite3.OperationalError:
                            # Column might already exist or other issue, ignore for now
                            pass
            
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type)")
            # Idempotency check index
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_idempotency ON events(idempotency_key)")
            # Scoping index
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_scope ON events(tenant, workspace)")

    def append(self, event: EventEnvelope) -> None:
        # Use explicit column names for compatibility with both old and new schemas
        with self._conn:
            # Check which columns exist
            cursor = self._conn.execute("PRAGMA table_info(events)")
            existing_columns = [row[1] for row in cursor.fetchall()]
            
            # Base columns (always exist)
            base_columns = ['id', 'ts', 'type', 'trace_id', 'span_id', 'tenant', 'workspace', 
                          'actor_json', 'payload_json', 'idempotency_key', 'source_json', 'security_context_json']
            base_values = [
                event.id, event.ts, event.type, event.trace_id, event.span_id,
                event.tenant, event.workspace, json.dumps(event.actor),
                json.dumps(event.payload), event.idempotency_key, 
                json.dumps(event.source), json.dumps(event.security_context)
            ]
            
            # Optional columns (might not exist in old schema)
            optional_columns = ['schema_version', 'causation_id', 'correlation_id', 'reply_to', 'entity_id', 'expected_version']
            optional_values = [
                event.schema_version, event.causation_id, event.correlation_id,
                event.reply_to, event.entity_id, event.expected_version
            ]
            
            # Build query dynamically based on existing columns
            columns = base_columns.copy()
            values = base_values.copy()
            
            for col, val in zip(optional_columns, optional_values):
                if col in existing_columns:
                    columns.append(col)
                    values.append(val)
            
            # Build placeholders
            placeholders = ', '.join(['?' for _ in columns])
            
            query = f"INSERT INTO events ({', '.join(columns)}) VALUES ({placeholders})"
            self._conn.execute(query, values)

    def append_batch(self, events: List[EventEnvelope]) -> None:
        if not events:
            return
        
        # Check which columns exist (only once)
        cursor = self._conn.execute("PRAGMA table_info(events)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        # Prepare data based on existing columns
        data = []
        for e in events:
            # Base values (always exist)
            base_values = [
                e.id, e.ts, e.type, e.trace_id, e.span_id,
                e.tenant, e.workspace, json.dumps(e.actor),
                json.dumps(e.payload), e.idempotency_key,
                json.dumps(e.source), json.dumps(e.security_context)
            ]
            
            # Optional values (if columns exist)
            optional_values = []
            optional_columns = ['schema_version', 'causation_id', 'correlation_id', 'reply_to', 'entity_id', 'expected_version']
            optional_data = [e.schema_version, e.causation_id, e.correlation_id, e.reply_to, e.entity_id, e.expected_version]
            
            for col, val in zip(optional_columns, optional_data):
                if col in existing_columns:
                    optional_values.append(val)
            
            # Combine all values
            all_values = base_values + optional_values
            data.append(tuple(all_values))
        
        # Build column list and placeholders
        base_columns = ['id', 'ts', 'type', 'trace_id', 'span_id', 'tenant', 'workspace', 
                       'actor_json', 'payload_json', 'idempotency_key', 'source_json', 'security_context_json']
        columns = base_columns.copy()
        
        for col in ['schema_version', 'causation_id', 'correlation_id', 'reply_to', 'entity_id', 'expected_version']:
            if col in existing_columns:
                columns.append(col)
        
        placeholders = ', '.join(['?' for _ in columns])
        
        try:
            with self._conn:
                self._conn.executemany(f"""
                    INSERT INTO events ({', '.join(columns)}) VALUES ({placeholders})
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
        # Handle both old and new schemas dynamically
        cursor = self._conn.execute("PRAGMA table_info(events)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        # Map column index to field name
        column_map = {}
        for i, col_name in enumerate(existing_columns):
            column_map[col_name] = i
        
        # Extract values with fallbacks for missing columns
        def get_col(col_name, default=None):
            if col_name in column_map:
                return row[column_map[col_name]]
            return default
        
        return EventEnvelope(
            id=get_col('id'),
            ts=get_col('ts'),
            type=get_col('type'),
            schema_version=get_col('schema_version', '1.0'),
            trace_id=get_col('trace_id'),
            span_id=get_col('span_id'),
            tenant=get_col('tenant'),
            workspace=get_col('workspace'),
            actor=json.loads(get_col('actor_json', '{}')),
            payload=json.loads(get_col('payload_json', '{}')),
            idempotency_key=get_col('idempotency_key'),
            source=json.loads(get_col('source_json', '{}')),
            causation_id=get_col('causation_id'),
            correlation_id=get_col('correlation_id'),
            reply_to=get_col('reply_to'),
            entity_id=get_col('entity_id'),
            expected_version=get_col('expected_version'),
            security_context=json.loads(get_col('security_context_json', '{"principal_id": "unknown", "principal_type": "system"}'))
        )

    def close(self):
        self._conn.close()
