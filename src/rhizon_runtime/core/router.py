from typing import Dict, Optional, Protocol
import asyncio
import re
from rhizon_runtime.core.models import EventEnvelope
from rhizon_runtime.core.interfaces import EventBus

# Avoid circular import if possible, but we need RuntimeEngine for type hint?
# Use Protocol or 'RuntimeEngine' string forward reference.

class EngineProtocol(Protocol):
    async def process_event(self, envelope: EventEnvelope) -> None: ...

class InProcessRouter:
    """
    Routes commands between agents in the same process.
    """
    def __init__(self):
        self._routes: Dict[str, EngineProtocol] = {}
        self._patterns: Dict[str, re.Pattern] = {}

    def register(self, agent_name: str, engine: EngineProtocol):
        """
        Register an engine to handle commands for 'agent_name'.
        Convention: cmd.{agent_name}.* -> engine
        """
        self._routes[agent_name.lower()] = engine
        
    async def route(self, envelope: EventEnvelope) -> None:
        """
        Route a command envelope to the appropriate engine.
        """
        if not envelope.type.startswith("cmd."):
            return # Should not happen if filtered correctly
            
        parts = envelope.type.split(".")
        if len(parts) < 2:
            print(f"[Router] Malformed command type: {envelope.type}")
            return
            
        target_agent = parts[1].lower()
        
        engine = self._routes.get(target_agent)
        if engine:
            # Dispatch async without awaiting? Or await?
            # For causality/sagas, we often want async but guaranteed delivery.
            # In V0 (in-process), we might await to ensure strict ordering in tests?
            # User requirement: "ordering".
            # If we await, it's synchronous call stack -> effectively depth-first processing.
            await engine.process_event(envelope)
        else:
            print(f"[Router] No route for agent: {target_agent}")

