import asyncio
import json
import logging
from typing import List, Optional
import nats
from nats.aio.client import Client as NATS

from rhizon_runtime.core.interfaces import EventBus
from rhizon_runtime.core.models import EventEnvelope

logger = logging.getLogger(__name__)

class NatsEventBus:
    """
    NATS implementation of EventBus.
    Publishes events to: evt.{tenant}.{workspace}.{domain}.{name}
    """
    def __init__(self, nc: NATS):
        self.nc = nc

    async def publish(self, events: List[EventEnvelope]) -> None:
        for event in events:
            subject = self._get_subject(event)
            payload = event.model_dump_json().encode()
            try:
                await self.nc.publish(subject, payload)
                logger.debug(f"Published {event.id} to {subject}")
            except Exception as e:
                logger.error(f"Failed to publish {event.id} to {subject}: {e}")
                # For Phase 0.12 (Core NATS), we log error. 
                # Retry logic should be handled by caller or stronger infrastructure (JetStream)
                raise e

    def _get_subject(self, event: EventEnvelope) -> str:
        # Expected type format: "evt.domain.name" or just "domain.name" if prefix not strictly enforcing
        # Requirement: evt.{tenant}.{workspace}.{domain}.{name}
        
        parts = event.type.split(".")
        
        # Remove "evt" prefix if present to avoid duplication
        if parts[0] == "evt":
            parts = parts[1:]
            
        # If parts is empty or weird, fallback
        if not parts:
            suffix = event.type
        else:
            suffix = ".".join(parts)
            
        return f"evt.{event.tenant}.{event.workspace}.{suffix}"
