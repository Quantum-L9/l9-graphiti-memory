#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/phase6/scripts/collect_repository_evidence.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: repository_evidence_collector
# tags: [git, phase5, repository, evidence]
# owner: igor_beylin
# status: active
# version: 1.1.0
# updated: 2026-07-26
# Purpose: collect repository identity, raw Git state, cleanliness, and Phase 5 validation proof without mutating the checkout.
from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import subprocess
import sys
from pathlib import Path

from phase6_integrity import sha256_file


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--check-id", required=True, choices=["phase5_validation_passed", "target_repository_source_diff_is_empty"])
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    repository = config["repository"]
    checkout = Path(repository["checkout_path"]).resolve()
    if repository["name"] != "Quantum-L9/l9-deploy" or not (checkout / ".git").exists():
        raise ValueError("collector requires the configured Quantum-L9/l9-deploy checkout")
    commit = run(["git", "rev-parse", "HEAD"], checkout)
    status = run(["git", "status", "--porcelain=v1", "--untracked-files=all"], checkout)
    if commit.returncode or status.returncode:
        raise RuntimeError(commit.stderr + status.stderr)
    commit_sha = commit.stdout.strip()
    if commit_sha != repository["expected_commit_sha"]:
        raise ValueError("checkout revision does not match the authorized target revision")
    clean = status.stdout.strip() == ""
    details = {"repository": "Quantum-L9/l9-deploy", "commit_sha": commit_sha, "worktree_clean": clean, "production_contact": False}
    suffix = "final"
    proof_dir = args.output_root / f"evidence/artifacts/{args.check_id}"
    proof_dir.mkdir(parents=True, exist_ok=True)
    commit_output = proof_dir / "git-commit.txt"
    status_output = proof_dir / "git-status.txt"
    commit_output.write_text(commit.stdout, encoding="utf-8")
    status_output.write_text(status.stdout if status.stdout else "CLEAN\n", encoding="utf-8")
    related = [
        {"path": commit_output.relative_to(args.output_root).as_posix(), "role": "repository_commit_output", "media_type": "text/plain"},
        {"path": status_output.relative_to(args.output_root).as_posix(), "role": "repository_status_output", "media_type": "text/plain"},
    ]
    if args.check_id == "phase5_validation_passed":
        command = shlex.split(repository["phase5_validation_command"])
        result = run(command, checkout)
        details.update({"phase5_status": "PASS" if result.returncode == 0 else "FAIL", "phase5_command_exit_code": result.returncode})
        suffix = "phase5"
        output_text = proof_dir / "phase5-command.txt"
        output_text.write_text("$ " + " ".join(command) + "\n\nSTDOUT\n" + result.stdout + "\nSTDERR\n" + result.stderr, encoding="utf-8")
        related.append({"path": output_text.relative_to(args.output_root).as_posix(), "role": "phase5_command_output", "media_type": "text/plain"})
    proof_path = proof_dir / "repository-proof.json"
    proof = {
        "schema": "l9.deploy.phase6-proof/v1",
        "producer_id": "collect_repository_evidence",
        "producer_version": "1.1.0",
        "producer_executable_sha256": sha256_file(Path(__file__)),
        "captured_at": now(),
        "subject": f"{args.check_id} repository proof",
        "source_kind": "repository_validator",
        "source_locator": f"repository://Quantum-L9/l9-deploy/{commit_sha}/{suffix}",
        "artifact_role": "repository_proof",
        "media_type": "application/json",
        "details": details,
        "related_artifacts": related,
    }
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if clean else "FAIL", "proof": str(proof_path)}, indent=2))
    return 0 if clean and details.get("phase5_status", "PASS") == "PASS" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
