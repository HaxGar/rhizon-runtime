import asyncio
import logging
import json
from typing import Optional
import nats
from nats.aio.client import Client as NATS
from nats.js.api import ConsumerConfig, DeliverPolicy, AckPolicy

from rhizon_runtime.core.engine import RuntimeEngine
from rhizon_runtime.core.models import EventEnvelope

logger = logging.getLogger(__name__)

class JetStreamConsumer:
    """
    Durable JetStream Consumer that feeds a RuntimeEngine.
    Implements the 'At-Least-Once' -> 'Exactly-Once Effect' protocol.
    """
    def __init__(self, 
                 nc: NATS, 
                 engine: RuntimeEngine, 
                 stream_name: str, 
                 subject_filter: str,
                 durable_name: str,
                 backoff_policy: Optional[list] = None):
        self.nc = nc
        self.js = nc.jetstream()
        self.engine = engine
        self.stream_name = stream_name
        self.subject_filter = subject_filter
        self.durable_name = durable_name
        self.running = False
        self._task = None
        # Default Progressive Backoff: 1s, 5s, 10s, 30s (in seconds)
        self.backoff_policy = backoff_policy if backoff_policy is not None else [1.0, 5.0, 10.0, 30.0]

    async def start(self):
        """
        Start the pull consumer loop.
        """
        # Ensure Consumer Exists
        # Durable, Explicit Ack, Filtered
        try:
            config_kwargs = {
                "durable_name": self.durable_name,
                "deliver_policy": DeliverPolicy.ALL,
                "ack_policy": AckPolicy.EXPLICIT,
                "filter_subject": self.subject_filter,
                "max_deliver": 5, # DLQ after 5 attempts
                "ack_wait": 30, # seconds
            }
            if self.backoff_policy:
                config_kwargs["backoff"] = self.backoff_policy

            logger.info(f"Adding consumer with config: {config_kwargs}")
            await self.js.add_consumer(
                self.stream_name,
                durable_name=self.durable_name,
                config=ConsumerConfig(**config_kwargs)
            )
            logger.info(f"Consumer {self.durable_name} ensured on {self.stream_name} filtering {self.subject_filter}")
        except Exception as e:
            logger.error(f"Failed to ensure consumer {self.durable_name}: {e}")
            raise e

        self.running = True
        self._task = asyncio.create_task(self._consume_loop())

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _consume_loop(self):
        """
        Continuous pull loop.
        """
        # Re-create subscription if connection drops?
        # nats-py pull_subscribe creates a subscription object.
        while self.running:
            try:
                psub = await self.js.pull_subscribe(
                    self.subject_filter, 
                    durable=self.durable_name, 
                    stream=self.stream_name
                )
                break
            except Exception as e:
                logger.error(f"Failed to subscribe, retrying in 5s: {e}")
                await asyncio.sleep(5)
        
        while self.running:
            try:
                # Fetch batch of 1
                msgs = await psub.fetch(1, timeout=1.0)
                for msg in msgs:
                    await self._process_msg(msg)
            except TimeoutError:
                # No messages, loop
                continue
            except nats.errors.TimeoutError:
                 continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error in consume loop: {e}")
                    await asyncio.sleep(1) # Backoff

    async def _process_msg(self, msg):
        """
        Process a single JetStream message with full durability protocol.
        """
        try:
            logger.info(f"Consumer {self.durable_name} received message on {msg.subject}")
            data = json.loads(msg.data.decode())
            envelope = EventEnvelope(**data)
            
            await self.engine.process_event(envelope)
            
            await msg.ack()
            logger.info(f"Consumer {self.durable_name} processed and ACKed message {envelope.id}")
            
        except Exception as e:
            logger.error(f"Failed to process message {msg.subject}: {e}")
            
            # DLQ Check
            try:
                md = msg.metadata
                # md.num_delivered is 1-based
                logger.info(f"Checking DLQ status for {msg.subject}. Num delivered: {md.num_delivered}")
                
                if md.num_delivered >= 5:
                    logger.critical(f"Message {msg.subject} exceeded max deliveries ({md.num_delivered}). Moving to DLQ.")
                    # Publish to failed.>
                    dlq_subject = f"failed.{msg.subject}"
                    await self.js.publish(dlq_subject, msg.data)
                    logger.info(f"Published to DLQ: {dlq_subject}")
                    # ACK original to remove from queue
                    await msg.ack()
                    logger.info("ACKed original message after DLQ")
                    return
            except Exception as dlq_err:
                 logger.error(f"Failed to process DLQ for {msg.subject}: {dlq_err}")

            # Explicit NAK to trigger backoff immediately (NATS handles backoff timing)
            await msg.nak()
