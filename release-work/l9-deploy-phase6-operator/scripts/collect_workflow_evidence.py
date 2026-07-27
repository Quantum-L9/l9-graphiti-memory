#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: release-work/l9-deploy-phase6-operator/scripts/collect_workflow_evidence.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: workflow_artifact_evidence_collector
# tags: [github-actions, artifacts, receipts, evidence]
# owner: igor_beylin
# status: active
# version: 1.1.0
# updated: 2026-07-26
# Purpose: validate a strict Phase 6 receipt, bind it to authoritative GitHub run metadata, and emit a policy-specific proof envelope.
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from phase6_integrity import sha256_file

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_KEYS = {"schema", "check_id", "repository", "run_id", "artifact_id", "captured_at", "details"}
CHECK_DETAIL_REQUIREMENTS: dict[str, set[str]] = {
    "immutable_image_and_attestation_verified": {
        "image_digest", "config_identity", "health", "promotion_state", "attestation_verified",
        "run_id", "artifact_id", "production_contact",
    },
    "healthy_candidate_deploy_passed": {
        "image_digest", "config_identity", "health", "promotion_state",
        "run_id", "artifact_id", "production_contact",
    },
    "invalid_secret_containment_passed": {
        "image_digest", "config_identity", "health", "promotion_state",
        "active_state_unchanged", "candidate_rejected", "run_id", "artifact_id", "production_contact",
    },
    "health_failure_rollback_converged": {
        "prior_image_digest", "restored_image_digest", "prior_config_identity", "restored_config_identity",
        "health", "state_pointer_restored", "run_id", "artifact_id", "production_contact",
    },
    "secret_only_rotation_preserved_image_digest": {
        "image_digest", "previous_image_digest", "config_identity", "previous_config_identity",
        "health", "promotion_state", "run_id", "artifact_id", "production_contact",
    },
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def validate_receipt(receipt: dict[str, Any], check_id: str, evidence_class: str) -> dict[str, Any]:
    observed = set(receipt)
    if observed != RECEIPT_KEYS:
        missing = sorted(RECEIPT_KEYS - observed)
        extra = sorted(observed - RECEIPT_KEYS)
        raise ValueError(f"receipt fields mismatch; missing={missing}; extra={extra}")
    if receipt["schema"] != "l9.deploy.phase6-live-receipt/v1" or receipt["check_id"] != check_id:
        raise ValueError("receipt contract or check_id mismatch")
    captured_schema = {"type": "string", "format": "date-time"}
    captured_errors = list(Draft202012Validator(captured_schema, format_checker=FormatChecker()).iter_errors(receipt["captured_at"]))
    if captured_errors:
        raise ValueError("receipt captured_at is not a valid date-time")
    details = receipt["details"]
    if not isinstance(details, dict):
        raise ValueError("receipt details must be an object")
    evidence_schema = load_object(ROOT / "schemas" / f"{evidence_class}-evidence.schema.json")
    details_schema = evidence_schema["properties"]["details"]
    errors = [error.message for error in Draft202012Validator(details_schema, format_checker=FormatChecker()).iter_errors(details)]
    if errors:
        raise ValueError("receipt details failed the evidence-class schema: " + "; ".join(errors))
    required = CHECK_DETAIL_REQUIREMENTS.get(check_id)
    if required is None:
        raise ValueError("no strict receipt detail contract exists for this workflow check")
    missing = sorted(required - set(details))
    if missing:
        raise ValueError("receipt details missing check-specific fields: " + ", ".join(missing))
    return details


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--check-id", required=True)
    parser.add_argument("--run-json", required=True, type=Path)
    parser.add_argument("--artifact-id", required=True, type=int)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    config = load_object(args.config)
    run = load_object(args.run_json)
    receipt = load_object(args.receipt)
    policy = yaml.safe_load((ROOT / "references/GO_NO_GO_POLICY.yaml").read_text(encoding="utf-8"))
    spec = policy.get("checks", {}).get(args.check_id)
    if not isinstance(spec, dict) or spec.get("producer_id") != "collect_workflow_evidence":
        raise ValueError("check is not owned by the workflow evidence collector")
    repository_name = (run.get("repository") or {}).get("full_name")
    run_id = run.get("id")
    head_sha = run.get("head_sha")
    if repository_name != "Quantum-L9/l9-deploy" or not isinstance(run_id, int) or run_id < 1:
        raise ValueError("GitHub run metadata does not identify the canonical repository and numeric run id")
    if head_sha != config["repository"]["expected_commit_sha"]:
        raise ValueError("GitHub run head_sha does not match the authorized target revision")
    details = validate_receipt(receipt, args.check_id, spec["evidence_class"])
    if receipt["repository"] != repository_name or receipt["run_id"] != run_id or receipt["artifact_id"] != args.artifact_id:
        raise ValueError("receipt is not bound to the supplied GitHub run and artifact")
    if details.get("run_id") != run_id or details.get("artifact_id") != args.artifact_id:
        raise ValueError("receipt details are not bound to the supplied GitHub run and artifact")
    if details.get("production_contact") is not False:
        raise ValueError("workflow receipt indicates production contact")

    proof_dir = args.output_root / f"evidence/artifacts/{args.check_id}"
    proof_dir.mkdir(parents=True, exist_ok=True)
    receipt_copy = proof_dir / "live-receipt.json"
    run_copy = proof_dir / "github-run.json"
    receipt_copy.write_bytes(args.receipt.read_bytes())
    run_copy.write_bytes(args.run_json.read_bytes())
    required_role = spec["artifact_requirements"]["required_roles"][0]
    proof_path = proof_dir / "workflow-proof.json"
    proof = {
        "schema": "l9.deploy.phase6-proof/v1",
        "producer_id": "collect_workflow_evidence",
        "producer_version": "1.1.0",
        "producer_executable_sha256": sha256_file(Path(__file__)),
        "captured_at": receipt.get("captured_at", now()),
        "subject": f"{args.check_id} GitHub workflow artifact proof",
        "source_kind": "workflow_artifact_collector",
        "source_locator": f"github-artifact://Quantum-L9/l9-deploy/runs/{run_id}/artifacts/{args.artifact_id}",
        "artifact_role": "workflow_artifact_proof",
        "media_type": "application/json",
        "details": details,
        "related_artifacts": [
            {"path": receipt_copy.relative_to(args.output_root).as_posix(), "role": required_role, "media_type": "application/json"},
            {"path": run_copy.relative_to(args.output_root).as_posix(), "role": "github_run_metadata", "media_type": "application/json"},
        ],
    }
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "proof": str(proof_path)}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
