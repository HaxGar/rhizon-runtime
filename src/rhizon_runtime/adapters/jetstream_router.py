import logging
import nats
from nats.aio.client import Client as NATS
from nats.js.api import RetentionPolicy

from rhizon_runtime.core.interfaces import Router
from rhizon_runtime.core.models import EventEnvelope

logger = logging.getLogger(__name__)

class JetStreamCommandRouter:
    """
    NATS JetStream implementation of Router.
    Routes commands to: cmd.{tenant}.{workspace}.{target_agent}.{name}
    Ensures stream existence on startup.
    """
    def __init__(self, nc: NATS, stream_name: str = "MESHFORGE_COMMANDS"):
        self.nc = nc
        self.js = nc.jetstream()
        self.stream_name = stream_name

    async def ensure_stream(self):
        """
        Idempotently create or update the stream.
        """
        try:
            # We want a WorkQueue stream for Commands (Load Balancing)
            # Subjects: cmd.>
            await self.js.add_stream(
                name=self.stream_name,
                subjects=["cmd.>"],
                retention=RetentionPolicy.WORK_QUEUE, # Ensure command is processed by only one worker group member
                storage="file"
            )
            logger.info(f"Stream {self.stream_name} ensured.")
        except Exception as e:
            logger.error(f"Failed to ensure stream {self.stream_name}: {e}")
            raise e

    async def route(self, envelope: EventEnvelope) -> None:
        if not envelope.type.startswith("cmd."):
            logger.warning(f"Attempted to route non-command: {envelope.type}")
            return

        subject = self._get_subject(envelope)
        payload = envelope.model_dump_json().encode()
        
        try:
            # Publish to JetStream
            ack = await self.js.publish(subject, payload)
            logger.debug(f"Routed {envelope.id} to {subject} (seq={ack.seq})")
        except Exception as e:
            logger.error(f"Failed to route {envelope.id} to {subject}: {e}")
            raise e

    def _get_subject(self, envelope: EventEnvelope) -> str:
        # Requirement: cmd.{tenant}.{workspace}.{target_agent}.{name}
        parts = envelope.type.split(".")
        
        if len(parts) < 3:
            target_agent = "unknown"
            command_name = ".".join(parts[1:]) if len(parts) > 1 else parts[0]
        else:
            target_agent = parts[1]
            command_name = ".".join(parts[2:])

        return f"cmd.{envelope.tenant}.{envelope.workspace}.{target_agent}.{command_name}"
