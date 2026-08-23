#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/validate_harvest_coverage.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Validate that every audited harvest decision is closed and evidence-linked."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

_ALLOWED = {"implemented", "rejected_boundary", "blocked_external"}


def _paths(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.repo_root.resolve()
    path = root / "docs" / "harvest_coverage.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    if not isinstance(raw, dict) or raw.get("schema") != "l9.memory.harvest-coverage/v1":
        failures.append("invalid or missing harvest coverage schema")
        entries: list[dict[str, Any]] = []
    else:
        entries = raw.get("entries") if isinstance(raw.get("entries"), list) else []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            failures.append("harvest entry must be a mapping")
            continue
        entry_id = str(entry.get("id") or "")
        if not entry_id or entry_id in seen:
            failures.append(f"missing or duplicate harvest id: {entry_id!r}")
        seen.add(entry_id)
        concept = str(entry.get("concept") or "").strip()
        if not concept:
            failures.append(f"{entry_id}: concept is required")
        status = str(entry.get("status") or "")
        if status not in _ALLOWED:
            failures.append(f"{entry_id}: invalid status {status!r}")
            continue
        adr_paths = _paths(entry.get("adr_paths"))
        if not adr_paths:
            failures.append(f"{entry_id}: at least one ADR is required")
        for relative in adr_paths:
            if not (root / relative).is_file():
                failures.append(f"{entry_id}: missing ADR {relative}")
        if status == "implemented":
            implementation_paths = _paths(entry.get("implementation_paths"))
            test_paths = _paths(entry.get("test_paths"))
            if not implementation_paths:
                failures.append(f"{entry_id}: implemented concept has no implementation paths")
            if not test_paths:
                failures.append(f"{entry_id}: implemented concept has no test paths")
            for label, paths in (
                ("implementation", implementation_paths),
                ("test", test_paths),
            ):
                for relative in paths:
                    if not (root / relative).is_file():
                        failures.append(f"{entry_id}: missing {label} path {relative}")
        elif status == "rejected_boundary":
            if not str(entry.get("rationale") or "").strip():
                failures.append(f"{entry_id}: rejected boundary lacks rationale")
        elif status == "blocked_external":
            if not str(entry.get("blocker") or "").strip():
                failures.append(f"{entry_id}: external blocker is not named")
    if len(entries) < 40:
        failures.append(f"harvest coverage is unexpectedly shallow: {len(entries)} entries")
    text = path.read_text(encoding="utf-8").lower()
    for forbidden in ("status: partial", "status: deferred", "status: unknown"):
        if forbidden in text:
            failures.append(f"unclosed harvest status present: {forbidden}")
    if failures:
        sys.stdout.write("\n".join(failures) + "\n")
        return 1
    counts = {
        status: sum(1 for entry in entries if entry.get("status") == status)
        for status in sorted(_ALLOWED)
    }
    sys.stdout.write(f"PASS: {len(entries)} harvest decisions closed {counts}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
