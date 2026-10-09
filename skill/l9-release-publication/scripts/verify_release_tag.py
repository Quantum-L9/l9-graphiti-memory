#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: skill/l9-release-publication/scripts/verify_release_tag.py
#   layer: skill
#   owner: memory-control-plane
#   status: active
#   version: 2.6.0
#   updated: 2026-07-22

"""Verify an annotated tag object and its peeled commit.

Print one JSON object on stdout.

Exit 0: MATCH
Exit 1: MISMATCH
Exit 2: REMOTE_ABSENT (remote requested, ref missing, --require-remote not set)
Exit 3: TRANSPORT_BLOCKED
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any


def _run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _emit(payload: dict[str, Any], code: int) -> int:
    print(json.dumps(payload, sort_keys=True))
    return code


def local_identity(repo: str, tag: str) -> tuple[str, str, str]:
    kind = _run(["git", "cat-file", "-t", tag], cwd=repo)
    obj = _run(["git", "rev-parse", tag], cwd=repo)
    peeled = _run(["git", "rev-parse", f"{tag}^{{}}"], cwd=repo)
    return (
        kind.stdout.strip() if kind.returncode == 0 else "",
        obj.stdout.strip() if obj.returncode == 0 else "",
        peeled.stdout.strip() if peeled.returncode == 0 else "",
    )


def gh_api(path: str) -> tuple[int, str, str]:
    result = _run(["gh", "api", path])
    return result.returncode, result.stdout, result.stderr


def remote_identity(remote: str, tag: str) -> tuple[str, dict[str, str]]:
    code, out, err = gh_api(f"repos/{remote}/git/ref/tags/{tag}")
    if code != 0:
        blob = f"{out}\n{err}"
        if "404" in blob:
            return "absent", {}
        return "blocked", {"detail": err.strip() or out.strip()}
    try:
        ref = json.loads(out)
    except json.JSONDecodeError:
        return "blocked", {"detail": "remote ref response was not JSON"}
    obj = ref.get("object") if isinstance(ref, dict) else None
    if not isinstance(obj, dict):
        return "blocked", {"detail": "remote ref has no object"}
    sha = str(obj.get("sha") or "")
    kind = str(obj.get("type") or "")
    if kind != "tag" or not sha:
        return "mismatch", {"remote_tag_object": sha, "remote_kind": kind}
    code, out, err = gh_api(f"repos/{remote}/git/tags/{sha}")
    if code != 0:
        blob = f"{out}\n{err}"
        if "404" in blob:
            return "blocked", {"detail": "tag object sha from the ref was not found"}
        return "blocked", {"detail": err.strip() or out.strip()}
    try:
        tag_obj = json.loads(out)
    except json.JSONDecodeError:
        return "blocked", {"detail": "remote tag object response was not JSON"}
    target = tag_obj.get("object") if isinstance(tag_obj, dict) else None
    peeled = str(target.get("sha") or "") if isinstance(target, dict) else ""
    return "present", {"remote_tag_object": sha, "remote_peeled": peeled}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-dir", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--tag-object", required=True)
    parser.add_argument("--peeled-commit", required=True)
    parser.add_argument("--remote", help="owner/name")
    parser.add_argument(
        "--require-remote",
        action="store_true",
        help="Treat a missing remote ref as a mismatch. Use after the push.",
    )
    args = parser.parse_args()
    if args.require_remote and not args.remote:
        return _emit({"status": "MISMATCH", "detail": "--require-remote needs --remote"}, 1)

    kind, obj, peeled = local_identity(args.repo_dir, args.tag)
    payload: dict[str, Any] = {
        "tag": args.tag,
        "local_kind": kind,
        "local_tag_object": obj,
        "local_peeled": peeled,
        "expected_tag_object": args.tag_object,
        "expected_peeled": args.peeled_commit,
    }
    local_ok = kind == "tag" and obj == args.tag_object and peeled == args.peeled_commit
    if not local_ok:
        payload["status"] = "MISMATCH"
        return _emit(payload, 1)

    if not args.remote:
        payload["status"] = "MATCH"
        return _emit(payload, 0)

    state, remote = remote_identity(args.remote, args.tag)
    payload.update(remote)
    if state == "blocked":
        payload["status"] = "TRANSPORT_BLOCKED"
        return _emit(payload, 3)
    if state == "absent":
        if args.require_remote:
            payload["status"] = "MISMATCH"
            payload["detail"] = "remote ref absent after the push"
            return _emit(payload, 1)
        payload["status"] = "REMOTE_ABSENT"
        return _emit(payload, 2)
    if state == "mismatch":
        payload["status"] = "MISMATCH"
        return _emit(payload, 1)
    remote_ok = (
        remote.get("remote_tag_object") == args.tag_object
        and remote.get("remote_peeled") == args.peeled_commit
    )
    payload["status"] = "MATCH" if remote_ok else "MISMATCH"
    return _emit(payload, 0 if remote_ok else 1)


if __name__ == "__main__":
    sys.exit(main())
