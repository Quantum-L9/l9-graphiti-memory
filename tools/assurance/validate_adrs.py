#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/validate_adrs.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-27

"""Validate the complete ADR pack structure and index coverage."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REQUIRED = (
    "## Status",
    "## Context",
    "## Decision",
    "## Alternatives Considered",
    "## Rejected Alternatives",
    "## Invariants",
    "## Consequences",
    "## Security Impact",
    "## Migration Impact",
    "## Validation Requirements",
    "## Rollback Conditions",
    "## Supersedes / Superseded By",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    adr_dir = args.repo_root / "docs" / "adr"
    index = (adr_dir / "README.md").read_text(encoding="utf-8")
    files = sorted(adr_dir.glob("ADR-*.md"))
    failures: list[str] = []
    seen: set[int] = set()
    for path in files:
        match = re.match(r"ADR-(\d{3})-", path.name)
        if not match:
            failures.append(f"invalid ADR filename: {path.name}")
            continue
        number = int(match.group(1))
        if number in seen:
            failures.append(f"duplicate ADR number: {number:03d}")
        seen.add(number)
        text = path.read_text(encoding="utf-8")
        expected_title = f"# ADR-{number:03d}:"
        if not text.startswith(expected_title):
            failures.append(f"{path.name}: title must start at column zero with {expected_title}")
        for heading in REQUIRED:
            if not re.search(rf"(?m)^{re.escape(heading)}$", text):
                failures.append(f"{path.name}: missing renderable heading {heading}")
        if re.search(r"(?m)^ {4,}#", text):
            failures.append(f"{path.name}: indented Markdown heading renders as code")
        if path.name not in index:
            failures.append(f"{path.name}: missing from ADR index")
    expected = set(range(1, 79))
    if seen != expected:
        failures.append(
            f"ADR number set mismatch: missing={sorted(expected - seen)} extra={sorted(seen - expected)}"
        )
    if failures:
        sys.stdout.write("\n".join(failures) + "\n")
        return 1
    sys.stdout.write(f"PASS: {len(files)} ADRs complete and indexed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
