from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field, field_validator
import json

class EventEnvelope(BaseModel):
    """
    V1 Event Envelope for MeshForge Runtime.
    Strict schema enforcement for all bus messages.
    """
    id: str = Field(..., description="Unique Event ID (stable/derivable in deterministic mode)")
    ts: int = Field(..., description="Unix Timestamp (ms). Injected by Runtime.")
    type: str = Field(..., description="Event Type (e.g. cmd.order.submit)")
    schema_version: str = Field("1.0", description="Schema Version")
    
    trace_id: str = Field(..., description="OpenTelemetry Trace ID")
    span_id: str = Field(..., description="OpenTelemetry Span ID")
    
    tenant: str = Field(..., description="Multi-tenancy isolation key")
    workspace: str = Field(..., description="Workspace isolation key")
    
    actor: Dict[str, str] = Field(..., description="Actor info {'id': str, 'role': str}")
    payload: Dict[str, Any] = Field(..., description="Business payload")
    
    idempotency_key: str = Field(..., description="Critical for de-duplication and replay")
    source: Dict[str, str] = Field(..., description="Source info {'agent': str, 'adapter': str}")

    # Phase 0.10: Multi-Agent fields
    causation_id: Optional[str] = Field(None, description="ID of the event that caused this event")
    correlation_id: Optional[str] = Field(None, description="ID identifying the conversation/transaction")
    reply_to: Optional[str] = Field(None, description="Address/Topic to reply to")

    # Phase 0.14: Concurrency fields
    entity_id: Optional[str] = Field(None, description="Target Entity/Aggregate ID for concurrency control")
    expected_version: Optional[int] = Field(None, description="Optimistic Concurrency: Expected version of the entity")

    # Phase 0.15: Security fields
    security_context: Dict[str, str] = Field(..., description="Security Context {'principal_id': str, 'principal_type': str}")

    @field_validator('actor')
    def validate_actor(cls, v):
        if 'id' not in v or 'role' not in v:
            raise ValueError("Actor must contain 'id' and 'role'")
        return v

    @field_validator('source')
    def validate_source(cls, v):
        if 'agent' not in v or 'adapter' not in v:
            raise ValueError("Source must contain 'agent' and 'adapter'")
        return v

    @field_validator('security_context')
    def validate_security_context(cls, v):
        if 'principal_id' not in v or 'principal_type' not in v:
            raise ValueError("Security Context must contain 'principal_id' and 'principal_type'")
        valid_types = {'service', 'agent', 'user', 'system'}
        if v['principal_type'] not in valid_types:
            raise ValueError(f"Security Context principal_type must be one of {valid_types}")
        return v

    def to_json(self, deterministic: bool = False) -> str:
        """
        Serialize to JSON with sorted keys for determinism.
        """
        return json.dumps(self.model_dump(), sort_keys=True)
