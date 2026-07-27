#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: release-work/l9-deploy-phase6-operator/scripts/build_dispatch_payload.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: deployment_dispatch_builder
# tags: [github, repository-dispatch, deployment-request]
# owner: igor_beylin
# status: active
# version: 1.0.0
# updated: 2026-07-26
# Purpose: build and optionally send the exact staging deployment repository_dispatch payload.
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("config must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    config = load(args.config)
    if config["repository"]["name"] != "Quantum-L9/l9-deploy":
        raise ValueError("unexpected repository")
    if config["environment"]["name"] != "staging" or config["environment"]["production_forbidden"] is not True:
        raise ValueError("staging lock failed")
    if config["authorization"].get("execution_authorized") is not True:
        raise ValueError("execution authorization is not recorded")
    source = config["source_release"]
    request = {
        "schema": "l9.deployment-request/v1",
        "request_id": str(uuid.uuid4()),
        "idempotency_key": f"phase6-staging-{uuid.uuid4()}",
        "source": {"repository": source["repository"], "commit_sha": source["commit_sha"], "ref": source["ref"], "run_id": source["workflow_run_id"]},
        "artifact": {"architecture": source.get("architecture", "linux/amd64"), "image": source["image_ref"].split("@", 1)[0], "digest": source["image_digest"], "image_ref": source["image_ref"]},
        "profile": {"path": source["profile_path"], "digest": source["profile_digest"]},
        "evidence": source["evidence"],
        "target": {"environment": "staging"},
        "requested_by": config["authorization"]["operator"],
        "requested_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    body = {"event_type": "l9.release.requested.v1", "client_payload": request}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not args.execute:
        print(json.dumps({"status": "DRY_RUN", "output": str(args.output)}, indent=2))
        return 0
    if os.environ.get("PHASE6_EXECUTE") != "YES":
        raise ValueError("PHASE6_EXECUTE=YES is required for dispatch")
    proc = subprocess.run(["gh", "api", "--method", "POST", "repos/Quantum-L9/l9-deploy/dispatches", "--input", str(args.output)], text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    print(json.dumps({"status": "DISPATCHED", "repository": "Quantum-L9/l9-deploy"}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
