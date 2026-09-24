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

from l9_graphite_memory.authz.signed_assertion import (
    agent_grant_from_config,
    mint_assertion,
    signing_keys_from_config,
    verify_assertion,
)
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


# ---------------------------------------------------------------------------
# Typed trust boundary (F-AUTH-1)
#
# The door used to hand-coerce the decoded JSON of
# L9_MEMORY_AGENT_GRANTS_JSON and L9_MEMORY_AGENT_SIGNING_KEYS_JSON. These are
# the negative cases that coercion admitted: each one is malformed *trusted*
# configuration, and each must fail closed rather than produce a principal.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("falsey", ["false", "False", "0", "no", "off"])
def test_stringy_false_never_grants_admin(falsey: str) -> None:
    """The escalation this finding names.

    ``bool("false")`` is ``True`` in Python, so a quoted flag in trusted
    configuration used to make the agent a tenant administrator. Asserted on
    every spelling an operator might reasonably write.
    """

    grant = agent_grant_from_config(_AGENT, {"is_admin": falsey})
    assert grant.is_admin is False


@pytest.mark.parametrize("truthy", ["true", "True", "1", "yes", "on", True])
def test_admin_still_reachable_from_a_deliberate_boolean(truthy: object) -> None:
    """Fail-closed must not mean unreachable: a real claim still works."""

    assert agent_grant_from_config(_AGENT, {"is_admin": truthy}).is_admin is True


@pytest.mark.parametrize("bad", ["banana", 2, -1, [], {}, None])
def test_non_boolean_admin_claim_fails_closed(bad: object) -> None:
    with pytest.raises(AuthenticationError, match="malformed signed-agent grant"):
        agent_grant_from_config(_AGENT, {"is_admin": bad})


@pytest.mark.parametrize(
    "field",
    ["roles", "read_namespaces", "write_namespaces", "promote_namespaces"],
)
@pytest.mark.parametrize("bad", [{"a": 1}, "single-string", 5, None, [1, 2]])
def test_malformed_list_claims_fail_closed(field: str, bad: object) -> None:
    """Previously: a dict iterated to its keys, a str to its characters, and
    anything else silently became an empty tuple — a malformed grant that
    looked like a deliberate revocation."""

    with pytest.raises(AuthenticationError, match="malformed signed-agent grant"):
        agent_grant_from_config(_AGENT, {field: bad})


def test_unknown_grant_key_fails_closed() -> None:
    """``extra="forbid"``, matching TokenPrincipalConfig.

    ``maintain_namespaces`` is the live example: the door never granted
    maintain authority, so a config carrying it was having it silently dropped.
    """

    with pytest.raises(AuthenticationError, match="maintain_namespaces"):
        agent_grant_from_config(_AGENT, {"maintain_namespaces": ["repo-a"]})


def test_valid_grant_retains_existing_behavior() -> None:
    grant = agent_grant_from_config(
        _AGENT,
        {
            "principal_id": "cursor",
            "user_id": "igor",
            "roles": ["agent"],
            "read_namespaces": ["repo-a"],
            "write_namespaces": ["repo-a"],
            "promote_namespaces": [],
            "is_admin": False,
        },
    )
    assert grant.principal_id == "cursor"
    assert grant.user_id == "igor"
    assert grant.roles == ("agent",)
    assert grant.read_namespaces == ("repo-a",)
    assert grant.write_namespaces == ("repo-a",)
    assert grant.promote_namespaces == ()
    assert grant.is_admin is False


@pytest.mark.parametrize("absent", [None, {}, [], "", 0])
def test_absent_or_non_object_grant_keeps_the_existing_message(absent: object) -> None:
    with pytest.raises(AuthenticationError, match="no grants configured for agent_id"):
        agent_grant_from_config(_AGENT, absent)


@pytest.mark.parametrize("bad_key", [5, None, {"k": "v"}, ["k"], True, ""])
def test_non_string_key_material_fails_closed(bad_key: object) -> None:
    """Previously a TypeError from hmac.new escaped the auth door.

    An unhandled TypeError is not an authentication outcome; it is a crash in
    the component that decides authority.
    """

    with pytest.raises(AuthenticationError, match="must be a non-empty string"):
        signing_keys_from_config({_AGENT: bad_key})


def test_non_string_agent_id_key_fails_closed() -> None:
    with pytest.raises(AuthenticationError, match="non-empty agent ids"):
        signing_keys_from_config({"": _KEY})


def test_valid_signing_keys_pass_through() -> None:
    assert signing_keys_from_config({_AGENT: _KEY}) == {_AGENT: _KEY}


def test_the_door_fails_closed_where_verify_assertion_alone_raises_typeerror() -> None:
    """The contrast, proven rather than asserted.

    ``verify_assertion`` still raises ``TypeError`` when handed unvalidated
    non-string key material — that is the raw primitive's behaviour and it is
    left as it was. What changed is the door: it types the key material first,
    so the same configuration now produces an authentication failure instead of
    an unhandled crash in the component that decides authority.
    """

    token = mint_assertion(_AGENT, _KEY)

    with pytest.raises(TypeError):
        verify_assertion(token, {_AGENT: 5})  # type: ignore[dict-item]

    with pytest.raises(AuthenticationError, match="must be a non-empty string"):
        signing_keys_from_config({_AGENT: 5})
