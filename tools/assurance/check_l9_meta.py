#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/check_l9_meta.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Validate inline and manifest-carried L9 metadata coverage."""

from __future__ import annotations

import argparse
import json
import sys

sys.dont_write_bytecode = True
from pathlib import Path

INLINE_EXTENSIONS = {".py", ".sh", ".md", ".mdc", ".yaml", ".yml", ".toml", ".in"}
INLINE_NAMES = {".gitignore"}
EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "validation",
    ".venv",
}


def _tracked_files(root: Path) -> tuple[Path, ...]:
    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(
            part in EXCLUDED_PARTS
            or part.endswith(".egg-info")
            or part == ".coverage"
            or part.startswith(".coverage.")
            or part == "coverage.xml"
            for part in relative.parts
        ):
            continue
        if relative.as_posix() == "manifest.json":
            continue
        result.append(path)
    return tuple(sorted(result))


def validate(root: Path) -> tuple[str, ...]:
    failures: list[str] = []
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest.get("files") if isinstance(manifest, dict) else None
    if manifest.get("schema") != "l9.release-manifest/v2" or not isinstance(
        entries, list
    ):
        failures.append("manifest must use l9.release-manifest/v2")
        entries = []
    manifest_by_path = {
        str(entry.get("path")): entry for entry in entries if isinstance(entry, dict)
    }
    for path in _tracked_files(root):
        relative = path.relative_to(root).as_posix()
        entry = manifest_by_path.get(relative)
        if entry is None:
            failures.append(f"missing manifest metadata carrier: {relative}")
        else:
            meta = entry.get("l9_meta")
            if (
                not isinstance(meta, dict)
                or meta.get("path") != relative
                or meta.get("repo") != "Quantum-L9/l9-graphiti-memory"
            ):
                failures.append(f"invalid manifest l9_meta: {relative}")
        # .github/governance/* are strict-JSON documents consumed by the
        # governed analysis pipeline (resolve-governance parses them with
        # json.loads, which rejects comments). They carry metadata through the
        # manifest only, never an inline header.
        inline_capable = (
            path.suffix in INLINE_EXTENSIONS or path.name in INLINE_NAMES
        ) and not relative.startswith(".github/governance/")
        if inline_capable:
            head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:50])
            if "L9_META" not in head:
                failures.append(f"missing inline L9_META: {relative}")
    return tuple(failures)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    failures = validate(parser.parse_args().repo_root.resolve())
    if failures:
        sys.stdout.write("\n".join(failures) + "\n")
        return 1
    sys.stdout.write(
        "PASS: all tracked files carry L9_META inline or through the cryptographic manifest\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
