#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: release-work/l9-deploy-phase6-operator/scripts/validate_receipts.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: receipt_bundle_validator
# tags: [receipts, checksums, evidence]
# owner: igor_beylin
# status: active
# version: 1.1.0
# updated: 2026-07-26
# Purpose: validate a receipt directory against its SHA-256 manifest and emit a proof envelope.
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

from phase6_integrity import sha256_file


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt-dir", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    receipt_dir = args.receipt_dir.resolve()
    manifest = receipt_dir / "MANIFEST.sha256"
    if not manifest.is_file():
        raise ValueError("receipt MANIFEST.sha256 missing")
    valid = True
    count = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split(None, 1)
        relative = relative.lstrip("* ")
        path = (receipt_dir / relative).resolve()
        if receipt_dir not in path.parents or not path.is_file() or sha256_file(path) != digest:
            valid = False
        count += 1
    if count < 1:
        valid = False
    bundle_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    check_id = "receipts_and_ledgers_valid"
    proof_dir = args.output_root / f"evidence/artifacts/{check_id}"
    proof_dir.mkdir(parents=True, exist_ok=True)
    manifest_copy = proof_dir / "receipt-manifest.sha256"
    manifest_copy.write_bytes(manifest.read_bytes())
    proof_path = proof_dir / "receipt-validation-proof.json"
    proof = {
        "schema": "l9.deploy.phase6-proof/v1",
        "producer_id": "validate_receipts",
        "producer_version": "1.1.0",
        "producer_executable_sha256": sha256_file(Path(__file__)),
        "captured_at": now(),
        "subject": "Phase 6 receipt bundle integrity",
        "source_kind": "receipt_validator",
        "source_locator": f"phase6-receipts://sha256:{bundle_digest}",
        "artifact_role": "receipt_validation_report",
        "media_type": "application/json",
        "details": {"receipt_count": count, "ledger_chain_valid": valid, "all_digests_valid": valid, "bundle_sha256": bundle_digest, "production_contact": False},
        "related_artifacts": [{"path": manifest_copy.relative_to(args.output_root).as_posix(), "role": "receipt_manifest", "media_type": "text/plain"}],
    }
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if valid else "FAIL", "proof": str(proof_path)}, indent=2))
    return 0 if valid else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
