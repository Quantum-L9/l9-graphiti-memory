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

import re
import time

import pytest

from l9_graphite_memory.authz.signed_assertion import (
    agent_grant_from_config,
    identity_assertion_hmac,
    local_assertion_digest,
    mint_assertion,
    signing_keys_from_config,
    verify_assertion,
    verify_canonical_identity_assertion,
)
from l9_graphite_memory.contracts.identity import (
    AGENT_BINDINGS_REF,
    GLOBAL_IDENTITY_AUTHORITY_REVISION,
    IDENTITY_BINDING_REF,
    IDENTITY_PROJECTION_REF,
    IDENTITY_RESOLVER_REF,
    REQUIRED_GOVERNING_COORDINATES,
    SEMANTIC_DIGEST_COORDINATES,
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


# ---------------------------------------------------------------------------
# Canonical identity assertion (local interop digest + HMAC)
#
# The digest and HMAC below are the shared golden vector with
# Cursor-Governance. A change to either algorithm must fail both repositories.
# ---------------------------------------------------------------------------

GOLDEN_KEY = "golden-identity-hmac-key"
GOLDEN_DIGEST = "sha256:8c72474b8c0a21b465ec6d8971217455754b89008fcd61c88d51fecc47af816f"
GOLDEN_HMAC = "a937237875b4b8b3c3ed51ec151383806480c03da8e4e8606c8fc69435373b2e"
_ACTOR = "l9.actor-registry/global@1#claude-code"
_SURFACE = "l9.surface-registry/global@1#claude-code-cli"


def canonical_provenance(agent_id: str) -> dict:
    """The provenance a resolved assertion must carry for ``agent_id``.

    Shared by every door fixture: the producer coordinates, the exact
    ``.github`` authority revision the identity projection was generated from,
    the registry and projection digests, and the binding that ties the runtime
    to this actor. Memory pins these; it does not fetch what they name.
    """

    return {
        "evidence_refs": [
            IDENTITY_PROJECTION_REF,
            IDENTITY_BINDING_REF,
            f"{AGENT_BINDINGS_REF}#{agent_id}",
        ],
        "resolver_ref": IDENTITY_RESOLVER_REF,
        "governing_coordinates": {
            "actor_registry_digest": (
                "sha256:34fbe4abc246e21c28401941025317be52c109c88335577616a2648cc93c6f6f"
            ),
            "agent_bindings_ref": AGENT_BINDINGS_REF,
            "global_identity_authority_revision": GLOBAL_IDENTITY_AUTHORITY_REVISION,
            "identity_binding_ref": IDENTITY_BINDING_REF,
            "identity_projection_digest": (
                "sha256:489195262a26195a649170c63145f6ad317a99eb082bf360444164ad3ef5a667"
            ),
            "identity_projection_ref": IDENTITY_PROJECTION_REF,
            "surface_registry_digest": (
                "sha256:d7200409ff02141a274ff8c9221d31429f6a6fae27539e6d9c8d20f1a6eba988"
            ),
        },
    }


def _golden_body() -> dict:
    return {
        "schema": "l9.identity-assertion/v1",
        "subject_ref": _ACTOR,
        "product_ref": "l9-graphiti-memory:product/l9-graphite-memory",
        "resolved_dimensions": {
            "actor_identity": _ACTOR,
            "constellation_identity": "unknown",
            "release_identity": "unknown",
            "runtime_identity": "unknown",
            "surface_identity": _SURFACE,
        },
        "bindings": [
            "l9.cursor-governance/identity-binding@1",
            "l9.cursor-governance/agent-bindings@2#claude-code",
        ],
        "evidence_refs": [
            "l9.projection/cursor-governance-identity@1",
            "l9.cursor-governance/identity-binding@1",
            "l9.cursor-governance/agent-bindings@2#claude-code",
        ],
        "resolver_ref": "l9.cursor-governance/resolver/runtime-agent-identity@1",
        "governing_coordinates": {
            "actor_registry_digest": (
                "sha256:34fbe4abc246e21c28401941025317be52c109c88335577616a2648cc93c6f6f"
            ),
            "agent_bindings_ref": "l9.cursor-governance/agent-bindings@2",
            "global_identity_authority_revision": "07b0df96fc3008d55a96f804923e2177ff312295",
            "identity_binding_ref": "l9.cursor-governance/identity-binding@1",
            "identity_projection_digest": (
                "sha256:489195262a26195a649170c63145f6ad317a99eb082bf360444164ad3ef5a667"
            ),
            "identity_projection_ref": "l9.projection/cursor-governance-identity@1",
            "surface_registry_digest": (
                "sha256:d7200409ff02141a274ff8c9221d31429f6a6fae27539e6d9c8d20f1a6eba988"
            ),
        },
        "result": "resolved",
        "provenance": {
            "runtime_evidence_digest": (
                "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            )
        },
    }


def _sealed(body: dict | None = None, *, key: str = GOLDEN_KEY) -> tuple[dict, str]:
    payload = _golden_body() if body is None else body
    digest = local_assertion_digest(payload)
    sealed = dict(payload)
    sealed["assertion_digest"] = digest
    return sealed, identity_assertion_hmac(digest, key)


def _verify(
    body: dict | None = None,
    *,
    agent_id: str = "claude-code",
    key: str = GOLDEN_KEY,
    hmac_hex: str | None = None,
):
    sealed, mac = _sealed(body, key=key)
    return verify_canonical_identity_assertion(
        sealed,
        supplied_hmac=hmac_hex if hmac_hex is not None else mac,
        agent_id=agent_id,
        signing_key=key,
    )


def test_golden_identity_digest_and_hmac_vector() -> None:
    body = _golden_body()
    assert local_assertion_digest(body) == GOLDEN_DIGEST
    sealed, mac = _sealed(body)
    assert sealed["assertion_digest"] == GOLDEN_DIGEST
    assert mac == GOLDEN_HMAC
    parsed = _verify(body)
    assert parsed.schema_name == "l9.identity-assertion/v1"
    assert parsed.resolved_dimensions.actor_identity == _ACTOR
    assert parsed.resolved_dimensions.surface_identity == _SURFACE


def test_identity_digest_is_independent_of_key_order() -> None:
    body = _golden_body()
    reversed_body = {key: body[key] for key in reversed(tuple(body))}
    assert local_assertion_digest(reversed_body) == GOLDEN_DIGEST


def test_authentication_token_wire_format_is_unchanged(monkeypatch) -> None:
    """The signed-agent token stays ``agent_id.exp.nonce.hexsig`` over ``agent|exp|nonce``."""

    monkeypatch.setattr(
        "l9_graphite_memory.authz.signed_assertion.time.time", lambda: 1_700_000_000
    )
    monkeypatch.setattr(
        "l9_graphite_memory.authz.signed_assertion.os.urandom",
        lambda _n: bytes.fromhex("ab" * 16),
    )
    token = mint_assertion("claude-code", GOLDEN_KEY, ttl_seconds=3600)
    assert token == (
        "claude-code.1700003600.abababababababababababababababab."
        "16b37add9b79e72250b4560ea23571d3340a9959208e4e13598c898014f663c4"
    )
    assert verify_assertion(token, {"claude-code": GOLDEN_KEY}) == "claude-code"


@pytest.mark.parametrize("result", ["unknown", "ambiguous", "invalid"])
def test_unresolved_identity_result_is_rejected(result: str) -> None:
    body = _golden_body()
    body["result"] = result
    with pytest.raises(AuthenticationError, match=f"result is {result}"):
        _verify(body)


def test_invalid_global_schema_is_rejected() -> None:
    body = _golden_body()
    body["schema"] = "l9.identity-assertion/v0"
    with pytest.raises(AuthenticationError, match="invalid global schema"):
        _verify(body)


def test_assertion_digest_mismatch_is_rejected() -> None:
    sealed, mac = _sealed()
    sealed["assertion_digest"] = "sha256:" + "0" * 64
    with pytest.raises(AuthenticationError, match="digest mismatch"):
        verify_canonical_identity_assertion(
            sealed, supplied_hmac=mac, agent_id="claude-code", signing_key=GOLDEN_KEY
        )


def test_assertion_hmac_mismatch_is_rejected() -> None:
    with pytest.raises(AuthenticationError, match="HMAC mismatch"):
        _verify(hmac_hex="0" * 64)


def test_wrong_product_ref_is_rejected() -> None:
    body = _golden_body()
    body["product_ref"] = "l9-graphiti-memory:product/other"
    with pytest.raises(AuthenticationError, match="product_ref"):
        _verify(body)


def test_actor_prefix_must_be_the_global_registry() -> None:
    body = _golden_body()
    body["subject_ref"] = "claude-code"
    body["resolved_dimensions"] = {**body["resolved_dimensions"], "actor_identity": "claude-code"}
    with pytest.raises(AuthenticationError, match="wrong coordinate prefix"):
        _verify(body)


def test_actor_fragment_must_match_authenticated_agent() -> None:
    with pytest.raises(AuthenticationError, match="authenticated agent_id"):
        _verify(agent_id="codex")


def test_subject_ref_must_equal_actor_identity() -> None:
    body = _golden_body()
    body["subject_ref"] = "l9.actor-registry/global@1#codex"
    with pytest.raises(AuthenticationError, match="subject_ref differs"):
        _verify(body)


def test_malformed_surface_coordinate_is_rejected() -> None:
    body = _golden_body()
    body["resolved_dimensions"] = {
        **body["resolved_dimensions"],
        "surface_identity": "claude-code-cli",
    }
    with pytest.raises(AuthenticationError, match="malformed surface"):
        _verify(body)


def test_unknown_surface_is_accepted() -> None:
    body = _golden_body()
    body["resolved_dimensions"] = {**body["resolved_dimensions"], "surface_identity": "unknown"}
    parsed = _verify(body)
    assert parsed.resolved_dimensions.surface_identity == "unknown"


def test_identity_assertion_roles_are_not_authorization() -> None:
    """A valid assertion may carry injected role or namespace claims. They grant nothing."""

    body = _golden_body()
    body["roles"] = ["admin"]
    body["write_namespaces"] = ["stolen"]
    parsed = _verify(body)
    assert not hasattr(parsed, "roles") or "roles" not in parsed.model_fields_set
    dumped = parsed.model_dump()
    assert "roles" not in dumped
    assert "write_namespaces" not in dumped


# ---------------------------------------------------------------------------
# Provenance / currentness of the consumed assertion
# ---------------------------------------------------------------------------


def test_golden_body_carries_the_pinned_provenance() -> None:
    """The golden vector is the provenance contract: same refs, same revision."""

    body = _golden_body()
    expected = canonical_provenance("claude-code")
    assert body["evidence_refs"] == expected["evidence_refs"]
    assert body["resolver_ref"] == expected["resolver_ref"]
    assert body["governing_coordinates"] == expected["governing_coordinates"]
    assert set(REQUIRED_GOVERNING_COORDINATES) == set(body["governing_coordinates"])


def test_empty_evidence_refs_is_rejected() -> None:
    body = _golden_body()
    body["evidence_refs"] = []
    with pytest.raises(AuthenticationError, match="evidence_refs is empty"):
        _verify(body)


def test_missing_governing_coordinates_is_rejected() -> None:
    body = _golden_body()
    body["governing_coordinates"] = {}
    with pytest.raises(AuthenticationError, match="governing_coordinates is empty"):
        _verify(body)


@pytest.mark.parametrize("key", REQUIRED_GOVERNING_COORDINATES)
def test_missing_required_governing_coordinate_is_rejected(key: str) -> None:
    body = _golden_body()
    del body["governing_coordinates"][key]
    with pytest.raises(AuthenticationError, match=f"coordinate {key} is missing"):
        _verify(body)


def test_wrong_resolver_ref_is_rejected() -> None:
    body = _golden_body()
    body["resolver_ref"] = "l9-graphiti-memory:resolver/server-side-principal@1"
    with pytest.raises(AuthenticationError, match="resolver_ref is not"):
        _verify(body)


def test_wrong_global_authority_revision_is_rejected() -> None:
    """A candidate or stale .github revision is not the pinned identity authority."""

    body = _golden_body()
    body["governing_coordinates"]["global_identity_authority_revision"] = "c46d91e0" + "0" * 32
    with pytest.raises(AuthenticationError, match="global_identity_authority_revision is not"):
        _verify(body)


def test_wrong_identity_projection_ref_is_rejected() -> None:
    body = _golden_body()
    body["governing_coordinates"]["identity_projection_ref"] = (
        "l9.projection/cursor-governance-identity@2"
    )
    with pytest.raises(AuthenticationError, match="identity_projection_ref is not"):
        _verify(body)


def test_wrong_identity_binding_ref_is_rejected() -> None:
    body = _golden_body()
    body["governing_coordinates"]["identity_binding_ref"] = (
        "l9.cursor-governance/identity-binding@2"
    )
    with pytest.raises(AuthenticationError, match="identity_binding_ref is not"):
        _verify(body)


def test_wrong_agent_bindings_ref_is_rejected() -> None:
    body = _golden_body()
    body["governing_coordinates"]["agent_bindings_ref"] = "l9.cursor-governance/agent-bindings@1"
    with pytest.raises(AuthenticationError, match="agent_bindings_ref is not"):
        _verify(body)


def test_agent_binding_fragment_must_name_the_authenticated_agent() -> None:
    """The evidence must bind this actor, not merely some actor."""

    body = _golden_body()
    body["evidence_refs"] = [
        IDENTITY_PROJECTION_REF,
        IDENTITY_BINDING_REF,
        f"{AGENT_BINDINGS_REF}#codex",
    ]
    with pytest.raises(AuthenticationError, match="lacks .*agent-bindings@2#claude-code"):
        _verify(body)


@pytest.mark.parametrize("ref", [IDENTITY_PROJECTION_REF, IDENTITY_BINDING_REF])
def test_missing_required_evidence_ref_is_rejected(ref: str) -> None:
    body = _golden_body()
    body["evidence_refs"] = [r for r in body["evidence_refs"] if r != ref]
    with pytest.raises(AuthenticationError, match=f"lacks {re.escape(ref)}"):
        _verify(body)


@pytest.mark.parametrize("key", SEMANTIC_DIGEST_COORDINATES)
@pytest.mark.parametrize(
    "bad",
    [
        "sha256:" + "A" * 64,
        "sha256:" + "0" * 63,
        "sha1:" + "0" * 40,
        "0" * 64,
    ],
    ids=["uppercase-hex", "short", "wrong-algorithm", "no-prefix"],
)
def test_malformed_semantic_digest_is_rejected(key: str, bad: str) -> None:
    body = _golden_body()
    body["governing_coordinates"][key] = bad
    with pytest.raises(AuthenticationError, match=f"{key} is not a semantic digest"):
        _verify(body)
