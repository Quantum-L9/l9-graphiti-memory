#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: release-work/l9-deploy-phase6-operator/scripts/build_evidence_record.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: source_specific_evidence_attestor
# tags: [phase6, evidence, provenance, attestation]
# owner: igor_beylin
# status: active
# version: 1.0.0
# updated: 2026-07-26
# Purpose: derive policy assertions from collector proof and sign a strict evidence record.
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from phase6_integrity import load_private_key, load_public_key, public_key_pem, safe_artifact_relpath, sha256_file, sign_record

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def derive_assertions(check_id: str, details: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    production_contact = bool(details.get("production_contact", False))
    if check_id == "phase5_validation_passed":
        return {"phase5_validation_passed": details.get("phase5_status") == "PASS"}
    if check_id == "protected_environment_enforced":
        return {"protected": details.get("protected") is True and int(details.get("approval_count", 0)) >= 1}
    if check_id == "exact_runner_labels_verified":
        expected = config.get("runner", {}).get("required_labels", [])
        return {"exact_runner_labels": details.get("runner_labels") == expected}
    if check_id == "oidc_positive_exchange_passed":
        authorized = details.get("authorization_class") == "AUTHORIZED" and details.get("policy_match") is True
        return {
            "exchange_allowed": details.get("exchange_result") == "ALLOWED",
            "authorized_claim": authorized,
            "token_signature_verified": details.get("token_signature_verified_by_issuer") is True,
        }
    if check_id == "oidc_negative_exchange_denied":
        unauthorized = details.get("authorization_class") == "UNAUTHORIZED" and details.get("policy_match") is False
        return {
            "exchange_denied": details.get("exchange_result") == "DENIED",
            "unauthorized_claim": unauthorized,
            "token_signature_verified": details.get("token_signature_verified_by_issuer") is True,
            "unauthorized_exchange_allowed": details.get("exchange_result") == "ALLOWED",
        }
    if check_id == "infisical_audit_review_passed":
        return {"audit_review_clean": details.get("audit_review_clean") is True and details.get("unauthorized_access_count", 1) == 0 and details.get("redaction_verified") is True and int(details.get("event_count", 0)) > 0}
    if check_id == "immutable_image_and_attestation_verified":
        return {"attestation_verified": details.get("attestation_verified") is True}
    if check_id == "healthy_candidate_deploy_passed":
        return {"health_green": details.get("health") == "GREEN", "candidate_active": details.get("promotion_state") == "ACTIVE"}
    if check_id == "invalid_secret_containment_passed":
        return {
            "active_state_unchanged": details.get("active_state_unchanged") is True,
            "candidate_rejected": details.get("candidate_rejected") is True and details.get("promotion_state") == "REJECTED",
            "production_contact": production_contact,
        }
    if check_id == "health_failure_rollback_converged":
        image_restored = details.get("prior_image_digest") == details.get("restored_image_digest")
        config_restored = details.get("prior_config_identity") == details.get("restored_config_identity")
        state_restored = details.get("state_pointer_restored") is True
        health_green = details.get("health") == "GREEN"
        return {
            "image_restored": image_restored,
            "config_restored": config_restored,
            "state_restored": state_restored,
            "health_green": health_green,
            "rollback_converged": image_restored and config_restored and state_restored and health_green,
            "production_contact": production_contact,
        }
    if check_id == "secret_only_rotation_preserved_image_digest":
        return {
            "image_digest_unchanged": details.get("previous_image_digest") == details.get("image_digest"),
            "config_identity_changed": details.get("previous_config_identity") not in {None, details.get("config_identity")},
            "health_green": details.get("health") == "GREEN",
            "production_contact": production_contact,
        }
    if check_id == "canary_scan_zero_matches":
        return {"zero_matches": details.get("finding_count") == 0 and details.get("unauthorized_access_count") == 0, "production_contact": production_contact}
    if check_id == "receipts_and_ledgers_valid":
        return {"ledger_chain_valid": details.get("ledger_chain_valid") is True, "receipt_digests_valid": details.get("all_digests_valid") is True}
    if check_id == "target_repository_source_diff_is_empty":
        return {"worktree_clean": details.get("worktree_clean") is True, "production_contact": production_contact}
    if check_id == "final_staging_health_green":
        return {"health_green": details.get("health") == "GREEN", "staging_only": details.get("environment") == "staging", "production_contact": production_contact}
    raise ValueError(f"no assertion adapter for {check_id}")


def artifact_descriptor(path: Path, relative: str, role: str, media_type: str, check_id: str) -> dict[str, Any]:
    safe_artifact_relpath(relative, check_id)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"artifact missing or unsafe: {relative}")
    size = path.stat().st_size
    if size < 1 or size > 25 * 1024 * 1024:
        raise ValueError(f"artifact size out of bounds: {relative}")
    return {"path": relative, "sha256": sha256_file(path), "size_bytes": size, "media_type": media_type, "role": role}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--check-id", required=True)
    parser.add_argument("--proof-file", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--evidence-signing-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    policy = yaml.safe_load((ROOT / "references/GO_NO_GO_POLICY.yaml").read_text(encoding="utf-8"))
    spec = policy.get("checks", {}).get(args.check_id)
    if not isinstance(spec, dict) or "evidence_class" not in spec:
        raise ValueError("check_id is not an external evidence check")
    config = load_json(args.run_dir / "input.snapshot.json")
    proof = load_json(args.proof_file)
    schema = json.loads((ROOT / "schemas/proof-envelope.schema.json").read_text(encoding="utf-8"))
    errors = [error.message for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(proof)]
    if errors:
        raise ValueError("invalid proof envelope: " + "; ".join(errors))
    mode = config.get("evidence", {}).get("mode", "live")
    expected_producer_id = "synthetic_fixture" if proof["source_kind"] == "synthetic_test" else spec["producer_id"]
    expected_script = ROOT / ("tests/test_hardening.py" if proof["source_kind"] == "synthetic_test" else spec["producer_script"])
    if proof["producer_id"] != expected_producer_id or proof["producer_executable_sha256"] != sha256_file(expected_script):
        raise ValueError("proof producer identity does not match the packaged collector")
    if mode != "synthetic_test" and proof["source_kind"] == "synthetic_test":
        raise ValueError("synthetic proof is forbidden in live mode")
    if proof["source_kind"] != "synthetic_test" and proof["source_kind"] not in spec.get("allowed_sources", []):
        raise ValueError("proof source kind is not allowed by policy")
    if proof["source_kind"] != "synthetic_test" and not re.fullmatch(spec["locator_pattern"], proof["source_locator"]):
        raise ValueError("proof source locator does not match policy")

    proof_relative = args.proof_file.resolve().relative_to(args.artifact_root.resolve()).as_posix()
    artifacts = [artifact_descriptor(args.proof_file, proof_relative, proof["artifact_role"], proof["media_type"], args.check_id)]
    for item in proof["related_artifacts"]:
        related = (args.artifact_root / item["path"]).resolve()
        relative = related.relative_to(args.artifact_root.resolve()).as_posix()
        artifacts.append(artifact_descriptor(related, relative, item["role"], item["media_type"], args.check_id))
    required_roles = set(spec.get("artifact_requirements", {}).get("required_roles", []))
    observed_roles = {item["role"] for item in artifacts}
    missing_roles = sorted(required_roles - observed_roles)
    if missing_roles:
        raise ValueError("collector proof is missing required artifact roles: " + ", ".join(missing_roles))

    assertions = derive_assertions(args.check_id, proof["details"], config)
    expected = spec.get("assertions", {})
    status = "PASS" if all(assertions.get(key) == value for key, value in expected.items()) else "FAIL"
    record = {
        "schema": "l9.deploy.phase6-evidence-record/v3",
        "run_binding": load_json(args.run_dir / "integrity/run-binding.json"),
        "evidence_class": spec["evidence_class"],
        "check_id": args.check_id,
        "scenario_id": spec["scenario"],
        "captured_at": proof["captured_at"],
        "source": {
            "kind": proof["source_kind"],
            "locator": proof["source_locator"],
            "producer": {
                "id": proof["producer_id"],
                "version": proof["producer_version"],
                "executable_sha256": proof["producer_executable_sha256"],
            },
        },
        "status": status,
        "subject": proof["subject"],
        "assertions": assertions,
        "artifacts": artifacts,
        "details": proof["details"],
    }
    evidence_private_key = load_private_key(args.evidence_signing_key)
    embedded_evidence_key = load_public_key(args.run_dir / "integrity/evidence-attestor-public-key.pem")
    embedded_ledger_key = load_public_key(args.run_dir / "integrity/ledger-public-key.pem")
    if public_key_pem(evidence_private_key.public_key()) != public_key_pem(embedded_evidence_key):
        raise ValueError("evidence signing key does not match the run evidence authority")
    if public_key_pem(evidence_private_key.public_key()) == public_key_pem(embedded_ledger_key):
        raise ValueError("evidence signing key must be distinct from the ledger key")
    signed = sign_record(record, evidence_private_key)
    record_schema = json.loads((ROOT / "schemas" / f"{spec['evidence_class']}-evidence.schema.json").read_text(encoding="utf-8"))
    record_errors = [error.message for error in Draft202012Validator(record_schema, format_checker=FormatChecker()).iter_errors(signed)]
    if record_errors:
        raise ValueError("derived evidence record failed its class schema: " + "; ".join(record_errors))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "output": str(args.output), "check_id": args.check_id}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
