#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/phase6/scripts/phase6_integrity.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: evidence_integrity_library
# tags: [phase6, ed25519, evidence, ledger, integrity]
# owner: igor_beylin
# status: active
# version: 3.0.0
# updated: 2026-07-26
# Purpose: provide canonical hashing, Ed25519 signatures, and safe evidence-path validation.
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))


def load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("signing key must be an Ed25519 private key")
    return key


def load_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("trusted key must be an Ed25519 public key")
    return key


def public_key_pem(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def private_key_pem(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def key_fingerprint(key: Ed25519PublicKey) -> str:
    raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return "sha256:" + sha256_bytes(raw)


def sign_payload(payload: dict[str, Any], private_key: Ed25519PrivateKey) -> dict[str, str]:
    body = canonical(payload)
    public_key = private_key.public_key()
    return {
        "algorithm": "Ed25519",
        "key_fingerprint": key_fingerprint(public_key),
        "payload_sha256": sha256_bytes(body),
        "signature": b64url_encode(private_key.sign(body)),
    }


def verify_payload(payload: dict[str, Any], attestation: dict[str, Any], public_key: Ed25519PublicKey) -> list[str]:
    errors: list[str] = []
    if attestation.get("algorithm") != "Ed25519":
        errors.append("attestation algorithm must be Ed25519")
    expected_fingerprint = key_fingerprint(public_key)
    if attestation.get("key_fingerprint") != expected_fingerprint:
        errors.append("attestation key fingerprint does not match trusted key")
    body = canonical(payload)
    if attestation.get("payload_sha256") != sha256_bytes(body):
        errors.append("attestation payload digest mismatch")
    try:
        signature = b64url_decode(str(attestation.get("signature", "")))
        public_key.verify(signature, body)
    except (InvalidSignature, ValueError, TypeError):
        errors.append("attestation signature invalid")
    return errors


def sign_record(record: dict[str, Any], private_key: Ed25519PrivateKey) -> dict[str, Any]:
    unsigned = {key: value for key, value in record.items() if key != "attestation"}
    signed = dict(unsigned)
    signed["attestation"] = sign_payload(unsigned, private_key)
    return signed


def verify_record(record: dict[str, Any], public_key: Ed25519PublicKey) -> list[str]:
    attestation = record.get("attestation")
    if not isinstance(attestation, dict):
        return ["record attestation missing"]
    unsigned = {key: value for key, value in record.items() if key != "attestation"}
    return verify_payload(unsigned, attestation, public_key)


def sign_event(event: dict[str, Any], private_key: Ed25519PrivateKey) -> dict[str, Any]:
    unsigned = {key: value for key, value in event.items() if key != "signature"}
    signed = dict(unsigned)
    signed["signature"] = sign_payload(unsigned, private_key)
    return signed


def verify_event(event: dict[str, Any], public_key: Ed25519PublicKey) -> list[str]:
    signature = event.get("signature")
    if not isinstance(signature, dict):
        return ["ledger event signature missing"]
    unsigned = {key: value for key, value in event.items() if key != "signature"}
    return verify_payload(unsigned, signature, public_key)


def safe_artifact_relpath(value: str, check_id: str) -> PurePosixPath:
    if "\\" in value:
        raise ValueError("artifact paths must use POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError("artifact path must be normalized and relative")
    expected = ("evidence", "artifacts", check_id)
    if tuple(path.parts[:3]) != expected or len(path.parts) < 4:
        raise ValueError(f"artifact path must be under evidence/artifacts/{check_id}/")
    if path.name in {"", ".", ".."}:
        raise ValueError("artifact filename is invalid")
    return path


def contained_path(root: Path, relative: PurePosixPath) -> Path:
    root_resolved = root.resolve()
    candidate = (root / Path(*relative.parts)).resolve()
    if os.path.commonpath([str(root_resolved), str(candidate)]) != str(root_resolved):
        raise ValueError("artifact path escapes evidence root")
    return candidate
