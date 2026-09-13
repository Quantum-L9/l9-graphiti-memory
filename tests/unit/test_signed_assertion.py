# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_signed_assertion.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.4.0
#   updated: 2026-09-13

"""Unit tests for HMAC-SHA256 signed agent assertions (trust-model-2)."""

from __future__ import annotations

import time

import pytest

from l9_graphite_memory.authz.signed_assertion import mint_assertion, verify_assertion
from l9_graphite_memory.errors import AuthenticationError

_KEY = "super-secret-signing-key"
_AGENT = "cursor"


def test_mint_and_verify_round_trip() -> None:
    token = mint_assertion(_AGENT, _KEY)
    agent_id = verify_assertion(token, {_AGENT: _KEY})
    assert agent_id == _AGENT


def test_verify_returns_agent_id() -> None:
    token = mint_assertion("claude-code", _KEY, ttl_seconds=60)
    result = verify_assertion("claude-code." + token.split(".", 1)[1], {"claude-code": _KEY})
    assert result == "claude-code"


def test_multiple_agents_each_verified_with_own_key() -> None:
    keys = {"agent-a": "key-a", "agent-b": "key-b"}
    tok_a = mint_assertion("agent-a", "key-a")
    tok_b = mint_assertion("agent-b", "key-b")
    assert verify_assertion(tok_a, keys) == "agent-a"
    assert verify_assertion(tok_b, keys) == "agent-b"


def test_bad_signature_rejected() -> None:
    token = mint_assertion(_AGENT, _KEY)
    # Corrupt the last character of the signature
    corrupted = token[:-1] + ("0" if token[-1] != "0" else "1")
    with pytest.raises(AuthenticationError, match="invalid assertion signature"):
        verify_assertion(corrupted, {_AGENT: _KEY})


def test_wrong_key_rejected() -> None:
    token = mint_assertion(_AGENT, _KEY)
    with pytest.raises(AuthenticationError, match="invalid assertion signature"):
        verify_assertion(token, {_AGENT: "wrong-key"})


def test_unknown_agent_id_rejected() -> None:
    token = mint_assertion(_AGENT, _KEY)
    with pytest.raises(AuthenticationError, match="unknown agent_id"):
        verify_assertion(token, {"other-agent": _KEY})


def test_expired_assertion_rejected(monkeypatch) -> None:
    token = mint_assertion(_AGENT, _KEY, ttl_seconds=1)
    # Advance time past expiry
    monkeypatch.setattr("l9_graphite_memory.authz.signed_assertion.time", _FakeTime(offset=10))
    with pytest.raises(AuthenticationError, match="expired"):
        verify_assertion(token, {_AGENT: _KEY})


def test_malformed_token_too_few_parts() -> None:
    with pytest.raises(AuthenticationError, match="malformed"):
        verify_assertion("agent.123.nonce", {_AGENT: _KEY})


def test_malformed_token_non_integer_exp() -> None:
    with pytest.raises(AuthenticationError, match="malformed"):
        verify_assertion(f"{_AGENT}.notanumber.nonce.sig", {_AGENT: _KEY})


def test_agent_id_with_dot_raises_on_mint() -> None:
    with pytest.raises(ValueError, match="must not contain"):
        mint_assertion("bad.agent", _KEY)


def test_empty_agent_id_raises_on_mint() -> None:
    with pytest.raises(ValueError):
        mint_assertion("", _KEY)


class _FakeTime:
    """Drop-in replacement for the ``time`` module with a fixed offset."""

    def __init__(self, offset: float) -> None:
        self._offset = offset

    def time(self) -> float:
        return time.time() + self._offset
