#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/check_memory_write_bypass.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Fail CI when production code bypasses the canonical MemoryService write path."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_ALLOWED_SQL_FILES = {
    "src/l9_graphite_memory/adapters/sqlite_store.py",
    "src/l9_graphite_memory/adapters/postgres_store.py",
}
_ALLOWED_COMMIT_CALLERS = {
    "src/l9_graphite_memory/services/memory_service.py",
}
# Lifecycle transitions append a status event and move a record between states.
# They never rewrite content, and the store enforces the expected previous
# state, but they still mutate canonical state, so the set of modules allowed
# to perform one is explicit rather than incidental.
_ALLOWED_TRANSITION_CALLERS = {
    "src/l9_graphite_memory/services/memory_service.py",
    "src/l9_graphite_memory/maintenance/service.py",
    # Store adapters implement the operation; they are not callers of it.
    "src/l9_graphite_memory/adapters/in_memory_store.py",
    "src/l9_graphite_memory/adapters/sqlite_store.py",
    "src/l9_graphite_memory/adapters/postgres_store.py",
}
# A canonical write becomes durable during the operation or fails. Only the
# one-way drain for the retired deferred-ingestion release may still read a
# serialized MemoryWriteRequest off disk, and it can never write one back.
_ALLOWED_DEFERRED_INGESTION_READERS = {
    "src/l9_graphite_memory/migration/legacy_write_queue.py",
}
_REQUEST_SERIALIZERS = {"model_dump", "model_dump_json"}
# Opening a SQLite file directly is a write bypass everywhere except when
# inspecting a store this process is NOT configured to use. The backend
# transition guard reads a prior ledger read-only to decide whether startup
# should fail closed (ADR-077). It is exempt from the connect rule only; the
# mutation-marker rule below still applies to it in full, so it cannot acquire
# a write path without failing this check.
_ALLOWED_SQLITE_READERS = {
    "src/l9_graphite_memory/migration/backend_transition.py",
}
_MUTATION_MARKERS = (
    "insert into memory_records",
    "update memory_records",
    "delete from memory_records",
    "insert into memory_status_events",
    "insert into operation_receipts",
    "insert into outbox_events",
)


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    excerpt: str


def _request_local_names(tree: ast.AST) -> set[str]:
    """Locals annotated as, or assigned from, a MemoryWriteRequest."""

    names: set[str] = set()

    def _is_request_annotation(annotation: ast.expr | None) -> bool:
        if isinstance(annotation, ast.Name):
            return annotation.id == "MemoryWriteRequest"
        if isinstance(annotation, ast.Attribute):
            return annotation.attr == "MemoryWriteRequest"
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            return "MemoryWriteRequest" in annotation.value
        return False

    def _is_request_construction(value: ast.expr | None) -> bool:
        if not isinstance(value, ast.Call):
            return False
        func = value.func
        if isinstance(func, ast.Name):
            return func.id == "MemoryWriteRequest"
        if isinstance(func, ast.Attribute):
            return func.attr in {"MemoryWriteRequest", "request"} or (
                isinstance(func.value, ast.Name)
                and func.value.id == "MemoryWriteRequest"
            )
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and _is_request_annotation(node.annotation):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
        elif isinstance(node, ast.Assign) and _is_request_construction(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.arg) and _is_request_annotation(node.annotation):
            names.add(node.arg)
    return names


def scan_file(path: Path, root: Path) -> list[Violation]:
    relative = path.relative_to(root).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError) as exc:
        return [Violation(relative, 1, "parse-error", str(exc))]
    violations: list[Violation] = []
    lines = source.splitlines()
    request_names = _request_local_names(tree)
    for node in ast.walk(tree):
        if (
            relative not in _ALLOWED_DEFERRED_INGESTION_READERS
            and isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _REQUEST_SERIALIZERS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in request_names
        ):
            violations.append(
                Violation(
                    relative,
                    node.lineno,
                    "deferred-canonical-ingestion",
                    lines[node.lineno - 1].strip()[:300],
                )
            )
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lowered = node.value.casefold()
            if (
                any(marker in lowered for marker in _MUTATION_MARKERS)
                and relative not in _ALLOWED_SQL_FILES
            ):
                violations.append(
                    Violation(
                        relative,
                        node.lineno,
                        "direct-memory-sql",
                        lines[node.lineno - 1].strip()[:300],
                    )
                )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                node.func.attr == "transition_state"
                and relative not in _ALLOWED_TRANSITION_CALLERS
            ):
                violations.append(
                    Violation(
                        relative,
                        node.lineno,
                        "direct-lifecycle-transition",
                        lines[node.lineno - 1].strip()[:300],
                    )
                )
            if (
                node.func.attr == "commit_write"
                and relative not in _ALLOWED_COMMIT_CALLERS
            ):
                violations.append(
                    Violation(
                        relative,
                        node.lineno,
                        "direct-store-commit",
                        lines[node.lineno - 1].strip()[:300],
                    )
                )
            if (
                node.func.attr == "connect"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "sqlite3"
                and relative not in _ALLOWED_SQL_FILES
                and relative not in _ALLOWED_SQLITE_READERS
            ):
                violations.append(
                    Violation(
                        relative,
                        node.lineno,
                        "direct-sqlite-connect",
                        lines[node.lineno - 1].strip()[:300],
                    )
                )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    violations: list[Violation] = []
    for path in sorted((root / "src" / "l9_graphite_memory").rglob("*.py")):
        violations.extend(scan_file(path, root))
    if args.json:
        sys.stdout.write(
            json.dumps({"violations": [asdict(item) for item in violations]}, indent=2)
            + "\n"
        )
    elif violations:
        for item in violations:
            sys.stdout.write(f"{item.path}:{item.line}: {item.rule}: {item.excerpt}\n")
    else:
        sys.stdout.write(
            "PASS: no canonical memory write bypasses or deferred-ingestion paths detected\n"
        )
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
