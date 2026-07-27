#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: release-work/l9-deploy-phase6-operator/scripts/generate_signing_key.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: signing_key_generator
# tags: [phase6, ed25519, trust-anchor, separation-of-duties]
# owner: igor_beylin
# status: active
# version: 2.0.0
# updated: 2026-07-26
# Purpose: generate a purpose-bound external Ed25519 keypair without placing private material in the pack.
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from phase6_integrity import key_fingerprint, private_key_pem, public_key_pem


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--purpose", required=True, choices=["ledger", "evidence-attestor"])
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--public-key", required=True, type=Path)
    args = parser.parse_args()
    if args.private_key.exists() or args.public_key.exists():
        raise ValueError("refusing to overwrite an existing key")
    if args.private_key.resolve().parent == Path(__file__).resolve().parents[1]:
        raise ValueError("private keys must be generated outside the handoff pack")
    args.private_key.parent.mkdir(parents=True, exist_ok=True)
    args.public_key.parent.mkdir(parents=True, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    args.private_key.write_bytes(private_key_pem(private))
    os.chmod(args.private_key, 0o600)
    args.public_key.write_bytes(public_key_pem(private.public_key()))
    os.chmod(args.public_key, 0o644)
    print(json.dumps({
        "status": "PASS",
        "purpose": args.purpose,
        "public_key_fingerprint": key_fingerprint(private.public_key()),
        "private_key_path": str(args.private_key),
        "public_key_path": str(args.public_key),
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
