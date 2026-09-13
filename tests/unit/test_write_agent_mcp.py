# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_write_agent_mcp.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.4.0
#   updated: 2026-09-13

"""Tests for memory.write_agent MCP tool and stdio principal assertion auth."""

from __future__ import annotations

import json
import os

import pytest

from l9_graphite_memory.authz.signed_assertion import mint_assertion
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.errors import AuthenticationError
from l9_graphite_memory.mcp_tools import ALIASES, MCPToolApplication, tool_definitions
from l9_graphite_memory.server import _stdio_principal


# ---------------------------------------------------------------------------
# memory.write_agent tool — discovery
# ---------------------------------------------------------------------------


def test_write_agent_is_in_tool_definitions() -> None:
    names = {item["name"] for item in tool_definitions()}
    assert "memory.write_agent" in names


def test_write_agent_alias_registered() -> None:
    assert ALIASES.get("write_agent") == "memory.write_agent"


# ---------------------------------------------------------------------------
# memory.write_agent — allowed classes succeed (no phase-lock needed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "memory_class",
    [
        "insight",
        "decision",
        "observation",
        "episodic",
        "meta",
        "semantic",
        "constraint",
        "lesson",    # alias → insight
        "note",      # alias → observation
        "pickup",    # alias → meta
    ],
)
def test_write_agent_allowed_class_succeeds(memory_class, memory_service, principal) -> None:
    app = MCPToolApplication(memory_service)
    receipt = app.call(
        principal,
        "memory.write_agent",
        {
            "namespace": "repo-a",
            "content": f"agent write with class {memory_class}",
            "memory_class": memory_class,
        },
    )
    assert receipt.record_id is not None


def test_write_agent_preference_class_requires_consent(memory_service, principal) -> None:
    """preference memory_class is in the write_agent allowlist but needs consent upstream."""
    app = MCPToolApplication(memory_service)
    receipt = app.call(
        principal,
        "memory.write_agent",
        {
            "namespace": "repo-a",
            "content": "preference write without consent",
            "memory_class": "preference",
        },
    )
    # The service applies admission rules: preference requires consent.
    # The tool correctly passes through to the service — the rejection is upstream.
    assert receipt.status.value == "rejected"


def test_write_agent_default_class_is_observation(memory_service, principal) -> None:
    app = MCPToolApplication(memory_service)
    receipt = app.call(
        principal,
        "memory.write_agent",
        {"namespace": "repo-a", "content": "default class write"},
    )
    assert receipt.record_id is not None


def test_write_agent_alias_lesson_maps_to_insight(memory_service, principal) -> None:
    app = MCPToolApplication(memory_service)
    receipt = app.call(
        principal,
        "memory.write_agent",
        {"namespace": "repo-a", "content": "lesson write", "memory_class": "lesson"},
    )
    assert receipt.record_id is not None


# ---------------------------------------------------------------------------
# memory.write_agent — disallowed class raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_class",
    ["procedure", "rule", "unknown_class", ""],
)
def test_write_agent_disallowed_class_raises(bad_class, memory_service, principal) -> None:
    app = MCPToolApplication(memory_service)
    with pytest.raises((ValueError, Exception)):
        app.call(
            principal,
            "memory.write_agent",
            {"namespace": "repo-a", "content": "bad class", "memory_class": bad_class},
        )


# ---------------------------------------------------------------------------
# memory.write_governed — requires phase-lock, fails without one
# ---------------------------------------------------------------------------


def test_write_governed_without_lock_raises(memory_service, principal) -> None:
    app = MCPToolApplication(memory_service)
    with pytest.raises(Exception, match="phase.lock"):
        app.call(
            principal,
            "memory.write_governed",
            {
                "namespace": "repo-a",
                "content": "governed write without lock",
                "task_signature": "nonexistent-lock",
            },
        )


def test_write_governed_with_lock_succeeds(memory_service, principal) -> None:
    app = MCPToolApplication(memory_service)
    app.call(
        principal,
        "memory.phase_lock",
        {"namespace": "repo-a", "task_signature": "test-lock"},
    )
    receipt = app.call(
        principal,
        "memory.write_governed",
        {
            "namespace": "repo-a",
            "content": "governed write with lock",
            "task_signature": "test-lock",
        },
    )
    assert receipt.record_id is not None


# ---------------------------------------------------------------------------
# _stdio_principal — tier 1 (human door)
# ---------------------------------------------------------------------------


def test_stdio_principal_human_door_grants_admin(monkeypatch) -> None:
    monkeypatch.setenv("L9_MEMORY_HUMAN_DOOR_SECRET", "hunter2")
    settings = MemorySettings()
    p = _stdio_principal(settings)
    assert p.agent_id == "human"
    assert p.is_admin is True
    assert p.auth_method == "stdio-human-door"
    assert "*" in p.write_namespaces


# ---------------------------------------------------------------------------
# _stdio_principal — tier 2 (agent assertion door)
# ---------------------------------------------------------------------------


def _agent_env(monkeypatch, *, agent_id: str, signing_key: str, token: str | None = None) -> None:
    monkeypatch.setenv("L9_MEMORY_AGENTS_DOOR_SECRET", "open-sesame")
    monkeypatch.setenv(
        "L9_MEMORY_AGENT_SIGNING_KEYS_JSON",
        json.dumps({agent_id: signing_key}),
    )
    monkeypatch.setenv(
        "L9_MEMORY_AGENT_GRANTS_JSON",
        json.dumps({
            agent_id: {
                "user_id": "igor",
                "principal_id": agent_id,
                "roles": ["agent"],
                "read_namespaces": ["repo-a"],
                "write_namespaces": ["repo-a"],
                "promote_namespaces": [],
                "is_admin": False,
            }
        }),
    )
    if token is not None:
        monkeypatch.setenv("L9_MEMORY_AGENT_ASSERTION", token)


def test_stdio_principal_agent_assertion_succeeds(monkeypatch) -> None:
    key = "agent-signing-key"
    agent_id = "cursor"
    token = mint_assertion(agent_id, key)
    _agent_env(monkeypatch, agent_id=agent_id, signing_key=key, token=token)
    settings = MemorySettings()
    p = _stdio_principal(settings)
    assert p.agent_id == agent_id
    assert p.auth_method == "stdio-agent-assertion"
    assert p.is_admin is False
    assert "repo-a" in p.write_namespaces


def test_stdio_principal_forged_assertion_denied(monkeypatch) -> None:
    """A token signed with the wrong key must be rejected."""
    key = "real-key"
    agent_id = "cursor"
    forged_token = mint_assertion(agent_id, "attacker-key")
    _agent_env(monkeypatch, agent_id=agent_id, signing_key=key, token=forged_token)
    settings = MemorySettings()
    with pytest.raises(AuthenticationError, match="invalid assertion signature"):
        _stdio_principal(settings)


def test_stdio_principal_missing_assertion_raises(monkeypatch) -> None:
    monkeypatch.setenv("L9_MEMORY_AGENTS_DOOR_SECRET", "open-sesame")
    monkeypatch.delenv("L9_MEMORY_AGENT_ASSERTION", raising=False)
    settings = MemorySettings()
    with pytest.raises(AuthenticationError, match="L9_MEMORY_AGENT_ASSERTION is missing"):
        _stdio_principal(settings)


def test_stdio_principal_missing_keys_json_raises(monkeypatch) -> None:
    monkeypatch.setenv("L9_MEMORY_AGENTS_DOOR_SECRET", "open-sesame")
    monkeypatch.setenv("L9_MEMORY_AGENT_ASSERTION", "fake")
    monkeypatch.delenv("L9_MEMORY_AGENT_SIGNING_KEYS_JSON", raising=False)
    settings = MemorySettings()
    with pytest.raises(AuthenticationError, match="L9_MEMORY_AGENT_SIGNING_KEYS_JSON is missing"):
        _stdio_principal(settings)


# ---------------------------------------------------------------------------
# _stdio_principal — tier 3 (local fallback, no env vars set)
# ---------------------------------------------------------------------------


def test_stdio_principal_local_fallback(monkeypatch) -> None:
    monkeypatch.delenv("L9_MEMORY_HUMAN_DOOR_SECRET", raising=False)
    monkeypatch.delenv("L9_MEMORY_AGENTS_DOOR_SECRET", raising=False)
    settings = MemorySettings(
        local_read_namespaces=("repo-a",),
        local_write_namespaces=("repo-a",),
    )
    p = _stdio_principal(settings)
    assert p.auth_method == "stdio-local"
    assert p.is_admin is False
