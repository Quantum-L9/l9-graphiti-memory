#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: release-work/l9-deploy-phase6-operator/scripts/collect_host_evidence.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: host_evidence_collector
# tags: [ssh, docker, host, evidence]
# owner: igor_beylin
# status: active
# version: 1.0.0
# updated: 2026-07-26
# Purpose: collect non-secret staging host and Docker readiness evidence over pinned-host SSH.
from __future__ import annotations

import argparse
import json
import subprocess
import sys
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
    args = parser.parse_args()
    config = load(args.config)
    if config["environment"]["name"] != "staging" or config["environment"]["production_forbidden"] is not True:
        raise ValueError("staging lock failed")
    target = config["target"]
    host = target["host"]
    user = target["ssh_user"]
    port = int(target.get("ssh_port", 22))
    known_hosts = target["known_hosts_file"]
    if not all([host, user, known_hosts]):
        raise ValueError("host, ssh_user, and known_hosts_file are required")
    remote = """set -euo pipefail
printf '{'
printf '\"uname\":'; uname -a | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))'
printf ',\"identity\":'; id | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))'
printf ',\"docker_version\":'; docker version --format '{{json .Server.Version}}'
printf ',\"compose_version\":'; docker compose version --short | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))'
printf ',\"docker_info\":'; docker info --format '{{json .}}'
printf ',\"containers\":['
first=1
while IFS= read -r line; do
  if [ \"$first\" -eq 0 ]; then printf ','; fi
  first=0
  printf '%s' \"$line\"
done < <(docker ps --no-trunc --format '{{json .}}')
printf ']'
printf ',\"disk\":'; df -P / | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))'
printf '}\\n'
"""
    command = ["ssh", "-p", str(port), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known_hosts}", f"{user}@{host}", "bash", "-s"]
    proc = subprocess.run(command, input=remote, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    data = json.loads(proc.stdout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
