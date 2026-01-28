import asyncio
import logging
from typing import List
import nats
from nats.aio.client import Client as NATS
from nats.js.api import StreamConfig, RetentionPolicy

from rhizon_runtime.core.interfaces import EventBus
from rhizon_runtime.core.models import EventEnvelope

logger = logging.getLogger(__name__)

class JetStreamEventBus:
    """
    NATS JetStream implementation of EventBus.
    Publishes events to: evt.{tenant}.{workspace}.{domain}.{name}
    Ensures stream existence on startup.
    """
    def __init__(self, nc: NATS, stream_name: str = "MESHFORGE_EVENTS"):
        self.nc = nc
        self.js = nc.jetstream()
        self.stream_name = stream_name

    async def ensure_stream(self):
        """
        Idempotently create or update the stream.
        """
        try:
            # We want a durable stream for Events
            # Subjects: evt.>
            await self.js.add_stream(
                name=self.stream_name,
                subjects=["evt.>"],
                retention=RetentionPolicy.LIMITS, # Keep events based on limits (age/bytes/msgs)
                storage="file" # Durable
            )
            logger.info(f"Stream {self.stream_name} ensured.")
        except Exception as e:
            logger.error(f"Failed to ensure stream {self.stream_name}: {e}")
            raise e

    async def publish(self, events: List[EventEnvelope]) -> None:
        for event in events:
            subject = self._get_subject(event)
            payload = event.model_dump_json().encode()
            try:
                # Publish to JetStream
                # We expect an Ack from the server (publish is async but waits for ack by default in nats-py js.publish)
                ack = await self.js.publish(subject, payload)
                logger.debug(f"Published {event.id} to {subject} (seq={ack.seq})")
            except Exception as e:
                logger.error(f"Failed to publish {event.id} to {subject}: {e}")
                raise e

    def _get_subject(self, event: EventEnvelope) -> str:
        # Requirement: evt.{tenant}.{workspace}.{domain}.{name}
        parts = event.type.split(".")
        if parts[0] == "evt":
            parts = parts[1:]
        
        if not parts:
            suffix = event.type
        else:
            suffix = ".".join(parts)
            
        return f"evt.{event.tenant}.{event.workspace}.{suffix}"
