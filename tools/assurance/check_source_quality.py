#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/check_source_quality.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Deterministic source-quality checks used when third-party linters are unavailable."""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str


_ALLOWED_PRINT_MODULES = {
    "src/l9_graphite_memory/cli.py",
    "src/l9_graphite_memory/server.py",
    "src/l9_graphite_memory/services/outbox_worker.py",
    "src/l9_graphite_memory/graphiti_gate_lib.py",
    "tools/assurance/check_source_quality.py",
}
_ALLOWED_UNANNOTATED = {"self", "cls"}


def _relative(root: Path, path: Path) -> str:
    return str(path.relative_to(root))


def _function_findings(
    relative: str, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> list[Finding]:
    findings: list[Finding] = []
    arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    if node.args.vararg is not None:
        arguments.append(node.args.vararg)
    if node.args.kwarg is not None:
        arguments.append(node.args.kwarg)
    for argument in arguments:
        if argument.arg not in _ALLOWED_UNANNOTATED and argument.annotation is None:
            findings.append(
                Finding(
                    relative,
                    node.lineno,
                    "ANN001",
                    f"argument {argument.arg!r} is not annotated",
                )
            )
    if node.returns is None:
        findings.append(
            Finding(
                relative,
                node.lineno,
                "ANN201",
                f"function {node.name!r} has no return annotation",
            )
        )
    defaults = [*node.args.defaults, *node.args.kw_defaults]
    for default in defaults:
        if isinstance(default, (ast.List, ast.Dict, ast.Set)):
            findings.append(
                Finding(relative, node.lineno, "B006", "mutable default argument")
            )
    return findings


def inspect_file(root: Path, path: Path) -> list[Finding]:
    relative = _relative(root, path)
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=relative)
    except SyntaxError as exc:
        return [Finding(relative, exc.lineno or 1, "E999", str(exc))]
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            findings.extend(_function_findings(relative, node))
        elif isinstance(node, ast.ImportFrom) and any(
            alias.name == "*" for alias in node.names
        ):
            findings.append(Finding(relative, node.lineno, "F403", "wildcard import"))
        elif isinstance(node, ast.ExceptHandler) and node.type is None:
            findings.append(Finding(relative, node.lineno, "E722", "bare except"))
        elif isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "print"
                and relative not in _ALLOWED_PRINT_MODULES
            ):
                findings.append(
                    Finding(
                        relative,
                        node.lineno,
                        "T201",
                        "print used outside CLI/server/assurance",
                    )
                )
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr
                in {
                    "run",
                    "Popen",
                    "call",
                    "check_call",
                    "check_output",
                }
                and any(
                    keyword.arg == "shell"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in node.keywords
                )
            ):
                findings.append(
                    Finding(relative, node.lineno, "S602", "subprocess shell=True")
                )
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "now"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "datetime"
                and not node.args
                and not any(keyword.arg == "tz" for keyword in node.keywords)
            ):
                findings.append(
                    Finding(
                        relative,
                        node.lineno,
                        "DTZ005",
                        "datetime.now() without timezone",
                    )
                )
    for line_number, line in enumerate(text.splitlines(), start=1):
        upper = line.upper()
        if ("TODO" in upper or "FIXME" in upper) and not relative.startswith(
            "tools/assurance/"
        ):
            findings.append(
                Finding(relative, line_number, "TD001", "TODO/FIXME in approved source")
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    paths = sorted((root / "src").rglob("*.py"))
    findings = [finding for path in paths for finding in inspect_file(root, path)]
    if findings:
        for finding in findings:
            sys.stdout.write(
                f"{finding.path}:{finding.line}: {finding.rule} {finding.message}\n"
            )
        return 1
    sys.stdout.write(
        f"PASS: {len(paths)} production Python files meet deterministic quality rules\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
