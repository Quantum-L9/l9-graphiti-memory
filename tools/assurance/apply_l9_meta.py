#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/apply_l9_meta.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-10-02

"""Apply canonical inline L9 metadata to comment-safe tracked files.

This is a PREPARATION tool. It may insert a missing block and reconcile the
structural identity (repo, path, layer, owner) of a stale one. With
``--check`` it only reports what it would change and writes nothing; release
validation runs that mode, never the mutating one.

Derivation, parsing and rendering belong to ``l9_meta``; this module owns
only where a new block is placed in a file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import l9_meta

REPOSITORY = l9_meta.REPOSITORY
VERSION = "2.5.0"
# Artifact fields stamped on a block this tool inserts. An existing block keeps
# its own artifact fields: reconciliation never rewrites them from location.
INSERTED_STATUS = "active"
INSERTED_UPDATED = "2026-07-22"


def _new_block(relative: Path, style: str, prefix: str) -> list[str]:
    fields = l9_meta.canonical_fields(
        relative, status=INSERTED_STATUS, version=VERSION, updated=INSERTED_UPDATED
    )
    return l9_meta.render_block(fields, style=style, prefix=prefix)


def _insert_markdown(text: str, relative: Path) -> str:
    block = [*_new_block(relative, "markdown", ""), ""]
    lines = text.splitlines()
    if relative.parts[:2] == ("docs", "adr") and lines and lines[0].startswith("# ADR-"):
        lines[1:1] = ["", *block]
        return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    if lines and lines[0].strip() == "---":
        try:
            closing = next(
                index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
            )
        except StopIteration:
            closing = -1
        if closing >= 0:
            lines[closing + 1 : closing + 1] = ["", *block]
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return "\n".join([*block, *lines]) + ("\n" if text.endswith("\n") else "")


def _insert_comments(text: str, relative: Path, prefix: str) -> str:
    lines = text.splitlines()
    block = _new_block(relative, "comment", prefix)
    insertion = 1 if lines and lines[0].startswith("#!") else 0
    lines[insertion:insertion] = [*block, ""]
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def tracked_comment_safe_files(root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in l9_meta.repository_files(root)
        if l9_meta.is_inline_capable(path.relative_to(root))
    )


def plan(root: Path) -> tuple[list[tuple[Path, str, str]], list[str]]:
    """Decide, without writing, what each inline-capable file needs.

    Returns ``(changes, failures)``: ``changes`` holds ``(path, action,
    new_text)`` for files that are missing or stale, ``failures`` names files
    whose block is malformed or ambiguous and must be repaired by hand.
    """

    changes: list[tuple[Path, str, str]] = []
    failures: list[str] = []
    for path in tracked_comment_safe_files(root):
        relative = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        try:
            meta = l9_meta.parse_inline(text, relative)
        except l9_meta.MetaError as error:
            failures.append(f"malformed inline L9_META: {relative.as_posix()}: {error}")
            continue
        if meta is None:
            if l9_meta.is_markdown(relative):
                updated = _insert_markdown(text, relative)
            else:
                prefix = l9_meta.comment_prefix(relative) or "#"
                updated = _insert_comments(text, relative, prefix)
            changes.append((path, "insert", updated))
            continue
        mismatches = l9_meta.compare(meta, relative)
        if mismatches:
            changes.append((path, "reconcile", l9_meta.reconcile_text(text, relative)))
    return changes, failures


def apply(root: Path, *, check: bool) -> int:
    changes, failures = plan(root)
    for path, action, text in changes:
        relative = path.relative_to(root).as_posix()
        if check:
            sys.stdout.write(f"{action} needed: {relative}\n")
        else:
            path.write_text(text, encoding="utf-8")
            sys.stdout.write(f"{action}: {relative}\n")
    for failure in failures:
        sys.stdout.write(failure + "\n")
    if check:
        if changes or failures:
            sys.stdout.write(
                f"FAIL: {len(changes)} files need metadata preparation, "
                f"{len(failures)} malformed; nothing written\n"
            )
            return 1
        sys.stdout.write("PASS: inline L9_META is current on every inline-capable file\n")
        return 0
    sys.stdout.write(f"Applied L9_META to {len(changes)} files\n")
    if failures:
        sys.stdout.write(f"FAIL: {len(failures)} malformed blocks were not touched\n")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--check",
        action="store_true",
        help="report missing, stale or malformed metadata and exit non-zero; write nothing",
    )
    args = parser.parse_args()
    return apply(args.repo_root.resolve(), check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
