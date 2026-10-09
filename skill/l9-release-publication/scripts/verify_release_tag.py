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
import re
import subprocess
import sys
from typing import Any

_TAG = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_REMOTE = re.compile(r"\A[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_SHA = re.compile(r"\A[0-9a-fA-F]{40}\Z")
_ORIGIN = re.compile(
    r"\A(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?\Z"
)


def _run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def _accepted(pattern: re.Pattern[str], value: str | None) -> str:
    match = pattern.fullmatch(value or "")
    return "" if match is None else match.group(0)


def _emit(payload: dict[str, Any], code: int) -> int:
    print(json.dumps(payload, sort_keys=True))
    return code


def local_identity(repo: str, tag: str) -> tuple[str, str, str]:
    kind = _run(["git", "cat-file", "-t", "--", tag], cwd=repo)
    obj = _run(["git", "rev-parse", "--verify", "--end-of-options", tag], cwd=repo)
    peeled = _run(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{tag}^{{}}"],
        cwd=repo,
    )
    return (
        kind.stdout.strip() if kind.returncode == 0 else "",
        obj.stdout.strip() if obj.returncode == 0 else "",
        peeled.stdout.strip() if peeled.returncode == 0 else "",
    )


def gh_api(path: str) -> tuple[int, str, str]:
    result = _run(["gh", "api", path])
    return result.returncode, result.stdout, result.stderr


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _transport(code: int, out: str, err: str, detail: str) -> tuple[str, dict[str, str]] | None:
    if code == 0:
        return None
    if "404" in f"{out}\n{err}":
        return "blocked", {"detail": detail}
    return "blocked", {"detail": err.strip() or out.strip()}


def _annotated_sha(owner: str, name: str, tag: str) -> tuple[str, dict[str, str], str]:
    code, out, err = gh_api(f"repos/{owner}/{name}/git/ref/tags/{tag}")
    if code != 0 and "404" in f"{out}\n{err}":
        return "absent", {}, ""
    failed = _transport(code, out, err, "tag ref request failed")
    if failed is not None:
        return failed[0], failed[1], ""
    ref = _json_object(out)
    obj = ref.get("object") if isinstance(ref, dict) else None
    if not isinstance(obj, dict):
        return "blocked", {"detail": "remote ref has no object"}, ""
    sha = _accepted(_SHA, str(obj.get("sha") or ""))
    if str(obj.get("type") or "") != "tag" or not sha:
        return (
            "mismatch",
            {
                "remote_tag_object": str(obj.get("sha") or ""),
                "remote_kind": str(obj.get("type") or ""),
            },
            "",
        )
    return "tag", {}, sha


def _peeled_commit(owner: str, name: str, sha: str) -> tuple[str, dict[str, str]]:
    code, out, err = gh_api(f"repos/{owner}/{name}/git/tags/{sha}")
    failed = _transport(code, out, err, "tag object sha from the ref was not found")
    if failed is not None and "404" in f"{out}\n{err}":
        return failed
    if failed is not None:
        return failed
    tag_obj = _json_object(out)
    target = tag_obj.get("object") if isinstance(tag_obj, dict) else None
    if not isinstance(target, dict):
        return "blocked", {"detail": "remote tag object response was not JSON"}
    return "present", {"remote_tag_object": sha, "remote_peeled": str(target.get("sha") or "")}


def remote_identity(remote: str, tag: str) -> tuple[str, dict[str, str]]:
    owner, _, name = remote.partition("/")
    state, payload, sha = _annotated_sha(owner, name, tag)
    if state != "tag":
        return state, payload
    return _peeled_commit(owner, name, sha)


def origin_repository(repo: str) -> str:
    result = _run(["git", "remote", "get-url", "origin"], cwd=repo)
    if result.returncode != 0:
        return ""
    match = _ORIGIN.fullmatch(result.stdout.strip())
    if match is None:
        return ""
    return f"{match.group(1)}/{match.group(2)}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-dir", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--tag-object", required=True)
    parser.add_argument("--peeled-commit", required=True)
    parser.add_argument("--remote", help="owner/name")
    parser.add_argument(
        "--bind-origin",
        action="store_true",
        help="Require git origin to be the same owner/name as --remote before a push.",
    )
    parser.add_argument(
        "--require-remote",
        action="store_true",
        help="Treat a missing remote ref as a mismatch. Use after the push.",
    )
    args = parser.parse_args()
    if args.require_remote and not args.remote:
        return _emit({"status": "MISMATCH", "detail": "--require-remote needs --remote"}, 1)
    if args.bind_origin and not args.remote:
        return _emit({"status": "MISMATCH", "detail": "--bind-origin needs --remote"}, 1)
    tag = _accepted(_TAG, args.tag)
    tag_object = _accepted(_SHA, args.tag_object)
    peeled_commit = _accepted(_SHA, args.peeled_commit)
    remote = _accepted(_REMOTE, args.remote) if args.remote else ""
    if not tag or not tag_object or not peeled_commit or (args.remote and not remote):
        return _emit(
            {
                "status": "MISMATCH",
                "detail": "tag, object, peel, or remote is not an allowlisted token",
            },
            1,
        )
    args.tag = tag
    args.tag_object = tag_object
    args.peeled_commit = peeled_commit
    if args.remote:
        args.remote = remote

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

    if args.bind_origin:
        bound = origin_repository(args.repo_dir)
        payload["origin"] = bound
        if bound != args.remote:
            payload["status"] = "MISMATCH"
            payload["detail"] = "origin is not the verified owner/name"
            return _emit(payload, 1)

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
