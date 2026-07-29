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
from collections.abc import AsyncIterator, Callable
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


class ActiveAgentClient:
    """Entry point for constructing external-runtime active-memory sessions.

    Instances are constructed by the runtime factory
    (`l9_graphite_memory.adapters.factory.ActiveMemoryFactory`) and bound
    to exactly one `ActiveStore`/`AwarenessBus` pair for one deployment.
    External consumer code receives an already-constructed
    `ActiveAgentClient` and never instantiates adapters itself.
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
        await self._store.register(identity, lease)
        self._lease = lease
        self._heartbeat_failures = 0

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
            await self._reregister()
        except ActiveMemoryUnavailableError:
            self._heartbeat_failures += 1
            if (
                self._heartbeat_failures
                >= self._runtime_config.heartbeat_failure_threshold
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
        self._lifecycle.transition_to(ActiveAgentSessionState.RE_REGISTERING)
        self._instance_id = self._generate_instance_id()
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
                f"cannot write context while session is in state "
                f"{self._lifecycle.state.value!r}"
            )
        assert self._lease is not None
        draft = ActiveContextDraft(
            objective=objective,
            status=status,
            working_on=working_on,
            blockers=blockers,
        )
        return await self._store.put_context(self._lease, expected_version, draft)

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

    async def subscribe(
        self, *, group_id: str | None = None
    ) -> AsyncIterator[AgentEvent]:
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

    async def drain(self) -> None:  # NOSONAR(S7503) - kept async for SDK-wide calling consistency
        """Begin graceful shutdown: stop writes, keep lease until close()."""
        if self._lifecycle.state in (
            ActiveAgentSessionState.ACTIVE,
            ActiveAgentSessionState.DEGRADED,
        ):
            self._lifecycle.transition_to(ActiveAgentSessionState.DRAINING)

    async def _cancel_heartbeat_task(self) -> None:
        if self._heartbeat_task is None:
            return
        self._heartbeat_task.cancel()
        try:
            await self._heartbeat_task
        except asyncio.CancelledError:
            # Expected: we just cancelled this task ourselves above, and this
            # `close()` coroutine is not itself being cancelled, so the
            # cancellation does not need to propagate further. # NOSONAR(S7497)
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
