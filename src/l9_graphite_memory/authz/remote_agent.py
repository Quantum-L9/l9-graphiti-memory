# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/authz/remote_agent.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.7.0
#   updated: 2026-07-22

"""Signed-agent authentication for the remote (Streamable HTTP) MCP transport.

The HTTP door verifies the same evidence the stdio agent door verifies
(ADR-098), but from the request instead of the process environment, and
independently on every request:

``Authorization: Bearer <agent assertion>``
    The ``agent_id.exp.nonce.signature`` token minted by
    :func:`~l9_graphite_memory.authz.signed_assertion.mint_assertion`. Its
    HMAC proves possession of the agent's server-registered signing key.
``L9-Identity-Assertion: <base64url(JSON)>``
    The sealed ``l9.identity-assertion/v1`` object, base64url encoded so a
    non-ASCII member survives an HTTP header.
``L9-Identity-Assertion-HMAC: <hex>``
    The HMAC of that object's digest under the same agent key.

The signing keys and the grants are server-side configuration read once at
startup from ``L9_MEMORY_AGENT_SIGNING_KEYS_JSON`` and
``L9_MEMORY_AGENT_GRANTS_JSON`` — the variables the stdio door already reads,
not a second identity registry. A request can name an agent; it cannot
supply a key, a role, a tenant, or a namespace.
"""

from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from l9_graphite_memory.authz.signed_assertion import (
    AgentDoorGrant,
    agent_grant_from_config,
    agent_principal,
    decode_json_object,
    signing_keys_from_config,
    verify_assertion,
    verify_canonical_identity_assertion,
)
from l9_graphite_memory.contracts import MemoryPrincipal
from l9_graphite_memory.errors import AuthenticationError, ConfigurationError

if TYPE_CHECKING:
    from l9_graphite_memory.config import MemorySettings

IDENTITY_ASSERTION_HEADER = "L9-Identity-Assertion"
IDENTITY_ASSERTION_HMAC_HEADER = "L9-Identity-Assertion-HMAC"
SIGNING_KEYS_ENV = "L9_MEMORY_AGENT_SIGNING_KEYS_JSON"
GRANTS_ENV = "L9_MEMORY_AGENT_GRANTS_JSON"
HTTP_AGENT_AUTH_METHOD = "http-agent-assertion"
# The human door is a separate trust tier that only a local process holding
# L9_MEMORY_HUMAN_DOOR_SECRET reaches. No remote agent may carry its name.
RESERVED_AGENT_IDS = frozenset({"human"})
# Tolerated clock difference between the minting host and this server when
# the assertion's remaining lifetime is checked against the ceiling.
CLOCK_SKEW_SECONDS = 60
# Upper bound on the encoded identity assertion. The sealed object is about
# 1.5 KiB; anything this large is not one.
MAX_IDENTITY_ASSERTION_HEADER_BYTES = 16_384
# verify_assertion refusals whose wording differs between a registered and an
# unregistered agent id.
_REGISTRATION_REVEALING_REFUSALS = ("unknown agent_id", "invalid assertion signature")


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"HTTP signed-agent authentication requires {name}")
    return value


def _decode_identity_assertion(encoded: str) -> dict[str, Any]:
    if len(encoded) > MAX_IDENTITY_ASSERTION_HEADER_BYTES:
        raise AuthenticationError(f"{IDENTITY_ASSERTION_HEADER} header is too large")
    compact = encoded.strip()
    padded = compact + "=" * (-len(compact) % 4)
    try:
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        text = raw.decode("utf-8")
    except ValueError as exc:  # binascii.Error and UnicodeDecodeError are ValueErrors
        raise AuthenticationError(
            f"{IDENTITY_ASSERTION_HEADER} header is not base64url-encoded UTF-8 JSON"
        ) from exc
    return decode_json_object(text, IDENTITY_ASSERTION_HEADER)


def _bearer(authorization: str | None) -> str:
    if not authorization:
        raise AuthenticationError("missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Authorization must use Bearer scheme")
    return token


class SignedAgentAuthenticator:
    """Verify a signed agent per request and resolve its server-side grant."""

    def __init__(
        self,
        settings: MemorySettings,
        *,
        signing_keys: Mapping[str, Any],
        grants: Mapping[str, Any],
    ) -> None:
        keys = signing_keys_from_config(signing_keys)
        if not keys:
            raise ConfigurationError(f"{SIGNING_KEYS_ENV} registers no agent")
        reserved = sorted(RESERVED_AGENT_IDS & set(keys))
        if reserved:
            raise ConfigurationError(
                f"{SIGNING_KEYS_ENV} registers reserved agent id(s) {reserved}; "
                "the human door is not reachable over HTTP"
            )
        # Every registered agent's grant is validated now, so a malformed grant
        # stops the server at startup instead of surfacing on one agent's call.
        validated: dict[str, AgentDoorGrant] = {}
        for agent_id in keys:
            try:
                validated[agent_id] = agent_grant_from_config(agent_id, grants.get(agent_id))
            except AuthenticationError as exc:
                raise ConfigurationError(str(exc)) from exc
        self._settings = settings
        self._keys = keys
        self._grants = validated
        self._max_ttl = settings.http_agent_assertion_max_ttl_seconds

    @classmethod
    def from_environment(cls, settings: MemorySettings) -> SignedAgentAuthenticator:
        """Load the agent key and grant registry the stdio door also reads."""

        try:
            keys = decode_json_object(_required_env(SIGNING_KEYS_ENV), SIGNING_KEYS_ENV)
            grants = decode_json_object(_required_env(GRANTS_ENV), GRANTS_ENV)
        except AuthenticationError as exc:
            raise ConfigurationError(str(exc)) from exc
        return cls(settings, signing_keys=keys, grants=grants)

    @property
    def agent_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._keys))

    def authenticate(
        self,
        *,
        authorization: str | None,
        identity_assertion: str | None,
        identity_assertion_hmac: str | None,
    ) -> MemoryPrincipal:
        """Return the verified agent's principal, or raise AuthenticationError.

        Order: the signed assertion (key possession, expiry), its lifetime
        ceiling, then the identity evidence bound to that same agent and key,
        then the agent's grant. Nothing from the request becomes a claim.
        """

        token = _bearer(authorization)
        try:
            agent_id = verify_assertion(token, self._keys)
        except AuthenticationError as exc:
            # One answer for an unregistered agent and a bad signature, so a
            # remote caller cannot enumerate the registered agent ids. Expiry
            # and shape refusals are decided before any key lookup, name
            # nothing registered, and stay specific so a client can re-mint.
            if str(exc).startswith(_REGISTRATION_REVEALING_REFUSALS):
                raise AuthenticationError(
                    "agent assertion is not valid for a registered agent"
                ) from exc
            raise
        expires_at = int(token.split(".", 3)[1])
        if expires_at - time.time() > self._max_ttl + CLOCK_SKEW_SECONDS:
            raise AuthenticationError(
                f"agent assertion lifetime exceeds the {self._max_ttl}s ceiling "
                f"for agent_id={agent_id!r}"
            )
        if not identity_assertion:
            raise AuthenticationError(f"missing {IDENTITY_ASSERTION_HEADER} header")
        if not identity_assertion_hmac:
            raise AuthenticationError(f"missing {IDENTITY_ASSERTION_HMAC_HEADER} header")
        verify_canonical_identity_assertion(
            _decode_identity_assertion(identity_assertion),
            supplied_hmac=identity_assertion_hmac,
            agent_id=agent_id,
            signing_key=self._keys[agent_id],
        )
        return agent_principal(
            self._settings,
            agent_id,
            self._grants[agent_id],
            auth_method=HTTP_AGENT_AUTH_METHOD,
        )


def encode_identity_assertion(sealed: Mapping[str, Any]) -> str:
    """Encode a sealed identity assertion for the ``L9-Identity-Assertion`` header.

    The digest is computed over the decoded object, so any lossless JSON
    encoding verifies; this one is compact UTF-8, base64url without padding.
    """

    payload = json.dumps(dict(sealed), separators=(",", ":"), ensure_ascii=False)
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


__all__ = [
    "IDENTITY_ASSERTION_HEADER",
    "IDENTITY_ASSERTION_HMAC_HEADER",
    "SignedAgentAuthenticator",
    "encode_identity_assertion",
]
