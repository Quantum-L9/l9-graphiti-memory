# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_checkpoint_integrity.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from l9_graphite_memory.integrity import CheckpointIntegrity


def test_checkpoint_digest_is_deterministic_and_signature_detects_tampering() -> None:
    key = b"test-signing-key"
    first = CheckpointIntegrity.seal(
        "1", "checkpoint-1", {"b": 2, "a": 1}, signing_key=key
    )
    second = CheckpointIntegrity.seal(
        "1", "checkpoint-1", {"a": 1, "b": 2}, signing_key=key
    )

    assert first.digest == second.digest
    assert CheckpointIntegrity.verify(first, signing_key=key, require_signature=True)
    tampered = first.model_copy(update={"state": {"a": 99, "b": 2}})
    assert not CheckpointIntegrity.verify(
        tampered, signing_key=key, require_signature=True
    )
