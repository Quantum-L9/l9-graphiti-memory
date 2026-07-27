#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: release-work/l9-deploy-phase6-operator/scripts/collect_final_convergence.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: final_convergence_collector
# tags: [staging, health, convergence, evidence]
# owner: igor_beylin
# status: active
# version: 1.1.0
# updated: 2026-07-26
# Purpose: validate and bind an authoritative staging health snapshot to the authorized terminal-state contract.
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from phase6_integrity import sha256_file


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--health-snapshot", required=True, type=Path)
    parser.add_argument("--convergence-id", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    snapshot = json.loads(args.health_snapshot.read_text(encoding="utf-8"))
    snapshot_schema = json.loads((Path(__file__).resolve().parents[1] / "schemas/host-health.schema.json").read_text(encoding="utf-8"))
    snapshot_errors = [
        error.message
        for error in Draft202012Validator(snapshot_schema, format_checker=FormatChecker()).iter_errors(snapshot)
    ]
    if snapshot_errors:
        raise ValueError("invalid host-health snapshot: " + "; ".join(snapshot_errors))
    expected_commit = config["repository"]["expected_commit_sha"]
    expected_run_id = config["source_release"]["workflow_run_id"]
    expected_base_url = config["target"]["base_url"]
    expected_health_path = config["target"]["health_path"]
    if snapshot["commit_sha"] != expected_commit:
        raise ValueError("host-health snapshot commit does not match the authorized target revision")
    if snapshot["workflow_run_id"] != expected_run_id:
        raise ValueError("host-health snapshot workflow run does not match the authorized source release")
    if snapshot["base_url"] != expected_base_url or snapshot["health_path"] != expected_health_path:
        raise ValueError("host-health snapshot endpoint does not match the authorized staging target")
    if snapshot["http_status"] < 200 or snapshot["http_status"] >= 300:
        raise ValueError("host-health snapshot HTTP status is not successful")
    details = {
        "environment": "staging",
        "health": snapshot.get("health"),
        "worktree_clean": True,
        "terminal_release": config["environment"]["final_terminal_state"],
        "production_contact": snapshot["production_contact"],
        "active_image_digest": snapshot["active_image_digest"],
        "active_config_identity": snapshot["active_config_identity"],
    }
    check_id = "final_staging_health_green"
    proof_dir = args.output_root / f"evidence/artifacts/{check_id}"
    proof_dir.mkdir(parents=True, exist_ok=True)
    snapshot_copy = proof_dir / "host-health-snapshot.json"
    snapshot_copy.write_bytes(args.health_snapshot.read_bytes())
    proof_path = proof_dir / "final-convergence-proof.json"
    proof = {
        "schema": "l9.deploy.phase6-proof/v1",
        "producer_id": "collect_final_convergence",
        "producer_version": "1.1.0",
        "producer_executable_sha256": sha256_file(Path(__file__)),
        "captured_at": snapshot["checked_at"],
        "subject": "final staging convergence",
        "source_kind": "final_convergence_collector",
        "source_locator": f"phase6-final://{args.convergence_id}",
        "artifact_role": "final_convergence_proof",
        "media_type": "application/json",
        "details": details,
        "related_artifacts": [{"path": snapshot_copy.relative_to(args.output_root).as_posix(), "role": "host_health_snapshot", "media_type": "application/json"}],
    }
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if details["health"] == "GREEN" else "FAIL", "proof": str(proof_path)}, indent=2))
    return 0 if details["health"] == "GREEN" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
