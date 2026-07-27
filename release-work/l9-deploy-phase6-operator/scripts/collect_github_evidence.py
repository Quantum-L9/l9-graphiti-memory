#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: release-work/l9-deploy-phase6-operator/scripts/collect_github_evidence.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: github_evidence_collector
# tags: [github, environment, runners, workflows, evidence]
# owner: igor_beylin
# status: active
# version: 2.1.0
# updated: 2026-07-26
# Purpose: collect canonical GitHub staging environment and runner proof envelopes from the GitHub API.
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from phase6_integrity import sha256_file

SENSITIVE_KEYS = {"token", "value", "password", "private_key", "secret"}
REQUIRED_LABELS = ["self-hosted", "l9-deployment", "hetzner-private"]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def gh_json(endpoint: str) -> Any:
    process = subprocess.run(["gh", "api", endpoint], text=True, capture_output=True, check=False)
    if process.returncode != 0:
        raise RuntimeError(f"gh api failed for {endpoint}: {process.stderr.strip()}")
    return json.loads(process.stdout) if process.stdout.strip() else None


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if str(key).lower() in SENSITIVE_KEYS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="Quantum-L9/l9-deploy")
    parser.add_argument("--environment", default="staging")
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    if args.repo != "Quantum-L9/l9-deploy" or args.environment != "staging":
        raise ValueError("collector is locked to Quantum-L9/l9-deploy staging")
    owner, repository = args.repo.split("/", 1)
    environment_data = redact(gh_json(f"repos/{owner}/{repository}/environments/{args.environment}"))
    runners_data = redact(gh_json(f"repos/{owner}/{repository}/actions/runners?per_page=100"))
    if not isinstance(environment_data, dict) or not isinstance(runners_data, dict):
        raise ValueError("GitHub API returned an unexpected shape")
    protection_rules = environment_data.get("protection_rules", [])
    reviewers = []
    for rule in protection_rules if isinstance(protection_rules, list) else []:
        if isinstance(rule, dict) and rule.get("type") == "required_reviewers":
            reviewers.extend(rule.get("reviewers", []))
    protected = bool(protection_rules) and len(reviewers) >= 1
    eligible = []
    for runner in runners_data.get("runners", []):
        if not isinstance(runner, dict):
            continue
        labels = {item.get("name") for item in runner.get("labels", []) if isinstance(item, dict)}
        if set(REQUIRED_LABELS).issubset(labels) and runner.get("status") == "online":
            eligible.append(runner.get("name"))
    script_digest = sha256_file(Path(__file__))
    proof_specs = [
        (
            "protected_environment_enforced",
            "github_environment_export",
            f"github-api://repos/{args.repo}/environments/staging",
            {"environment": "staging", "protected": protected, "runner_labels": REQUIRED_LABELS, "approval_count": len(reviewers), "repository": args.repo, "production_contact": False},
            environment_data,
            "environment-api.json",
        ),
        (
            "exact_runner_labels_verified",
            "github_runner_export",
            f"github-api://repos/{args.repo}/actions/runners",
            {"environment": "staging", "protected": protected, "runner_labels": REQUIRED_LABELS if eligible else [], "approval_count": len(reviewers), "repository": args.repo, "production_contact": False},
            runners_data,
            "runners-api.json",
        ),
    ]
    outputs = {}
    for check_id, role, locator, details, raw_data, raw_name in proof_specs:
        directory = args.output_root / f"evidence/artifacts/{check_id}"
        directory.mkdir(parents=True, exist_ok=True)
        raw_path = directory / raw_name
        write_json(raw_path, raw_data)
        proof_path = directory / "github-proof.json"
        proof = {
            "schema": "l9.deploy.phase6-proof/v1",
            "producer_id": "collect_github_evidence",
            "producer_version": "2.1.0",
            "producer_executable_sha256": script_digest,
            "captured_at": now(),
            "subject": f"{check_id} GitHub API proof",
            "source_kind": "github_api_collector",
            "source_locator": locator,
            "artifact_role": "github_api_proof",
            "media_type": "application/json",
            "details": details,
            "related_artifacts": [{"path": raw_path.relative_to(args.output_root).as_posix(), "role": role, "media_type": "application/json"}],
        }
        write_json(proof_path, proof)
        outputs[check_id] = str(proof_path)
    result = {"status": "PASS" if protected and eligible else "FAIL", "eligible_runners": eligible, "proofs": outputs}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
