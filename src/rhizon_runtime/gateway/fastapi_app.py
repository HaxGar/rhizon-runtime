from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
import logging
import asyncio

from rhizon_runtime.core.models import EventEnvelope
from rhizon_runtime.core.engine import RuntimeEngine

logger = logging.getLogger("meshforge.gateway")

class RuntimeGateway:
    """
    HTTP Gateway for MeshForge Runtime.
    Exposes a POST /events endpoint that accepts EventEnvelopes and dispatches them 
    to registered RuntimeEngines.
    """
    def __init__(self):
        self.app = FastAPI(title="MeshForge Runtime Gateway", version="0.7.0")
        self.engines: List[RuntimeEngine] = []
        self._setup_routes()

    def register_engine(self, engine: RuntimeEngine):
        self.engines.append(engine)
        logger.info(f"Registered engine for agent: {engine.agent_id}")

    def _setup_routes(self):
        @self.app.post("/events", response_model=List[EventEnvelope])
        async def handle_event(envelope: EventEnvelope):
            """
            Synchronously process an event through all registered engines
            and return the resulting events (Command -> Events pattern).
            """
            logger.info(f"Received event: {envelope.type} (ID: {envelope.id})")
            
            # In V0, we broadcast to all engines and collect results.
            # In a real system, this would use a Bus subscription or specific routing.
            
            results = []
            
            # Run sequentially or parallel?
            # Sequential is safer for V0 determinism if one event triggers another (chained).
            # But here we assume a single Command triggers a single Manager.
            
            for engine in self.engines:
                try:
                    # process_event now returns the emitted events
                    emitted = await engine.process_event(envelope)
                    if emitted:
                        results.extend(emitted)
                except Exception as e:
                    logger.error(f"Error in engine {engine.agent_id}: {e}")
                    # We continue to other engines? Or fail?
                    # For a Command, usually one handler is expected.
                    # If any fails, we might want to report error.
                    # But generic error handling is tricky.
                    pass
            
            return results

        @self.app.get("/health")
        async def health():
            return {"status": "ok", "engines": len(self.engines)}

        @self.app.get("/debug/state/{agent_id}")
        async def get_agent_state(agent_id: str):
            """
            Get the deterministic hash and version of an agent's state.
            """
            for engine in self.engines:
                if engine.agent_id == agent_id:
                    # Accessing engine state directly. 
                    # In strict actor model, we should send a message.
                    # But for V0 debug, direct access is fine (engine is local).
                    
                    # Need to acquire lock if we want to be safe, but get_state is usually read-only
                    # However, engine._lock is async.
                    # Let's try to be safe.
                    if hasattr(engine, "_lock"):
                        async with engine._lock:
                            state_hash = engine.get_state_hash()
                            state = engine.adapter.get_state()
                    else:
                        state_hash = engine.get_state_hash()
                        state = engine.adapter.get_state()
                        
                    return {
                        "agent_id": agent_id,
                        "hash": state_hash,
                        "version": state.version,
                        "updated_at": state.updated_at,
                        "data": state.data
                    }
            
            raise HTTPException(status_code=404, detail="Agent not found")

def create_app(engines: List[RuntimeEngine] = None) -> FastAPI:
    gateway = RuntimeGateway()
    if engines:
        for engine in engines:
            gateway.register_engine(engine)
    return gateway.app
