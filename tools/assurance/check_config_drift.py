#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/check_config_drift.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Check that namespace and security defaults remain centralized."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

_ALLOWED = {
    "src/l9_graphite_memory/config/models.py",
    "src/l9_graphite_memory/config/loader.py",
    "src/l9_graphite_memory/group_resolver.py",
    "src/l9_graphite_memory/resources/group_registry.yaml",
}
_TRACKED_NAMES = {
    "workspace_namespace",
    "http_auth_required",
    "projection_backend",
    "outbox_max_attempts",
    "gate_ttl_minutes",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    violations: list[str] = []
    for path in sorted((root / "src" / "l9_graphite_memory").rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative in _ALLOWED:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            violations.append(f"{relative}: parse error: {exc}")
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.keyword)
                and node.arg in _TRACKED_NAMES
                and isinstance(node.value, ast.Constant)
            ):
                violations.append(
                    f"{relative}:{node.lineno}: hardcoded {node.arg} outside canonical config"
                )
    if violations:
        sys.stdout.write("\n".join(violations) + "\n")
        return 1
    sys.stdout.write(
        "PASS: canonical configuration defaults have no duplicate assignments\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
