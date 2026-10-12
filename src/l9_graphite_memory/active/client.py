# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/active/client.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Stable external SDK surface for the active-memory subsystem.

`ActiveAgentClient` and `ActiveAgentSession` are the ONLY supported
integration points for external consumer applications (per ADR-067).
Consumers MUST NOT import `l9_graphite_memory.active.inmemory` or any
future Redis adapter module directly; those are internal implementation
details subject to change without a major version bump.

This module depends only on the ports defined in
`l9_graphite_memory.active.ports`, so it works identically against the
in-memory reference adapter, the null adapter, or a Redis adapter,
without any consumer-specific branching.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from l9_graphite_memory.active.errors import (
    ActiveMemoryUnavailableError,
    LeaseExpiredError,
)
from l9_graphite_memory.active.lifecycle import (
    ActiveAgentSessionState,
    LifecycleTransitionError,
    SessionLifecycle,
)
from l9_graphite_memory.active.models import (
    ActiveContext,
    ActiveContextDraft,
    AgentEvent,
    AgentEventType,
    AgentIdentity,
    AgentLease,
    AgentPresence,
    AgentScope,
    AgentStatus,
    AgentSubscription,
)
from l9_graphite_memory.active.ports import ActiveStore, AwarenessBus

logger = logging.getLogger("l9_graphite_memory.active.client")

Clock = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class _SessionRuntimeConfig:
    heartbeat_interval_seconds: int
    lease_ttl_seconds: int
    heartbeat_failure_threshold: int
    resync_backoff_seconds: float


@dataclass(slots=True)
class ActiveMemoryHealth:
    """Independent health of the active store and the awareness bus.

    ``store`` and ``bus`` carry each adapter's own probe result (or the
    typed failure that stopped it). ``healthy`` is true only when both
    probes completed; a disabled binding is never healthy, it is simply
    not selected (``enabled`` is false), so a deployment that requires
    active memory cannot read a null adapter as green.
    """

    enabled: bool
    backend: str
    healthy: bool
    store: dict[str, object]
    bus: dict[str, object]
    deployment: dict[str, object]
    error: str | None = None


@dataclass(slots=True)
class ActiveMemoryBinding:
    """One configured active-memory runtime: adapters, identity and policy.

    Built by `l9_graphite_memory.adapters.factory.build_active_memory` from
    `MemorySettings` and held by `MemoryRuntime`. It is the only supported
    way a consumer obtains an `ActiveAgentClient` against a configured
    backend (ADR-067): the consumer calls `client()` and never instantiates
    an adapter. The binding also answers independent readiness for the
    store and the bus, which is how the deployment proves the Redis leg is
    real rather than inferring it from an installed symbol.
    """

    backend: str
    enabled: bool
    required: bool
    deployment_id: str
    trust_domain: str
    environment: str
    store: ActiveStore
    bus: AwarenessBus
    credential_source: str | None = None
    heartbeat_interval_seconds: int = 10
    lease_ttl_seconds: int = 30
    heartbeat_failure_threshold: int = 3
    resync_backoff_seconds: float = 1.0

    def client(self, *, clock: Clock = _default_clock) -> ActiveAgentClient:
        """Construct a session client bound to this deployment's adapters."""

        return ActiveAgentClient(
            store=self.store,
            bus=self.bus,
            deployment_id=self.deployment_id,
            clock=clock,
            heartbeat_interval_seconds=self.heartbeat_interval_seconds,
            lease_ttl_seconds=self.lease_ttl_seconds,
            heartbeat_failure_threshold=self.heartbeat_failure_threshold,
            resync_backoff_seconds=self.resync_backoff_seconds,
        )

    def describe(self) -> dict[str, object]:
        """Non-secret description for receipts and readiness output."""

        return {
            "backend": self.backend,
            "enabled": self.enabled,
            "required": self.required,
            "deployment_id": self.deployment_id,
            "trust_domain": self.trust_domain,
            "environment": self.environment,
            "credential_source": self.credential_source,
        }

    async def health(self) -> ActiveMemoryHealth:
        """Probe the store and the bus independently; never raise."""

        store_result = await _probe(self.store.health)
        bus_result = await _probe(self.bus.health)
        failures = [r["error"] for r in (store_result, bus_result) if r.get("error")]
        return ActiveMemoryHealth(
            enabled=self.enabled,
            backend=self.backend,
            healthy=self.enabled and not failures,
            store=store_result,
            bus=bus_result,
            deployment=self.describe(),
            error="; ".join(str(f) for f in failures) or None,
        )

    async def close(self) -> None:
        """Release both adapters; a connection already torn down is not a failure."""

        for name, adapter in (("store", self.store), ("bus", self.bus)):
            try:
                await adapter.close()
            except (ActiveMemoryUnavailableError, RuntimeError, OSError) as exc:
                logger.debug("active-memory %s close reported %s", name, exc)


async def _probe(probe: Callable[[], Awaitable[object]]) -> dict[str, object]:
    """Run one adapter health probe and flatten its structural result."""

    try:
        result = await probe()
    except ActiveMemoryUnavailableError as exc:
        return {"connectivity": "unavailable", "error": str(exc)}
    snapshot: dict[str, object] = {}
    for name in ("backend", "connectivity", "authentication", "capabilities", "error"):
        value = getattr(result, name, None)
        if value is not None:
            snapshot[name] = list(value) if isinstance(value, tuple) else value
    if snapshot.get("connectivity") != "healthy" and "error" not in snapshot:
        snapshot["error"] = f"connectivity={snapshot.get('connectivity', 'unknown')}"
    return snapshot


class ActiveAgentClient:
    """Entry point for constructing external-runtime active-memory sessions.

    Instances are constructed through `ActiveMemoryBinding.client()`, the
    binding `l9_graphite_memory.adapters.factory.build_active_memory` yields
    from settings, and are bound to exactly one `ActiveStore`/`AwarenessBus`
    pair for one deployment. External consumer code receives an
    already-constructed `ActiveAgentClient` and never instantiates adapters
    itself.
    """

    def __init__(
        self,
        *,
        store: ActiveStore,
        bus: AwarenessBus,
        deployment_id: str,
        clock: Clock = _default_clock,
        heartbeat_interval_seconds: int = 10,
        lease_ttl_seconds: int = 30,
        heartbeat_failure_threshold: int = 3,
        resync_backoff_seconds: float = 1.0,
    ) -> None:
        self._store = store
        self._bus = bus
        self._deployment_id = deployment_id
        self._clock = clock
        self._runtime_config = _SessionRuntimeConfig(
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            lease_ttl_seconds=lease_ttl_seconds,
            heartbeat_failure_threshold=heartbeat_failure_threshold,
            resync_backoff_seconds=resync_backoff_seconds,
        )

    @asynccontextmanager
    async def open_session(
        self,
        *,
        agent_id: str,
        role: str,
        principal_id: str,
        group_ids: tuple[str, ...] = (),
        session_id: str | None = None,
        capabilities: frozenset[str] = frozenset(),
    ) -> AsyncIterator[ActiveAgentSession]:
        """Open a supervised active-agent session as an async context manager.

        On exit (including exception), the session transitions through
        DRAINING to CLOSED, unregistering its lease and stopping all
        background tasks. This is the only supported way to obtain an
        `ActiveAgentSession`.
        """
        session = ActiveAgentSession(
            store=self._store,
            bus=self._bus,
            deployment_id=self._deployment_id,
            agent_id=agent_id,
            role=role,
            principal_id=principal_id,
            group_ids=group_ids,
            session_id=session_id,
            capabilities=capabilities,
            clock=self._clock,
            runtime_config=self._runtime_config,
        )
        try:
            await session.start()
            yield session
        finally:
            await session.close()

    async def close(self) -> None:
        """Release the underlying store and bus resources.

        Must be called once during application shutdown after all
        sessions have been closed.
        """
        await self._store.close()
        await self._bus.close()


class ActiveAgentSession:
    """One external agent's supervised active-memory session.

    Manages: registration, heartbeat renewal, context writes, peer
    discovery, event subscription, degradation detection, reconnect and
    resynchronization, and graceful shutdown. See ADR-067 for the full
    state machine and background-task supervision requirements.
    """

    def __init__(
        self,
        *,
        store: ActiveStore,
        bus: AwarenessBus,
        deployment_id: str,
        agent_id: str,
        role: str,
        principal_id: str,
        group_ids: tuple[str, ...],
        session_id: str | None,
        capabilities: frozenset[str],
        clock: Clock,
        runtime_config: _SessionRuntimeConfig,
    ) -> None:
        self._store = store
        self._bus = bus
        self._deployment_id = deployment_id
        self._agent_id = agent_id
        self._role = role
        self._principal_id = principal_id
        self._group_ids = group_ids
        self._session_id = session_id
        self._capabilities = capabilities
        self._clock = clock
        self._runtime_config = runtime_config

        self._lifecycle = SessionLifecycle()
        self._instance_id = self._generate_instance_id()
        self._lease: AgentLease | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._heartbeat_failures = 0
        self._background_exception: BaseException | None = None
        self._closed = asyncio.Event()

    @staticmethod
    def _generate_instance_id() -> str:
        return uuid.uuid4().hex

    @property
    def state(self) -> ActiveAgentSessionState:
        """Current lifecycle state of this session."""
        return self._lifecycle.state

    @property
    def instance_id(self) -> str:
        """This session's current process-incarnation identifier.

        Changes on every re-registration; the `agent_id` remains stable.
        """
        return self._instance_id

    def background_exception(self) -> BaseException | None:
        """Return any exception raised by a supervised background task.

        External runtimes MUST poll this (or check it after `close()`)
        to avoid silently losing heartbeat/subscription failures.
        """
        return self._background_exception

    async def start(self) -> None:
        """Register this agent instance and start heartbeat supervision.

        Raises:
            ActiveMemoryUnavailableError: if registration fails because
                the backend cannot be reached.
        """
        self._lifecycle.transition_to(ActiveAgentSessionState.REGISTERING)
        try:
            await self._register()
        except ActiveMemoryUnavailableError:
            self._lifecycle.transition_to(ActiveAgentSessionState.FAILED)
            raise
        self._lifecycle.transition_to(ActiveAgentSessionState.ACTIVE)
        self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())

    async def _register(self) -> None:
        now = self._clock()
        identity = AgentIdentity(
            agent_id=self._agent_id,
            instance_id=self._instance_id,
            role=self._role,
            principal_id=self._principal_id,
            capabilities=self._capabilities,
            session_id=self._session_id,
            memory_group_ids=self._group_ids,
        )
        lease = AgentLease(
            lease_id=uuid.uuid4().hex,
            agent_id=self._agent_id,
            instance_id=self._instance_id,
            issued_at=now,
            expires_at=now + timedelta(seconds=self._runtime_config.lease_ttl_seconds),
            heartbeat_interval_seconds=self._runtime_config.heartbeat_interval_seconds,
        )
        presence = await self._store.register(identity, lease)
        self._lease = lease
        self._heartbeat_failures = 0
        await self._announce(AgentEventType.AGENT_REGISTERED, presence.presence_version)

    async def _announce(self, event_type: AgentEventType, state_version: int | None) -> None:
        """Publish a lifecycle pointer on the awareness bus, best effort.

        The bus is lossy by contract (`AwarenessBus`): a publish failure is
        logged and never fails the store operation it follows. One event per
        requested group, plus the deployment-wide channel, so a peer
        subscribed to either sees the pointer and re-reads current state.
        """

        now = self._clock()
        for group_id in (*self._group_ids, None):
            event = AgentEvent(
                event_id=uuid.uuid4().hex,
                event_type=event_type,
                agent_id=self._agent_id,
                instance_id=self._instance_id,
                role=self._role,
                deployment_id=self._deployment_id,
                occurred_at=now,
                group_id=group_id,
                state_version=state_version,
            )
            try:
                await self._bus.publish(event)
            except ActiveMemoryUnavailableError as exc:
                logger.debug(
                    "awareness publish skipped for agent_id=%s event=%s: %s",
                    self._agent_id,
                    event_type.value,
                    exc,
                )

    async def _heartbeat_loop(self) -> None:
        interval = self._runtime_config.heartbeat_interval_seconds
        try:
            while not self._closed.is_set():
                await asyncio.sleep(interval)
                if self._closed.is_set():
                    return
                await self._heartbeat_once()
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001 must observe all failures # NOSONAR(S5754)
            self._background_exception = exc
            logger.warning(
                "active-memory heartbeat loop failed for agent_id=%s instance_id=%s: %s",
                self._agent_id,
                self._instance_id,
                exc,
            )
            if self._lifecycle.state is ActiveAgentSessionState.ACTIVE:
                self._lifecycle.transition_to(ActiveAgentSessionState.DEGRADED)

    async def _heartbeat_once(self) -> None:
        assert self._lease is not None
        try:
            await self._store.renew(self._lease)
            self._heartbeat_failures = 0
            if self._lifecycle.state is ActiveAgentSessionState.DEGRADED:
                await self._resynchronize()
        except LeaseExpiredError:
            if self._lifecycle.state is ActiveAgentSessionState.DRAINING:
                # Shutdown is under way; the lease lapsing now is the
                # expected end state, not a reason to register again.
                return
            await self._reregister()
        except ActiveMemoryUnavailableError:
            self._heartbeat_failures += 1
            if (
                self._heartbeat_failures >= self._runtime_config.heartbeat_failure_threshold
                and self._lifecycle.state is ActiveAgentSessionState.ACTIVE
            ):
                self._lifecycle.transition_to(ActiveAgentSessionState.DEGRADED)

    async def _resynchronize(self) -> None:
        self._lifecycle.transition_to(ActiveAgentSessionState.RESYNCHRONIZING)
        try:
            presence = await self._store.get_presence(self._agent_id, self._instance_id)
            if presence is None:
                await self._reregister()
                return
            self._lifecycle.transition_to(ActiveAgentSessionState.ACTIVE)
        except ActiveMemoryUnavailableError:
            self._lifecycle.transition_to(ActiveAgentSessionState.DEGRADED)

    async def _reregister(self) -> None:
        if self._lifecycle.state is ActiveAgentSessionState.DEGRADED:
            # ADR-067: a degraded session recovers through RESYNCHRONIZING,
            # and only an expired lease found there leads to RE_REGISTERING.
            # An outage longer than the lease TTL reaches here with the lease
            # already rejected, so the resynchronization step is the
            # transition itself; skipping it was an illegal edge that ended
            # the heartbeat loop for good.
            self._lifecycle.transition_to(ActiveAgentSessionState.RESYNCHRONIZING)
        self._lifecycle.transition_to(ActiveAgentSessionState.RE_REGISTERING)
        previous = self._lease
        self._instance_id = self._generate_instance_id()
        if previous is not None:
            # The old incarnation is gone with its lease, but its presence and
            # context keys may outlive it until their own TTL (a backend that
            # persisted through the outage keeps them). Clear them so peers
            # do not list two instances of one agent; the store's unregister
            # is idempotent and inert for a lease it no longer recognizes.
            try:
                await self._store.unregister(previous)
            except ActiveMemoryUnavailableError as exc:
                logger.debug("stale presence cleanup deferred for %s: %s", self._agent_id, exc)
        try:
            await self._register()
        except ActiveMemoryUnavailableError:
            self._lifecycle.transition_to(ActiveAgentSessionState.DEGRADED)
            return
        self._lifecycle.transition_to(ActiveAgentSessionState.RESYNCHRONIZING)
        self._lifecycle.transition_to(ActiveAgentSessionState.ACTIVE)

    async def replace_context(
        self,
        *,
        objective: str | None,
        status: AgentStatus,
        working_on: tuple[str, ...] = (),
        blockers: tuple[str, ...] = (),
        expected_version: int | None = None,
    ) -> ActiveContext:
        """Atomically replace this session's active context.

        Raises:
            ActiveMemoryUnavailableError: if the session is not in the
                ACTIVE state, or if the backend cannot be reached.
            ContextVersionConflictError: if `expected_version` does not
                match the currently stored version.
            LeaseExpiredError: if the lease has expired; caller should
                allow the session to re-register before retrying.
        """
        if not self._lifecycle.can_write():
            raise ActiveMemoryUnavailableError(
                f"cannot write context while session is in state {self._lifecycle.state.value!r}"
            )
        assert self._lease is not None
        draft = ActiveContextDraft(
            objective=objective,
            status=status,
            working_on=working_on,
            blockers=blockers,
        )
        context = await self._store.put_context(self._lease, expected_version, draft)
        await self._announce(AgentEventType.AGENT_CONTEXT_UPDATED, context.version)
        return context

    async def get_peer_context(self, agent_id: str, instance_id: str) -> ActiveContext | None:
        """Read another agent instance's current context, or None if absent/expired.

        Discovery comes from `list_active()`; this reads the content a peer
        committed with `replace_context()`. It is a read of shared state,
        permitted in every non-terminal session state.
        """

        if self._lifecycle.state in (
            ActiveAgentSessionState.CLOSED,
            ActiveAgentSessionState.FAILED,
            ActiveAgentSessionState.NEW,
        ):
            raise ActiveMemoryUnavailableError(
                f"cannot read peer context while session is in state {self.state.value!r}"
            )
        return await self._store.get_context(agent_id, instance_id)

    async def list_active(
        self, *, group_id: str | None = None, roles: frozenset[str] | None = None
    ) -> tuple[AgentPresence, ...]:
        """Return currently active peers matching the given filters.

        Note: `roles` filtering beyond a single role is applied
        client-side over one or more scoped calls; the underlying port
        supports a single role filter per call.
        """
        scope = AgentScope(
            deployment_id=self._deployment_id,
            group_id=group_id,
            role=next(iter(roles)) if roles and len(roles) == 1 else None,
        )
        page = await self._store.list_active(scope, cursor=None, limit=100)
        items = page.items
        if roles and len(roles) != 1:
            items = tuple(p for p in items if p.identity.role in roles)
        return items

    async def subscribe(self, *, group_id: str | None = None) -> AsyncIterator[AgentEvent]:
        """Subscribe to awareness events scoped to this deployment.

        This is a best-effort, at-most-once stream (see `AwarenessBus`).
        Consumers MUST treat gaps as expected and re-read current state
        via `list_active()` / context reads rather than assuming
        delivery completeness.
        """
        scope = AgentScope(deployment_id=self._deployment_id, group_id=group_id)
        subscription = AgentSubscription(scope=scope)
        async for event in self._bus.subscribe(subscription):
            yield event

    async def drain(self) -> None:
        """Begin graceful shutdown: stop writes, keep lease until close()."""
        if self._lifecycle.state in (
            ActiveAgentSessionState.ACTIVE,
            ActiveAgentSessionState.DEGRADED,
        ):
            self._lifecycle.transition_to(ActiveAgentSessionState.DRAINING)
            await self._announce(AgentEventType.AGENT_DRAINING, None)

    async def _cancel_heartbeat_task(self) -> None:
        if self._heartbeat_task is None:
            return
        self._heartbeat_task.cancel()
        try:
            await self._heartbeat_task
        except asyncio.CancelledError:  # NOSONAR(S7497)
            # Expected: we just cancelled this task ourselves above, and this
            # `close()` coroutine is not itself being cancelled, so the
            # cancellation does not need to propagate further.
            pass

    async def _unregister_lease(self) -> None:
        if self._lifecycle.state != ActiveAgentSessionState.DRAINING:
            try:
                self._lifecycle.transition_to(ActiveAgentSessionState.DRAINING)
            except LifecycleTransitionError:
                pass
        if self._lease is None:
            return
        try:
            await self._store.unregister(self._lease)
            await self._announce(AgentEventType.AGENT_UNREGISTERED, None)
        except ActiveMemoryUnavailableError:
            logger.warning(
                "failed to unregister lease during close for "
                "agent_id=%s instance_id=%s; lease will expire naturally",
                self._agent_id,
                self._instance_id,
            )

    def _finalize_closed_state(self) -> None:
        if self._lifecycle.state == ActiveAgentSessionState.CLOSED:
            return
        try:
            self._lifecycle.transition_to(ActiveAgentSessionState.CLOSED)
        except LifecycleTransitionError:
            if self._lifecycle.state == ActiveAgentSessionState.NEW:
                self._lifecycle._state = ActiveAgentSessionState.CLOSED

    async def close(self) -> None:
        """Idempotently stop background tasks and unregister the lease."""
        if self._closed.is_set():
            return
        self._closed.set()

        await self._cancel_heartbeat_task()
        try:
            if self._lifecycle.state not in (
                ActiveAgentSessionState.CLOSED,
                ActiveAgentSessionState.NEW,
            ):
                await self._unregister_lease()
        finally:
            self._finalize_closed_state()
