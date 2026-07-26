#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/check_recursive_alignment.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Deterministic checks for the active L9 recursive-alignment contract."""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys

sys.dont_write_bytecode = True
from dataclasses import dataclass
from pathlib import Path

from check_l9_meta import validate as validate_l9_meta
from check_layer_boundaries import scan as scan_layer_boundaries

_DEPRECATED_ENVELOPE = "Packet" + "Envelope"
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
ALLOWED_TOP_LEVEL = {
    ".github",
    ".gitignore",
    ".pre-commit-config.yaml",
    "AGENTS.md",
    "ALIGNMENT.md",
    "ARCHITECTURE.md",
    "CHANGE_SUMMARY.md",
    "CONTRIBUTING.md",
    "CONVERGENCE_REPORT.yaml",
    "DELTA_REPORT.md",
    "IMPROVEMENT_REPORT.md",
    "LICENSE",
    "MANIFEST.in",
    "MANIFEST.md",
    "MIGRATION.md",
    "QUICKSTART.md",
    "README.md",
    "requirements-ci.txt",
    "ROADMAP.md",
    "RUNBOOK.md",
    "SECURITY.md",
    "VALIDATION.md",
    "config",
    "docs",
    "hooks",
    "improvement_log.jsonl",
    "manifest.json",
    "pyproject.toml",
    "ruff.toml",
    "rules",
    "scripts",
    "skill",
    "src",
    "tests",
    "tools",
    "validation",
}
SNAKE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
FORBIDDEN_LOG_KEYS = {
    "content",
    "email",
    "phone",
    "prompt",
    "secret",
    "token",
    "credential",
    "api_key",
}


@dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    line: int
    evidence: str


def _text_files(root: Path) -> tuple[Path, ...]:
    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(
            part in EXCLUDED_PARTS or part.endswith(".egg-info")
            for part in relative.parts
        ):
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        result.append(path)
    return tuple(sorted(result))


def _tracked_paths(root: Path) -> frozenset[str]:
    """Return git-tracked paths (posix) so transient tooling artifacts such as
    ``.git``, editable-install ``*.egg-info`` and pytest-generated
    ``__pycache__`` are never mistaken for committed repository content."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    return frozenset(entry for entry in result.stdout.split("\0") if entry)


def _python_calls(path: Path) -> tuple[tuple[int, str], ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            calls.append((node.lineno, node.func.id))
        elif isinstance(node.func, ast.Attribute) and isinstance(
            node.func.value, ast.Name
        ):
            calls.append((node.lineno, f"{node.func.value.id}.{node.func.attr}"))
    return tuple(calls)


def scan(root: Path) -> tuple[Violation, ...]:
    violations: list[Violation] = []

    tracked = _tracked_paths(root)
    tracked_top_level = {entry.split("/", 1)[0] for entry in tracked}

    for item in root.iterdir():
        # Only tracked top-level entries can be a structural violation; untracked
        # tooling directories (.git, .venv, *.egg-info, __pycache__) are ignored.
        if item.name not in ALLOWED_TOP_LEVEL and item.name in tracked_top_level:
            violations.append(
                Violation("file_structure", item.name, 1, "forbidden top-level entry")
            )

    for relative_posix in tracked:
        if relative_posix.endswith(".pyc") or "__pycache__" in relative_posix.split(
            "/"
        ):
            violations.append(
                Violation(
                    "file_structure",
                    relative_posix,
                    1,
                    "generated cache committed",
                )
            )

    for failure in validate_l9_meta(root):
        violations.append(Violation("l9_meta", "manifest.json", 1, failure))

    for finding in scan_layer_boundaries(root):
        violations.append(
            Violation("authority_boundary", finding.path, finding.line, finding.reason)
        )

    for path in _text_files(root):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if _DEPRECATED_ENVELOPE in text:
            line = text[: text.index(_DEPRECATED_ENVELOPE)].count("\n") + 1
            violations.append(
                Violation(
                    "transport",
                    relative,
                    line,
                    "deprecated inter-node envelope reference",
                )
            )

    for path in (
        sorted((root / "src").rglob("*.py"))
        + sorted((root / "tools").rglob("*.py"))
        + sorted((root / "scripts").rglob("*.py"))
    ):
        relative = path.relative_to(root).as_posix()
        for line, call in _python_calls(path):
            if call in {"print", "eval", "exec", "compile"}:
                violations.append(
                    Violation(
                        "security_observability",
                        relative,
                        line,
                        f"forbidden call: {call}",
                    )
                )
            if call in {"yaml.load", "yaml.full_load", "yaml.unsafe_load"}:
                violations.append(
                    Violation(
                        "security_observability",
                        relative,
                        line,
                        f"unsafe YAML call: {call}",
                    )
                )
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg in {
                "alias",
                "validation_alias",
                "serialization_alias",
            }:
                violations.append(
                    Violation(
                        "schema_field",
                        relative,
                        node.lineno,
                        f"field alias is forbidden: {node.arg}",
                    )
                )
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in FORBIDDEN_LOG_KEYS
            ):
                parent = next(
                    (
                        candidate
                        for candidate in ast.walk(tree)
                        if isinstance(candidate, ast.Call)
                        and node in ast.walk(candidate)
                    ),
                    None,
                )
                if (
                    isinstance(parent, ast.Call)
                    and isinstance(parent.func, ast.Attribute)
                    and parent.func.attr
                    in {"debug", "info", "warning", "error", "exception", "critical"}
                ):
                    violations.append(
                        Violation(
                            "security_observability",
                            relative,
                            node.lineno,
                            f"forbidden log field: {node.value}",
                        )
                    )

    for path in [
        root / "src/l9_graphite_memory/integrations/constellation.py",
        root / "src/l9_graphite_memory/ports/constellation.py",
    ]:
        if not path.is_file():
            violations.append(
                Violation(
                    "transport",
                    path.relative_to(root).as_posix(),
                    1,
                    "missing constellation boundary",
                )
            )
            continue
        text = path.read_text(encoding="utf-8")
        for pattern, message in (
            (r"https?://", "peer URL forbidden at constellation boundary"),
            (r"\bdestination\s*:", "caller-selected destination forbidden"),
            (r"\bnode_registry\b", "private node registry forbidden"),
            (r"\bpeer_url\b", "peer URL field forbidden"),
        ):
            match = re.search(pattern, text)
            if match:
                violations.append(
                    Violation(
                        "gate_routing",
                        path.relative_to(root).as_posix(),
                        text[: match.start()].count("\n") + 1,
                        message,
                    )
                )

    guard = root / "src/l9_graphite_memory/graphiti_gate_lib.py"
    guard_text = guard.read_text(encoding="utf-8") if guard.is_file() else ""
    for forbidden in ("json.loads", "write_text", "os.replace", "Path("):
        if forbidden in guard_text:
            violations.append(
                Violation(
                    "gate_routing",
                    guard.relative_to(root).as_posix(),
                    1,
                    "compatibility Gate shim owns state",
                )
            )

    for path in sorted((root / "src/l9_graphite_memory").rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            candidate: str | None = None
            if isinstance(node, ast.arg):
                candidate = node.arg
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and isinstance(parents.get(node), ast.ClassDef)
            ):
                candidate = node.target.id
            if (
                candidate
                and not candidate.startswith("__")
                and not SNAKE_NAME.fullmatch(candidate)
            ):
                violations.append(
                    Violation(
                        "schema_field",
                        relative,
                        node.lineno,
                        f"non-snake schema field: {candidate}",
                    )
                )

    required_tests = {
        "tests/unit/test_constellation_bridge.py",
        "tests/unit/test_gate.py",
        "tests/regression/test_recursive_alignment.py",
    }
    for relative in required_tests:
        if not (root / relative).is_file():
            violations.append(
                Violation(
                    "testing_validation",
                    relative,
                    1,
                    "required alignment behavior test missing",
                )
            )

    return tuple(violations)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    violations = scan(parser.parse_args().repo_root.resolve())
    if violations:
        for item in violations:
            sys.stdout.write(f"{item.path}:{item.line}: {item.rule}: {item.evidence}\n")
        return 1
    sys.stdout.write(
        "PASS: recursive L9 alignment contract satisfied across all ten passes\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
