from typing import Dict, Set, List, Optional
import time
import hashlib
import asyncio
from opentelemetry import trace, metrics
from opentelemetry.trace import Status, StatusCode

from rhizon_runtime.core.models import EventEnvelope
from rhizon_runtime.core.interfaces import AgentRuntimeAdapter, EventBus, EventStoreAdapter, Router

class RuntimeEngine:
    """
    Core Runtime Engine that drives the Agent Adapter.
    Handles determinism, time injection, idempotency, and routing.
    """
    def __init__(self, 
                 agent_id: str, 
                 adapter: AgentRuntimeAdapter, 
                 bus: EventBus, 
                 store: Optional[EventStoreAdapter] = None, 
                 router: Optional[Router] = None,
                 deterministic: bool = False,
                 tracer: Optional[trace.Tracer] = None,
                 meter: Optional[metrics.Meter] = None,
                 tenant: str = "default",
                 workspace: str = "default"):
        self.agent_id = agent_id
        self.adapter = adapter
        self.bus = bus
        self.store = store
        self.router = router
        self.deterministic = deterministic
        
        # Phase 0.15: Strict Scoping
        self.tenant = tenant
        self.workspace = workspace
        
        # Concurrency control
        self._lock = asyncio.Lock()
        
        # Idempotency tracking
        self._processed_keys: Set[str] = set()
        
        # Observability counters (simple dicts for V0)
        self.metrics = {
            "events_received_total": 0,
            "events_emitted_total": 0,
            "commands_sent_total": 0,
            "event_processing_duration_ms": 0,
            "security_violations_total": 0
        }
        
        # OpenTelemetry Instrumentation
        self.tracer = tracer or trace.get_tracer("meshforge.runtime.engine")
        self.meter = meter or metrics.get_meter("meshforge.runtime.engine")
        
        self.otel_counter_received = self.meter.create_counter(
            "events_received_total", description="Total events received by the engine"
        )
        self.otel_counter_emitted = self.meter.create_counter(
            "events_emitted_total", description="Total events emitted by the engine"
        )
        self.otel_counter_idempotency = self.meter.create_counter(
            "idempotency_hits_total", description="Total idempotency hits (duplicates skipped)"
        )
        self.otel_counter_security = self.meter.create_counter(
            "security_violations_total", description="Total security violations rejected"
        )
        self.otel_hist_duration = self.meter.create_histogram(
            "event_processing_duration_ms", description="Event processing duration in milliseconds"
        )

    def recover(self):
        """
        Replay events from store to restore state.
        STRICTLY SCOPED to (tenant, workspace).
        """
        if not self.store:
            return

        with self.tracer.start_as_current_span("recover", attributes={"agent.id": self.agent_id}) as span:
            # Replay all events for THIS tenant/workspace
            filters = {"tenant": self.tenant, "workspace": self.workspace}
            events = self.store.replay(filters=filters)
            span.set_attribute("events.count", len(events))
            
            for event in events:
                # Double-check scope (Defense in Depth)
                if event.tenant != self.tenant or event.workspace != self.workspace:
                    print(f"[RuntimeEngine] CRITICAL: Recovered event {event.id} has invalid scope {event.tenant}/{event.workspace}. Skipping.")
                    continue

                # During recovery, we ONLY apply to state.
                # We do NOT publish to bus or route commands.
                self.adapter.apply(event)
                # Re-populate idempotency keys so we don't re-process old commands
                if event.idempotency_key:
                    scoped_key = f"{event.tenant}:{event.workspace}:{event.idempotency_key}"
                    self._processed_keys.add(scoped_key)
            
            # Debug logging
            print(f"[RuntimeEngine] Recovered {len(events)} events. Processed keys: {len(self._processed_keys)}")

    async def process_event(self, envelope: EventEnvelope):
        """
        Process an incoming event envelope.
        """
        async with self._lock:
            with self.tracer.start_as_current_span(
                "process_event", 
                kind=trace.SpanKind.SERVER,
                attributes={
                    "agent.id": self.agent_id,
                    "event.type": envelope.type,
                    "event.id": envelope.id,
                    "meshforge.trace_id": envelope.trace_id or "",
                    "meshforge.causation_id": envelope.causation_id or ""
                }
            ) as span:
                try:
                    # 0. Security & Isolation Check (Phase 0.15)
                    if envelope.tenant != self.tenant or envelope.workspace != self.workspace:
                        reason = f"Security Violation: Event scope {envelope.tenant}/{envelope.workspace} does not match Engine scope {self.tenant}/{self.workspace}"
                        print(f"[RuntimeEngine] {reason}")
                        
                        violation_event = self._create_security_violation_event(envelope, reason)
                        
                        # Persist violation? Yes, strictly required for Audit.
                        if self.store:
                             self.store.append(violation_event)
                        
                        # Mark the original command as processed to avoid spam
                        scoped_key = f"{envelope.tenant}:{envelope.workspace}:{envelope.idempotency_key}"
                        self._processed_keys.add(scoped_key)
                        
                        # We do NOT publish the violation to the public bus if it's sensitive?
                        # Actually spec says "evt.security.violation" is persisted.
                        # Maybe published to a security stream? For now standard publish.
                        await self.bus.publish([violation_event])
                        
                        self.metrics["security_violations_total"] += 1
                        self.otel_counter_security.add(1, {"agent": self.agent_id, "reason": "scope_mismatch"})
                        span.set_attribute("security.violation", True)
                        
                        return [violation_event]

                    # 1. Idempotency Check
                    is_duplicate = False
                    scoped_key = f"{envelope.tenant}:{envelope.workspace}:{envelope.idempotency_key}"
                    if scoped_key in self._processed_keys:
                        is_duplicate = True
                    elif self.store:
                        # Fallback: Check store directly with tenant/workspace scoping
                        stored_events = self.store.get_by_idempotency_key(envelope.idempotency_key, envelope.tenant, envelope.workspace)
                        if stored_events:
                            is_duplicate = True
                            # Populate memory cache with scoped key
                            self._processed_keys.add(scoped_key)

                    if is_duplicate:
                        print(f"[RuntimeEngine] Duplicate Key: {envelope.idempotency_key}")
                        span.set_attribute("idempotency.hit", True)
                        self.otel_counter_idempotency.add(1, {"agent": self.agent_id})
                        
                        # Duplicate detected
                        # If we have a store, try to return the original result
                        if self.store:
                            original_events = self.store.get_by_idempotency_key(envelope.idempotency_key, envelope.tenant, envelope.workspace)
                            if original_events:
                                # CRITICAL: At-Least-Once Delivery
                                # If we crashed after Store but before Publish last time, these events might not have been sent.
                                # We must re-publish them now to ensure downstream receives them.
                                # Downstream must handle duplicates.
                                if original_events:
                                    events_to_publish = [e for e in original_events if not e.type.startswith("cmd.")]
                                    commands_to_route = [e for e in original_events if e.type.startswith("cmd.")]
                                    
                                    if events_to_publish:
                                        print(f"[RuntimeEngine] Re-publishing {len(events_to_publish)} events for idempotency.")
                                        await self.bus.publish(events_to_publish)
                                    
                                    if commands_to_route and self.router:
                                        print(f"[RuntimeEngine] Re-routing {len(commands_to_route)} commands for idempotency.")
                                        for cmd in commands_to_route:
                                            await self.router.route(cmd)

                                return original_events
                        
                        return []
                    
                    start_time = self._get_time_ms()
                    self.metrics["events_received_total"] += 1
                    self.otel_counter_received.add(1, {"agent": self.agent_id, "type": envelope.type})
        
                    # 1.5. Optimistic Concurrency Check (Anti-Double Write)
                    if envelope.expected_version is not None:
                        current_state = self.adapter.get_state()
                        
                        # Determine current version to check against
                        # If the command targets a specific entity, use that entity's version.
                        # Otherwise fall back to global version (or 0).
                        current_version = 0
                        target_entity_id = envelope.entity_id
                        
                        if target_entity_id and target_entity_id in current_state.entity_versions:
                            current_version = current_state.entity_versions[target_entity_id]
                        
                        # Note: If entity doesn't exist yet, version is 0.
                        # This allows "create if not exists" with expected_version=0
                        
                        if current_version != envelope.expected_version:
                            reason = f"Version mismatch for entity {target_entity_id}: expected {envelope.expected_version}, got {current_version}"
                            print(f"[RuntimeEngine] Concurrency Conflict: {reason}")
                            
                            conflict_event = self._create_conflict_event(envelope, current_version, reason)
                            
                            # We MUST persist this conflict decision to ensure deterministic replay.
                            if self.store:
                                with self.tracer.start_as_current_span("store.append_conflict"):
                                    self.store.append(conflict_event)
                            
                            # Publish the conflict event so the caller knows
                            with self.tracer.start_as_current_span("bus.publish_conflict"):
                                await self.bus.publish([conflict_event])
                                 
                            # Mark as processed so we don't retry and succeed later
                            self._processed_keys.add(scoped_key)
                            
                            span.set_attribute("concurrency.conflict", True)
                            return [conflict_event]

                    # 2. Invoke Adapter (Pure Decision)
                    with self.tracer.start_as_current_span("adapter.receive") as span_receive:
                        output_envelopes = self.adapter.receive(envelope)
                        
                        # Phase 0.15: Egress Enforcement (Strict Scoping)
                        # We forcibly overwrite tenant/workspace on all output events to match the Engine's scope.
                        # This prevents adapters from spoofing other tenants.
                        for out_env in output_envelopes:
                            out_env.tenant = self.tenant
                            out_env.workspace = self.workspace
                            
                        span_receive.set_attribute("output.count", len(output_envelopes))
                    
                    # 3. Persistence & State Update & Side Effects
                    if output_envelopes:
                        span.set_attribute("events.emitted_count", len(output_envelopes))
                        
                        # 3a. Persistence (Batch)
                        if self.store:
                            with self.tracer.start_as_current_span("store.append_batch") as span_store:
                                self.store.append_batch(output_envelopes)
                                span_store.set_attribute("batch.size", len(output_envelopes))
                        
                        # 3b. Separate Events vs Commands
                        events_to_publish = []
                        commands_to_route = []
                        
                        with self.tracer.start_as_current_span("adapter.apply_batch") as span_apply:
                            for env in output_envelopes:
                                # Apply to local state (both events and commands might update state, e.g. "command_sent")
                                self.adapter.apply(env)
                                
                                if env.type.startswith("cmd."):
                                    commands_to_route.append(env)
                                else:
                                    events_to_publish.append(env)
                            span_apply.set_attribute("apply.count", len(output_envelopes))
        
                        # 3c. Side Effects
                        
                        # Publish Events
                        if events_to_publish:
                            self.metrics["events_emitted_total"] += len(events_to_publish)
                            self.otel_counter_emitted.add(len(events_to_publish), {"agent": self.agent_id, "kind": "event"})
                            with self.tracer.start_as_current_span("bus.publish") as span_publish:
                                await self.bus.publish(events_to_publish)
                                span_publish.set_attribute("publish.count", len(events_to_publish))
                        
                        # Route Commands
                        if commands_to_route and self.router:
                            self.metrics["commands_sent_total"] += len(commands_to_route)
                            self.otel_counter_emitted.add(len(commands_to_route), {"agent": self.agent_id, "kind": "command"})
                            with self.tracer.start_as_current_span("router.route_batch") as span_route:
                                for cmd in commands_to_route:
                                    # Ensure command has trace context from trigger if missing?
                                    # Adapter should have handled this, but we could enforce.
                                    await self.router.route(cmd)
                                span_route.set_attribute("route.count", len(commands_to_route))
        
                    # 4. Mark processed (Command Idempotency)
                    self._processed_keys.add(scoped_key)
                    
                    duration = self._get_time_ms() - start_time
                    self.metrics["event_processing_duration_ms"] += duration
                    self.otel_hist_duration.record(duration, {"agent": self.agent_id, "type": envelope.type})
                    
                    return output_envelopes or []
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

    def _create_conflict_event(self, cmd: EventEnvelope, current_version: int, reason: str) -> EventEnvelope:
        """
        Helper to create a conflict event.
        """
        # Subject should be stable: evt.<agent_id>.conflict
        # Entity ID is in the payload.
        return EventEnvelope(
            id=f"evt-{cmd.id}-conflict",
            ts=self._get_time_ms(),
            type=f"evt.{self.agent_id}.conflict",
            payload={
                "entity_id": cmd.entity_id,
                "expected_version": cmd.expected_version,
                "current_version": current_version,
                "reason": reason
            },
            # CRITICAL: Use Command's idempotency key so we can find this event 
            # if the command is re-delivered (Crash Recovery / Idempotency Check).
            idempotency_key=cmd.idempotency_key,
            source={"agent": self.agent_id, "adapter": "runtime"},
            tenant=cmd.tenant,
            workspace=cmd.workspace,
            actor=cmd.actor,
            trace_id=cmd.trace_id,
            span_id=cmd.span_id,
            causation_id=cmd.id,
            correlation_id=cmd.correlation_id,
            security_context=cmd.security_context
        )

    async def tick(self):
        """
        Trigger time-based logic with strict tenant/workspace isolation.
        """
        async with self._lock:
            now = self._get_time_ms()
            output_events = self.adapter.tick(now)
            
            if output_events:
                # Phase 0.15.1: Enforce tenant/workspace isolation on tick() events
                for evt in output_events:
                    # Override any tenant/workspace set by adapter to ensure isolation
                    evt.tenant = self.tenant
                    evt.workspace = self.workspace
                
                if self.store:
                    self.store.append_batch(output_events)
                
                for evt in output_events:
                    self.adapter.apply(evt)
                
                self.metrics["events_emitted_total"] += len(output_events)
                await self.bus.publish(output_events)

    def _get_time_ms(self) -> int:
        if self.deterministic:
            return 1234567890000 # Stable fixed time
        return int(time.time() * 1000)
        
    def get_state_hash(self) -> str:
        """
        Compute a deterministic hash of the agent state.
        """
        state = self.adapter.get_state()
        # Ensure stable serialization
        import json
        json_str = json.dumps(state.model_dump(), sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()
