#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/audit_package_wiring.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Prove that production modules are imported, entrypoints, or explicit compatibility surfaces."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path


def module_name(root: Path, path: Path) -> str:
    relative = path.relative_to(root / "src").with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imported_modules(root: Path, path: Path) -> set[str]:
    current = module_name(root, path)
    package = current if path.name == "__init__.py" else current.rpartition(".")[0]
    package_parts = package.split(".") if package else []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            keep = max(0, len(package_parts) - (node.level - 1))
            base = package_parts[:keep]
            if node.module:
                base.extend(node.module.split("."))
            resolved = ".".join(base)
        else:
            resolved = node.module or ""
        if resolved:
            result.add(resolved)
            for alias in node.names:
                result.add(f"{resolved}.{alias.name}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    paths = sorted((root / "src" / "l9_graphite_memory").rglob("*.py"))
    modules = {module_name(root, path): path for path in paths}
    consumed: set[str] = set()
    for path in paths:
        for imported in imported_modules(root, path):
            if imported in modules:
                consumed.add(imported)
    entrypoints = {
        "l9_graphite_memory.cli",
        "l9_graphite_memory.server",
        "l9_graphite_memory.services.outbox_worker",
        "l9_graphite_memory.__main__",
        "l9_graphite_memory.graphiti_gate_lib",
        "l9_graphite_memory.graphiti_memory_client",
    }
    compatibility = {
        "l9_graphite_memory.episode_contract": "v0.2 import compatibility",
        "l9_graphite_memory.prune": "v0.2 programmatic prune compatibility",
        "l9_graphite_memory.projections": "ADR-063 projection control-plane surface",
        "l9_graphite_memory.active": (
            "ADR-067 public SDK surface for external runtimes; not consumed"
            " by this repository's own entrypoints"
        ),
        "l9_graphite_memory.active.inmemory": (
            "ADR-067 default ActiveStore/AwarenessBus adapter; selected by"
            " external consumers, not imported internally"
        ),
        "l9_graphite_memory.active.null_adapters": (
            "ADR-067 no-op ActiveStore/AwarenessBus adapter; selected by"
            " external consumers, not imported internally"
        ),
        "l9_graphite_memory.active.redis_adapters": (
            "ADR-065/ADR-068 Redis-backed ActiveStore/AwarenessBus adapter;"
            " selected by external consumers, not imported internally"
        ),
    }
    foundational = {
        "l9_graphite_memory",
        "l9_graphite_memory.version",
        "l9_graphite_memory.errors",
    }
    orphans = sorted(
        set(modules) - consumed - entrypoints - foundational - set(compatibility)
    )
    payload = {
        "modules": len(modules),
        "consumed": len(consumed),
        "entrypoints": sorted(entrypoints),
        "compatibility": compatibility,
        "orphans": orphans,
    }
    if args.json:
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        sys.stdout.write(
            f"modules={len(modules)} consumed={len(consumed)} orphans={len(orphans)}\n"
        )
        if orphans:
            sys.stdout.write("\n".join(orphans) + "\n")
    return 1 if orphans else 0


if __name__ == "__main__":
    raise SystemExit(main())
