# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/authz/signed_assertion.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.4.0
#   updated: 2026-09-13

"""HMAC-SHA256 agent assertion tokens for stdio MCP trust-model-2.

Format: ``<agent_id>.<exp_unix>.<nonce>.<hex_signature>``

The payload signed is the ASCII string ``<agent_id>|<exp_unix>|<nonce>``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from l9_graphite_memory.contracts.identity import (
    ACTOR_REGISTRY_PREFIX,
    IDENTITY_ASSERTION_SCHEMA,
    MEMORY_PRODUCT_REF,
    SURFACE_REGISTRY_PREFIX,
    IdentityAssertion,
)
from l9_graphite_memory.errors import AuthenticationError

_SEP = "."
_PAYLOAD_SEP = "|"


class AgentDoorGrant(BaseModel):
    """Typed principal claims for one agent id in ``L9_MEMORY_AGENT_GRANTS_JSON``.

    The bearer door has validated its claims at the trust boundary since
    :class:`~l9_graphite_memory.config.TokenPrincipalConfig`; this is the same
    kind of boundary and now resolves the same way. Hand-coercing the decoded
    JSON instead is how ``is_admin`` became reachable from a string: Python's
    ``bool("false")`` is ``True``, so a quoted flag in trusted configuration
    silently produced a tenant administrator. Pydantic parses ``"false"`` as
    ``False`` and refuses anything that is not a boolean at all.

    ``extra="forbid"`` matches the precedent and is deliberate rather than
    incidental: an unrecognised key in this blob is malformed trusted
    configuration, and the door has no way to honour it. ``maintain_namespaces``
    is one such key — the door has never granted maintain authority, so a
    config carrying it was silently having it dropped. It is now an error that
    says so, which is fail-closed and grants nothing new.
    """

    model_config = ConfigDict(extra="forbid")

    principal_id: str | None = Field(default=None, min_length=1, max_length=200)
    user_id: str | None = Field(default=None, max_length=200)
    roles: tuple[str, ...] = ()
    read_namespaces: tuple[str, ...] = ()
    write_namespaces: tuple[str, ...] = ()
    promote_namespaces: tuple[str, ...] = ()
    is_admin: bool = False


def signing_keys_from_config(raw: Mapping[str, Any]) -> dict[str, str]:
    """Validate decoded ``L9_MEMORY_AGENT_SIGNING_KEYS_JSON`` key material.

    :func:`verify_assertion` passes whatever it is given to ``hmac.new``, which
    raises ``TypeError`` for a non-string, non-bytes key. That is not an
    authentication outcome and escapes the door as an unhandled error, so key
    material is typed here instead — before any assertion is checked against it.
    """

    validated: dict[str, str] = {}
    for agent_id, key_material in raw.items():
        if not isinstance(agent_id, str) or not agent_id:
            raise AuthenticationError(
                "L9_MEMORY_AGENT_SIGNING_KEYS_JSON keys must be non-empty agent ids"
            )
        if not isinstance(key_material, str) or not key_material:
            raise AuthenticationError(
                "L9_MEMORY_AGENT_SIGNING_KEYS_JSON key material for "
                f"agent_id={agent_id!r} must be a non-empty string"
            )
        validated[agent_id] = key_material
    return validated


def agent_grant_from_config(agent_id: str, raw: Any) -> AgentDoorGrant:
    """Validate one agent's decoded grant object, or fail closed.

    An absent, empty, or non-object grant keeps the door's existing message;
    a present but malformed one is reported per offending field rather than
    coerced into a principal.
    """

    if not raw or not isinstance(raw, dict):
        raise AuthenticationError(
            f"no grants configured for agent_id={agent_id!r} in L9_MEMORY_AGENT_GRANTS_JSON"
        )
    try:
        return AgentDoorGrant.model_validate(raw)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or '<root>'}: {error['msg']}"
            for error in exc.errors()
        )
        raise AuthenticationError(
            f"malformed signed-agent grant for agent_id={agent_id!r} in "
            f"L9_MEMORY_AGENT_GRANTS_JSON: {details}"
        ) from exc


def mint_assertion(
    agent_id: str,
    signing_key: str | bytes,
    *,
    ttl_seconds: int = 3600,
) -> str:
    """Mint a signed assertion token for *agent_id*.

    Returns a dot-separated string ``agent_id.exp_unix.nonce.hex_sig``.
    The ``signing_key`` may be a str (UTF-8 encoded) or raw bytes.
    """
    if not agent_id or _SEP in agent_id:
        raise ValueError(f"agent_id must be non-empty and must not contain '.': {agent_id!r}")
    exp = int(time.time()) + ttl_seconds
    nonce = os.urandom(16).hex()
    payload = f"{agent_id}{_PAYLOAD_SEP}{exp}{_PAYLOAD_SEP}{nonce}"
    key = signing_key.encode("utf-8") if isinstance(signing_key, str) else signing_key
    sig = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{agent_id}{_SEP}{exp}{_SEP}{nonce}{_SEP}{sig}"


def verify_assertion(
    assertion: str,
    keys_by_agent_id: Mapping[str, str | bytes],
) -> str:
    """Verify *assertion* and return the verified ``agent_id``.

    Raises :class:`~l9_graphite_memory.errors.AuthenticationError` on any
    failure (malformed token, unknown agent, bad signature, expiry).
    """
    parts = assertion.split(_SEP, 3)
    if len(parts) != 4:
        raise AuthenticationError("malformed agent assertion: expected 4 dot-separated parts")
    agent_id, raw_exp, nonce, supplied_sig = parts

    try:
        exp = int(raw_exp)
    except ValueError:
        raise AuthenticationError("malformed agent assertion: exp is not an integer")

    if time.time() > exp:
        raise AuthenticationError(f"agent assertion expired for agent_id={agent_id!r}")

    key_material = keys_by_agent_id.get(agent_id)
    if key_material is None:
        raise AuthenticationError(f"unknown agent_id in assertion: {agent_id!r}")

    key = key_material.encode("utf-8") if isinstance(key_material, str) else key_material
    payload = f"{agent_id}{_PAYLOAD_SEP}{exp}{_PAYLOAD_SEP}{nonce}"
    expected_sig = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_sig, supplied_sig):
        raise AuthenticationError(f"invalid assertion signature for agent_id={agent_id!r}")

    return agent_id


def local_assertion_digest(assertion: Mapping[str, Any]) -> str:
    """Local interop digest for ``l9.identity-assertion/v1``.

    This is not global L9 semantic law. ``.github`` requires ``assertion_digest``
    and does not define a canonicalization algorithm, so both sides of this
    door share one implementation rule: copy the object, drop
    ``assertion_digest``, and hash UTF-8 JSON with sorted keys and compact
    separators. The result is prefixed ``sha256:``.
    """

    body = {key: value for key, value in assertion.items() if key != "assertion_digest"}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def identity_assertion_hmac(assertion_digest: str, signing_key: str | bytes) -> str:
    """HMAC-SHA256 of the ASCII assertion digest under the agent's signing key.

    Transport integrity for the identity assertion. It grants no role or
    namespace. The key is the same per-agent secret the signed-agent token uses.
    """

    if not isinstance(assertion_digest, str) or not assertion_digest.isascii():
        raise AuthenticationError("identity assertion digest is not ASCII")
    key = signing_key.encode("utf-8") if isinstance(signing_key, str) else signing_key
    return hmac.new(key, assertion_digest.encode("ascii"), hashlib.sha256).hexdigest()


def _same_secret(expected: str, supplied: object) -> bool:
    if not isinstance(supplied, str):
        return False
    candidate = supplied.strip().lower()
    if len(candidate) != len(expected):
        return False
    return hmac.compare_digest(expected, candidate)


def _coordinate_fragment(value: object, prefix: str) -> str | None:
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    fragment = value[len(prefix) :]
    if not fragment or "#" in fragment:
        return None
    return fragment


def verify_canonical_identity_assertion(
    raw: Mapping[str, Any],
    *,
    supplied_hmac: str,
    agent_id: str,
    signing_key: str | bytes,
) -> IdentityAssertion:
    """Verify canonical identity evidence against the already-authenticated agent.

    Authentication of the signed-agent token has already proved key possession
    for ``agent_id``. This checks that the supplied identity assertion was
    resolved, was not altered in transport, and names that same actor. It does
    not read roles or namespaces from the assertion.
    """

    if not isinstance(raw, Mapping):
        raise AuthenticationError("malformed identity assertion JSON")
    if raw.get("schema") != IDENTITY_ASSERTION_SCHEMA:
        raise AuthenticationError("invalid global schema value")
    try:
        parsed = IdentityAssertion.model_validate(dict(raw))
    except ValidationError as exc:
        raise AuthenticationError(f"malformed identity assertion: {exc}") from exc

    expected_digest = local_assertion_digest(raw)
    if not _same_secret(expected_digest, raw.get("assertion_digest")):
        raise AuthenticationError("identity assertion digest mismatch")
    expected_hmac = identity_assertion_hmac(expected_digest, signing_key)
    if not _same_secret(expected_hmac, supplied_hmac):
        raise AuthenticationError("identity assertion HMAC mismatch")

    if parsed.result != "resolved":
        raise AuthenticationError(f"identity assertion result is {parsed.result}")
    if parsed.product_ref != MEMORY_PRODUCT_REF:
        raise AuthenticationError(
            "identity assertion product_ref is not l9-graphiti-memory:product/l9-graphite-memory"
        )
    actor = _coordinate_fragment(parsed.resolved_dimensions.actor_identity, ACTOR_REGISTRY_PREFIX)
    if actor is None:
        raise AuthenticationError("actor identity has the wrong coordinate prefix")
    if actor != agent_id:
        raise AuthenticationError("actor identity does not match the authenticated agent_id")
    if parsed.subject_ref != parsed.resolved_dimensions.actor_identity:
        raise AuthenticationError("subject_ref differs from actor identity")
    surface = parsed.resolved_dimensions.surface_identity
    surface_ok = surface in (None, "unknown") or _coordinate_fragment(
        surface, SURFACE_REGISTRY_PREFIX
    )
    if not surface_ok:
        raise AuthenticationError("malformed surface coordinate")
    return parsed
