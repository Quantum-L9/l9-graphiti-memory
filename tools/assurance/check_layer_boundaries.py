#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/check_layer_boundaries.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Enforce dependency direction between memory core, adapters, and surfaces."""

from __future__ import annotations

import argparse
import ast
import sys

sys.dont_write_bytecode = True
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    imported: str
    reason: str


CORE_PREFIXES = (
    "l9_graphite_memory.contracts",
    "l9_graphite_memory.admission",
    "l9_graphite_memory.curation",
    "l9_graphite_memory.extraction",
    "l9_graphite_memory.lineage",
    "l9_graphite_memory.ports",
    "l9_graphite_memory.retrieval",
    "l9_graphite_memory.schema",
    "l9_graphite_memory.services.memory_service",
)
FORBIDDEN_CORE_IMPORTS = (
    "l9_graphite_memory.cli",
    "l9_graphite_memory.server",
    "l9_graphite_memory.transport",
    "l9_graphite_memory.zep_transport",
    "l9_graphite_memory.secrets",
    "l9_graphite_memory.authz.authenticator",
    "l9_graphite_memory.integrations",
)


def _module_for(root: Path, path: Path) -> str:
    relative = path.relative_to(root / "src").with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path) -> tuple[tuple[int, str], ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append((node.lineno, node.module))
    return tuple(result)


def scan(root: Path) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    package = root / "src" / "l9_graphite_memory"
    for path in sorted(package.rglob("*.py")):
        module = _module_for(root, path)
        if not module.startswith(CORE_PREFIXES):
            continue
        for line, imported in _imports(path):
            if imported.startswith(FORBIDDEN_CORE_IMPORTS):
                findings.append(
                    Finding(
                        path=path.relative_to(root).as_posix(),
                        line=line,
                        imported=imported,
                        reason="core memory law must not depend on service, transport, secret, or integration surfaces",
                    )
                )
    return tuple(findings)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    findings = scan(parser.parse_args().repo_root.resolve())
    if findings:
        for finding in findings:
            sys.stdout.write(
                f"{finding.path}:{finding.line}: {finding.imported}: {finding.reason}\n"
            )
        return 1
    sys.stdout.write(
        "PASS: core, adapter, service, and integration dependency directions are aligned\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
