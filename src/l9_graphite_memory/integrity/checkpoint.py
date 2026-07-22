# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/integrity/checkpoint.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Checkpoint integrity utility without taking ownership of agent checkpoint storage."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from l9_graphite_memory.admission.normalization import canonical_json


class CheckpointEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(min_length=1, max_length=100)
    checkpoint_id: str = Field(min_length=1, max_length=300)
    state: dict[str, Any]
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    signature: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    algorithm: str = "sha256"


class CheckpointIntegrity:
    """Canonicalize, hash, optionally HMAC-sign, and verify checkpoint payloads."""

    @staticmethod
    def digest(schema_version: str, checkpoint_id: str, state: dict[str, Any]) -> str:
        payload = canonical_json(
            {
                "schema_version": schema_version,
                "checkpoint_id": checkpoint_id,
                "state": state,
            }
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def seal(
        cls,
        schema_version: str,
        checkpoint_id: str,
        state: dict[str, Any],
        *,
        signing_key: bytes | None = None,
    ) -> CheckpointEnvelope:
        digest = cls.digest(schema_version, checkpoint_id, state)
        signature = (
            hmac.new(signing_key, digest.encode("ascii"), hashlib.sha256).hexdigest()
            if signing_key
            else None
        )
        return CheckpointEnvelope(
            schema_version=schema_version,
            checkpoint_id=checkpoint_id,
            state=state,
            digest=digest,
            signature=signature,
        )

    @classmethod
    def verify(
        cls,
        envelope: CheckpointEnvelope,
        *,
        signing_key: bytes | None = None,
        require_signature: bool = False,
    ) -> bool:
        expected_digest = cls.digest(
            envelope.schema_version,
            envelope.checkpoint_id,
            envelope.state,
        )
        if not hmac.compare_digest(expected_digest, envelope.digest):
            return False
        if require_signature and envelope.signature is None:
            return False
        if envelope.signature is not None:
            if signing_key is None:
                return False
            expected_signature = hmac.new(
                signing_key,
                envelope.digest.encode("ascii"),
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected_signature, envelope.signature)
        return True
