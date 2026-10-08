# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_server_principal.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import json

import pytest

from l9_graphite_memory.authz.signed_assertion import mint_assertion
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.errors import AuthenticationError
from l9_graphite_memory.server import _agent_door_principal, _stdio_principal
from l9_graphite_memory.version import MEMORY_SCHEMA_VERSION
from tests.unit.test_signed_assertion import _sealed


def test_stdio_principal_uses_configured_claims_without_implicit_admin() -> None:
    settings = MemorySettings(
        local_read_namespaces=("repo-a", "workspace"),
        local_write_namespaces=("repo-a",),
        local_promote_namespaces=(),
    )
    principal = _stdio_principal(settings)
    assert principal.read_namespaces == ("repo-a", "workspace")
    assert principal.write_namespaces == ("repo-a",)
    assert principal.promote_namespaces == ()
    assert principal.is_admin is False


def _door(
    monkeypatch: pytest.MonkeyPatch,
    sealed: dict,
    mac: str,
    *,
    agent_id: str = "claude-code",
    grant: dict | None = None,
) -> None:
    key = "golden-identity-hmac-key"
    monkeypatch.setenv("L9_MEMORY_AGENTS_DOOR_SECRET", "open-sesame")
    monkeypatch.setenv("L9_MEMORY_AGENT_SIGNING_KEYS_JSON", json.dumps({agent_id: key}))
    monkeypatch.setenv("L9_MEMORY_AGENT_ASSERTION", mint_assertion(agent_id, key))
    monkeypatch.setenv("L9_MEMORY_IDENTITY_ASSERTION_JSON", json.dumps(sealed))
    monkeypatch.setenv("L9_MEMORY_IDENTITY_ASSERTION_HMAC", mac)
    monkeypatch.setenv(
        "L9_MEMORY_AGENT_GRANTS_JSON",
        json.dumps(
            {
                agent_id: grant
                or {
                    "roles": ["implementer"],
                    "read_namespaces": ["repo-a"],
                    "write_namespaces": ["repo-a"],
                    "is_admin": False,
                }
            }
        ),
    )


def test_schema_version_is_unchanged() -> None:
    assert MEMORY_SCHEMA_VERSION == "2.2.0"


def test_agents_door_requires_identity_assertion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("L9_MEMORY_AGENTS_DOOR_SECRET", "open-sesame")
    monkeypatch.setenv("L9_MEMORY_AGENT_ASSERTION", mint_assertion("claude-code", "k"))
    monkeypatch.setenv("L9_MEMORY_AGENT_SIGNING_KEYS_JSON", json.dumps({"claude-code": "k"}))
    monkeypatch.delenv("L9_MEMORY_IDENTITY_ASSERTION_JSON", raising=False)
    monkeypatch.delenv("L9_MEMORY_IDENTITY_ASSERTION_HMAC", raising=False)
    with pytest.raises(AuthenticationError, match="L9_MEMORY_IDENTITY_ASSERTION_JSON is missing"):
        _stdio_principal(MemorySettings())


def test_agents_door_requires_identity_hmac(monkeypatch: pytest.MonkeyPatch) -> None:
    sealed, _mac = _sealed()
    monkeypatch.setenv("L9_MEMORY_AGENTS_DOOR_SECRET", "open-sesame")
    monkeypatch.setenv(
        "L9_MEMORY_AGENT_ASSERTION", mint_assertion("claude-code", "golden-identity-hmac-key")
    )
    monkeypatch.setenv(
        "L9_MEMORY_AGENT_SIGNING_KEYS_JSON",
        json.dumps({"claude-code": "golden-identity-hmac-key"}),
    )
    monkeypatch.setenv("L9_MEMORY_IDENTITY_ASSERTION_JSON", json.dumps(sealed))
    monkeypatch.delenv("L9_MEMORY_IDENTITY_ASSERTION_HMAC", raising=False)
    with pytest.raises(AuthenticationError, match="L9_MEMORY_IDENTITY_ASSERTION_HMAC is missing"):
        _agent_door_principal(MemorySettings())


def test_malformed_identity_json_is_authentication_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("L9_MEMORY_AGENTS_DOOR_SECRET", "open-sesame")
    monkeypatch.setenv(
        "L9_MEMORY_AGENT_ASSERTION", mint_assertion("claude-code", "golden-identity-hmac-key")
    )
    monkeypatch.setenv(
        "L9_MEMORY_AGENT_SIGNING_KEYS_JSON",
        json.dumps({"claude-code": "golden-identity-hmac-key"}),
    )
    monkeypatch.setenv("L9_MEMORY_IDENTITY_ASSERTION_JSON", "{")
    monkeypatch.setenv("L9_MEMORY_IDENTITY_ASSERTION_HMAC", "ab")
    with pytest.raises(AuthenticationError, match="not valid JSON"):
        _agent_door_principal(MemorySettings())


def test_canonical_actor_and_surface_become_the_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    sealed, mac = _sealed()
    _door(monkeypatch, sealed, mac)
    principal = _agent_door_principal(MemorySettings())
    assert principal is not None
    assert principal.agent_id == "claude-code"
    assert principal.auth_method == "stdio-agent-assertion"
    assert principal.roles == ("implementer",)
    assert principal.write_namespaces == ("repo-a",)
    assert principal.is_admin is False


def test_unknown_surface_still_authenticates(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.unit.test_signed_assertion import _golden_body

    body = _golden_body()
    body["resolved_dimensions"] = {**body["resolved_dimensions"], "surface_identity": "unknown"}
    sealed, mac = _sealed(body)
    _door(monkeypatch, sealed, mac)
    principal = _agent_door_principal(MemorySettings())
    assert principal is not None
    assert principal.agent_id == "claude-code"


def test_identity_assertion_cannot_widen_the_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.unit.test_signed_assertion import _golden_body

    body = _golden_body()
    body["roles"] = ["admin"]
    body["write_namespaces"] = ["*"]
    body["is_admin"] = True
    sealed, mac = _sealed(body)
    _door(monkeypatch, sealed, mac)
    principal = _agent_door_principal(MemorySettings())
    assert principal is not None
    assert principal.roles == ("implementer",)
    assert principal.write_namespaces == ("repo-a",)
    assert principal.is_admin is False
    assert principal.agent_id == "claude-code"


def test_missing_identity_does_not_fall_through_to_tier3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("L9_MEMORY_HUMAN_DOOR_SECRET", raising=False)
    monkeypatch.setenv("L9_MEMORY_AGENTS_DOOR_SECRET", "open-sesame")
    monkeypatch.setenv("L9_MEMORY_AGENT_ASSERTION", mint_assertion("claude-code", "k"))
    monkeypatch.setenv("L9_MEMORY_AGENT_SIGNING_KEYS_JSON", json.dumps({"claude-code": "k"}))
    monkeypatch.setenv(
        "L9_MEMORY_AGENT_GRANTS_JSON", json.dumps({"claude-code": {"roles": ["agent"]}})
    )
    monkeypatch.delenv("L9_MEMORY_IDENTITY_ASSERTION_JSON", raising=False)
    with pytest.raises(AuthenticationError, match="IDENTITY_ASSERTION_JSON is missing"):
        _stdio_principal(MemorySettings(local_write_namespaces=("*",)))
