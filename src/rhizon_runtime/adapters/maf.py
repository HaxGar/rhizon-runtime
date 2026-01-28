from typing import List, Dict, Any, Optional
import logging
from rhizon_runtime.core.interfaces import AgentRuntimeAdapter, HealthStatus, AgentState
from rhizon_runtime.core.models import EventEnvelope

logger = logging.getLogger("meshforge.adapters.maf")

# Try to import MAF. If not present, this module will fail to import, 
# which is fine as it should only be used when MAF is available.
try:
    import maf
    from maf import Agent as MAFAgent
except ImportError:
    # For dev/test without MAF installed, we might define a dummy or let it fail
    # But strictly, the prompt says "optional".
    # We'll allow import but fail on __init__ if not found, or define dummy for linting?
    # Let's assume it must be installed.
    MAFAgent = Any 
    # logger.warning("MAF library not found. MAFAdapter will not work.")

class MAFAdapter(AgentRuntimeAdapter):
    """
    Adapter for MeshForge Agent Framework (MAF).
    Wraps a MAF Agent to comply with MeshForge Runtime Protocol (ARA).
    """

    def __init__(self, maf_agent: MAFAgent):
        if MAFAgent is Any and "maf" not in globals():
             raise ImportError("MAF library is required to use MAFAdapter.")
             
        self.agent = maf_agent
        # In-memory state tracking for the adapter part, 
        # but real state is likely inside the MAF agent or managed by it.
        # For V0, we assume MAF agent is stateless or we snapshot it.

    def receive(self, envelope: EventEnvelope) -> List[EventEnvelope]:
        """
        Delegate decision to MAF Agent.
        Pure decision: Input -> Output Events.
        """
        try:
            # Convert Envelope to MAF Context/Message
            # This depends on MAF API. Assuming:
            # result = self.agent.process(message)
            
            # For V0, let's assume a simple contract:
            # agent.process(payload: dict) -> list[dict] (events to emit)
            
            # Deterministic enforcement:
            # MAF agent must be deterministic. We can't enforce it here but we assume it.
            
            output_payloads = self.agent.process(envelope.payload)
            
            # Convert results back to Envelopes
            events = []
            for i, p in enumerate(output_payloads):
                # We need to construct the event envelope.
                # ID generation should be deterministic based on input ID + index
                evt_id = f"{envelope.id}_{i}"
                
                # Type inference? Or explicit in payload?
                evt_type = p.get("type", "evt.maf.unknown")
                
                evt = EventEnvelope(
                    id=evt_id,
                    ts=envelope.ts, # Logical time propagation
                    type=evt_type,
                    trace_id=envelope.trace_id,
                    span_id=envelope.span_id,
                    tenant=envelope.tenant,
                    workspace=envelope.workspace,
                    actor=envelope.actor,
                    payload=p.get("payload", p), # If p has 'payload', use it, else p is payload
                    idempotency_key=envelope.idempotency_key, # Link back?
                    source={"agent": "MAFAdapter", "adapter": "maf"},
                    security_context=envelope.security_context
                )
                events.append(evt)
                
            return events

        except Exception as e:
            logger.exception("Error in MAF Agent processing")
            # Return error event?
            return []

    def apply(self, envelope: EventEnvelope) -> None:
        """
        Update internal state of MAF Agent based on confirmed event.
        """
        # If MAF agent has internal state that needs updating:
        if hasattr(self.agent, "apply"):
            self.agent.apply(envelope.payload)

    def tick(self, now: int) -> List[EventEnvelope]:
        """
        Time-based triggers for MAF Agent.
        """
        if hasattr(self.agent, "tick"):
             # meaningful return logic todo
             return []
        return []

    def get_state(self) -> AgentState:
        """
        Extract state from MAF Agent.
        """
        data = {}
        if hasattr(self.agent, "get_state"):
            data = self.agent.get_state()
        elif hasattr(self.agent, "__dict__"):
            data = str(self.agent.__dict__) # Risky serialization
            
        return AgentState(
            version=1,
            data={"maf_state": data},
            updated_at=0
        )

    def health(self) -> HealthStatus:
        return HealthStatus.READY
