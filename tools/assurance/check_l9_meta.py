#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/check_l9_meta.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-10-02

"""Validate inline and manifest-carried L9 metadata identity.

Read-only. For every tracked artifact this proves that the manifest carries a
structurally correct ``l9_meta`` entry and, for every inline-capable file,
that exactly one admissible inline block exists whose repo, path, layer and
owner equal the identity its real location implies. Presence of the marker is
not enough: a header copied from another location fails here, naming the file
and the mismatched field.
"""

from __future__ import annotations

import argparse
import json
import sys

sys.dont_write_bytecode = True
from pathlib import Path

import l9_meta


def _format(mismatches: tuple[tuple[str, str | None, str], ...]) -> str:
    return ", ".join(
        f"{field}={'<absent>' if actual is None else actual!r} expected {expected!r}"
        for field, actual, expected in mismatches
    )


def validate(root: Path) -> tuple[str, ...]:
    failures: list[str] = []
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest.get("files") if isinstance(manifest, dict) else None
    if manifest.get("schema") != "l9.release-manifest/v2" or not isinstance(entries, list):
        failures.append("manifest must use l9.release-manifest/v2")
        entries = []
    manifest_by_path = {
        str(entry.get("path")): entry for entry in entries if isinstance(entry, dict)
    }
    for path in l9_meta.repository_files(root):
        relative = path.relative_to(root)
        posix = relative.as_posix()
        if posix in l9_meta.MANIFEST_SELF:
            continue
        entry = manifest_by_path.get(posix)
        if entry is None:
            failures.append(f"missing manifest metadata carrier: {posix}")
        else:
            meta = entry.get("l9_meta")
            if not isinstance(meta, dict):
                failures.append(f"invalid manifest l9_meta: {posix}: not an object")
            else:
                mismatches = l9_meta.compare_manifest_meta(meta, relative)
                if mismatches:
                    failures.append(f"invalid manifest l9_meta: {posix}: {_format(mismatches)}")
        if not l9_meta.is_inline_capable(relative):
            continue
        text = path.read_text(encoding="utf-8")
        try:
            inline = l9_meta.parse_inline(text, relative)
        except l9_meta.MetaError as error:
            failures.append(f"malformed inline L9_META: {posix}: {error}")
            continue
        if inline is None:
            failures.append(f"missing inline L9_META: {posix}")
            continue
        mismatches = l9_meta.compare(inline, relative)
        if mismatches:
            failures.append(f"stale inline L9_META: {posix}: {_format(mismatches)}")
    return tuple(failures)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    failures = validate(parser.parse_args().repo_root.resolve())
    if failures:
        sys.stdout.write("\n".join(failures) + "\n")
        return 1
    sys.stdout.write(
        "PASS: all tracked files carry L9_META inline or through the cryptographic manifest, "
        "with structural identity matching their location\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
