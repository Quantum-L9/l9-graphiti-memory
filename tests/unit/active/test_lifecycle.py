"""Unit tests for l9_graphite_memory.active.lifecycle."""

from __future__ import annotations

import pytest

from l9_graphite_memory.active.lifecycle import (
    ActiveAgentSessionState,
    LifecycleTransitionError,
    SessionLifecycle,
)


def test_initial_state_is_new() -> None:
    lifecycle = SessionLifecycle()
    assert lifecycle.state is ActiveAgentSessionState.NEW


def test_new_to_registering_allowed() -> None:
    lifecycle = SessionLifecycle()
    lifecycle.transition_to(ActiveAgentSessionState.REGISTERING)
    assert lifecycle.state is ActiveAgentSessionState.REGISTERING


def test_new_to_active_disallowed() -> None:
    lifecycle = SessionLifecycle()
    with pytest.raises(LifecycleTransitionError):
        lifecycle.transition_to(ActiveAgentSessionState.ACTIVE)


def test_full_happy_path_to_closed() -> None:
    lifecycle = SessionLifecycle()
    lifecycle.transition_to(ActiveAgentSessionState.REGISTERING)
    lifecycle.transition_to(ActiveAgentSessionState.ACTIVE)
    lifecycle.transition_to(ActiveAgentSessionState.DRAINING)
    lifecycle.transition_to(ActiveAgentSessionState.CLOSED)
    assert lifecycle.is_terminal()


def test_degraded_recovery_path() -> None:
    lifecycle = SessionLifecycle()
    lifecycle.transition_to(ActiveAgentSessionState.REGISTERING)
    lifecycle.transition_to(ActiveAgentSessionState.ACTIVE)
    lifecycle.transition_to(ActiveAgentSessionState.DEGRADED)
    lifecycle.transition_to(ActiveAgentSessionState.RESYNCHRONIZING)
    lifecycle.transition_to(ActiveAgentSessionState.ACTIVE)
    assert lifecycle.state is ActiveAgentSessionState.ACTIVE


def test_expired_lease_reregistration_path() -> None:
    lifecycle = SessionLifecycle()
    lifecycle.transition_to(ActiveAgentSessionState.REGISTERING)
    lifecycle.transition_to(ActiveAgentSessionState.ACTIVE)
    lifecycle.transition_to(ActiveAgentSessionState.RE_REGISTERING)
    lifecycle.transition_to(ActiveAgentSessionState.RESYNCHRONIZING)
    lifecycle.transition_to(ActiveAgentSessionState.ACTIVE)
    assert lifecycle.state is ActiveAgentSessionState.ACTIVE


def test_can_write_only_when_active() -> None:
    lifecycle = SessionLifecycle()
    assert lifecycle.can_write() is False
    lifecycle.transition_to(ActiveAgentSessionState.REGISTERING)
    assert lifecycle.can_write() is False
    lifecycle.transition_to(ActiveAgentSessionState.ACTIVE)
    assert lifecycle.can_write() is True
    lifecycle.transition_to(ActiveAgentSessionState.DEGRADED)
    assert lifecycle.can_write() is False


def test_closed_is_terminal_with_no_transitions() -> None:
    lifecycle = SessionLifecycle()
    lifecycle.transition_to(ActiveAgentSessionState.REGISTERING)
    lifecycle.transition_to(ActiveAgentSessionState.FAILED)
    lifecycle.transition_to(ActiveAgentSessionState.CLOSED)
    with pytest.raises(LifecycleTransitionError):
        lifecycle.transition_to(ActiveAgentSessionState.ACTIVE)
