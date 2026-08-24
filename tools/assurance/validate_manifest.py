#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/validate_manifest.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Validate the release file manifest against the current repository tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.repo_root.resolve()
    manifest_path = root / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    entries = raw.get("files") if isinstance(raw, dict) else None
    if raw.get("schema") != "l9.release-manifest/v2" or not isinstance(entries, list):
        failures.append("invalid release manifest schema")
        entries = []
    seen: set[str] = set()
    for entry in entries:
        relative = str(entry.get("path") or "")
        if not relative or relative in seen:
            failures.append(f"missing or duplicate manifest path: {relative!r}")
            continue
        seen.add(relative)
        path = root / relative
        if not path.is_file():
            failures.append(f"missing file: {relative}")
            continue
        size = path.stat().st_size
        digest = _sha256(path)
        if size != entry.get("size_bytes"):
            failures.append(f"size mismatch: {relative}")
        if digest != entry.get("sha256"):
            failures.append(f"digest mismatch: {relative}")
        meta = entry.get("l9_meta")
        if not isinstance(meta, dict) or meta.get("path") != relative:
            failures.append(f"missing or invalid l9_meta: {relative}")
    if failures:
        sys.stdout.write("\n".join(failures) + "\n")
        return 1
    sys.stdout.write(
        f"PASS: {len(entries)} manifested files exist with matching size and SHA-256\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
