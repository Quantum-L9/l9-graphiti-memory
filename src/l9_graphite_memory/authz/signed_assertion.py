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
import os
import time
from typing import Mapping

from l9_graphite_memory.errors import AuthenticationError

_SEP = "."
_PAYLOAD_SEP = "|"


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
