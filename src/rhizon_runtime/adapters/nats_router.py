import logging
import nats
from nats.aio.client import Client as NATS
from rhizon_runtime.core.interfaces import Router
from rhizon_runtime.core.models import EventEnvelope

logger = logging.getLogger(__name__)

class NatsRouter:
    """
    NATS implementation of Router.
    Routes commands to: cmd.{tenant}.{workspace}.{target_agent}.{name}
    """
    def __init__(self, nc: NATS):
        self.nc = nc

    async def route(self, envelope: EventEnvelope) -> None:
        if not envelope.type.startswith("cmd."):
            logger.warning(f"Attempted to route non-command: {envelope.type}")
            return

        subject = self._get_subject(envelope)
        payload = envelope.model_dump_json().encode()
        
        try:
            await self.nc.publish(subject, payload)
            logger.debug(f"Routed {envelope.id} to {subject}")
        except Exception as e:
            logger.error(f"Failed to route {envelope.id} to {subject}: {e}")
            raise e

    def _get_subject(self, envelope: EventEnvelope) -> str:
        # Expected envelope.type format: "cmd.target_agent.command_name"
        # Requirement: cmd.{tenant}.{workspace}.{target_agent}.{name}
        
        parts = envelope.type.split(".")
        
        if len(parts) < 3:
            # Fallback if structure is weird: cmd.unknown.command_name
            target_agent = "unknown"
            command_name = ".".join(parts[1:]) if len(parts) > 1 else parts[0]
        else:
            target_agent = parts[1]
            command_name = ".".join(parts[2:])

        return f"cmd.{envelope.tenant}.{envelope.workspace}.{target_agent}.{command_name}"
