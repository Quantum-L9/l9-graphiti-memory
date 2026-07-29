"""External-runtime session lifecycle state machine.

Implements the state machine specified in ADR-071. This module is pure
domain logic (no I/O, no Redis dependency) so it can be unit tested
deterministically and reused identically by the Redis-backed adapter
and by the in-memory reference adapter.
"""

from __future__ import annotations

from enum import StrEnum


class LifecycleTransitionError(ValueError):
    """Raised when an illegal state transition is attempted."""


class ActiveAgentSessionState(StrEnum):
    """States in the external-runtime session lifecycle."""

    NEW = "new"
    REGISTERING = "registering"
    ACTIVE = "active"
    DEGRADED = "degraded"
    RESYNCHRONIZING = "resynchronizing"
    RE_REGISTERING = "re_registering"
    DRAINING = "draining"
    FAILED = "failed"
    CLOSED = "closed"


_ALLOWED_TRANSITIONS: dict[
    ActiveAgentSessionState, frozenset[ActiveAgentSessionState]
] = {
    ActiveAgentSessionState.NEW: frozenset({ActiveAgentSessionState.REGISTERING}),
    ActiveAgentSessionState.REGISTERING: frozenset(
        {ActiveAgentSessionState.ACTIVE, ActiveAgentSessionState.FAILED}
    ),
    ActiveAgentSessionState.ACTIVE: frozenset(
        {
            ActiveAgentSessionState.DEGRADED,
            ActiveAgentSessionState.DRAINING,
            ActiveAgentSessionState.RE_REGISTERING,
        }
    ),
    ActiveAgentSessionState.DEGRADED: frozenset(
        {
            ActiveAgentSessionState.RESYNCHRONIZING,
            ActiveAgentSessionState.DRAINING,
            ActiveAgentSessionState.FAILED,
        }
    ),
    ActiveAgentSessionState.RESYNCHRONIZING: frozenset(
        {
            ActiveAgentSessionState.ACTIVE,
            ActiveAgentSessionState.RE_REGISTERING,
            ActiveAgentSessionState.DEGRADED,
        }
    ),
    ActiveAgentSessionState.RE_REGISTERING: frozenset(
        {ActiveAgentSessionState.RESYNCHRONIZING, ActiveAgentSessionState.DEGRADED}
    ),
    ActiveAgentSessionState.DRAINING: frozenset({ActiveAgentSessionState.CLOSED}),
    ActiveAgentSessionState.FAILED: frozenset({ActiveAgentSessionState.CLOSED}),
    ActiveAgentSessionState.CLOSED: frozenset(),
}


class SessionLifecycle:
    """Enforces legal state transitions for one `ActiveAgentSession`.

    This class is intentionally synchronous and side-effect free; it
    only tracks and validates state. The owning session object is
    responsible for invoking the corresponding I/O (register, heartbeat,
    resync, etc.) before calling `transition_to()`.
    """

    def __init__(self) -> None:
        self._state = ActiveAgentSessionState.NEW

    @property
    def state(self) -> ActiveAgentSessionState:
        """Current lifecycle state."""
        return self._state

    def transition_to(self, target: ActiveAgentSessionState) -> None:
        """Transition to `target`, raising if the transition is illegal.

        Raises:
            LifecycleTransitionError: if `target` is not reachable from
                the current state.
        """
        allowed = _ALLOWED_TRANSITIONS[self._state]
        if target not in allowed:
            raise LifecycleTransitionError(
                f"illegal transition {self._state.value!r} -> {target.value!r}; "
                f"allowed targets: {sorted(s.value for s in allowed)}"
            )
        self._state = target

    def is_terminal(self) -> bool:
        """Return True if no further transitions are possible."""
        return len(_ALLOWED_TRANSITIONS[self._state]) == 0

    def can_write(self) -> bool:
        """Return True if context writes are currently permitted.

        Writes are permitted only in ACTIVE state; all other states
        (including DEGRADED and RESYNCHRONIZING) must reject writes
        because identity/version validity cannot be guaranteed.
        """
        return self._state is ActiveAgentSessionState.ACTIVE
