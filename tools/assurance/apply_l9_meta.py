#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/apply_l9_meta.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Apply canonical inline L9 metadata to comment-safe tracked files."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPOSITORY = "Quantum-L9/l9-graphiti-memory"
VERSION = "2.2.0"
COMMENT_EXTENSIONS = {
    ".py": "#",
    ".sh": "#",
    ".yaml": "#",
    ".yml": "#",
    ".toml": "#",
    ".gitignore": "#",
    ".in": "#",
}
MARKDOWN_EXTENSIONS = {".md", ".mdc"}
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
EXCLUDED_FILES = {"manifest.json"}


def _layer(path: Path) -> str:
    parts = path.parts
    if parts[0] == "src" and "contracts" in parts:
        return "contract"
    if parts[0] == "src" and "ports" in parts:
        return "port"
    if parts[0] == "src" and "integrations" in parts:
        return "integration"
    if parts[0] == "src" and "adapters" in parts:
        return "adapter"
    if parts[0] == "src" and "services" in parts:
        return "service"
    if parts[0] == "src":
        return "package"
    if parts[0] == "tests":
        return "test"
    if parts[0] == "tools":
        return "assurance"
    if parts[0] == "scripts":
        return "operations"
    if parts[0] == "hooks":
        return "hook"
    if parts[0] == ".github":
        return "ci"
    if parts[0] == "docs" and len(parts) > 1 and parts[1] == "adr":
        return "adr"
    if parts[0] == "docs":
        return "documentation"
    if parts[0] in {"config", "rules"}:
        return "configuration"
    if parts[0] == "skill":
        return "skill"
    return "repository"


def _metadata_lines(relative: Path, prefix: str) -> list[str]:
    updated = date(2026, 7, 22).isoformat()
    values = (
        ("l9_schema", "1"),
        ("repo", REPOSITORY),
        ("path", relative.as_posix()),
        ("layer", _layer(relative)),
        ("owner", "memory-control-plane"),
        ("status", "active"),
        ("version", VERSION),
        ("updated", updated),
    )
    return [
        f"{prefix} L9_META",
        *(f"{prefix}   {key}: {value}" for key, value in values),
    ]


def _insert_markdown(text: str, relative: Path) -> str:
    if "L9_META" in "\n".join(text.splitlines()[:40]):
        return text
    block = [
        "<!-- L9_META",
        "l9_schema: 1",
        f"repo: {REPOSITORY}",
        f"path: {relative.as_posix()}",
        f"layer: {_layer(relative)}",
        "owner: memory-control-plane",
        "status: active",
        f"version: {VERSION}",
        "updated: 2026-07-22",
        "/L9_META -->",
        "",
    ]
    lines = text.splitlines()
    if (
        relative.parts[:2] == ("docs", "adr")
        and lines
        and lines[0].startswith("# ADR-")
    ):
        lines[1:1] = ["", *block]
        return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    if lines and lines[0].strip() == "---":
        try:
            closing = next(
                index
                for index, line in enumerate(lines[1:], start=1)
                if line.strip() == "---"
            )
        except StopIteration:
            closing = -1
        if closing >= 0:
            lines[closing + 1 : closing + 1] = ["", *block]
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return "\n".join([*block, *lines]) + ("\n" if text.endswith("\n") else "")


def _insert_comments(text: str, relative: Path, prefix: str) -> str:
    if "L9_META" in "\n".join(text.splitlines()[:40]):
        return text
    lines = text.splitlines()
    block = _metadata_lines(relative, prefix)
    insertion = 1 if lines and lines[0].startswith("#!") else 0
    lines[insertion:insertion] = [*block, ""]
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def tracked_comment_safe_files(root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if (
            any(part in EXCLUDED_PARTS for part in relative.parts)
            or relative.as_posix() in EXCLUDED_FILES
        ):
            continue
        if (
            path.suffix in MARKDOWN_EXTENSIONS
            or path.suffix in COMMENT_EXTENSIONS
            or path.name == ".gitignore"
        ):
            paths.append(path)
    return tuple(sorted(paths))


def apply(root: Path, *, check: bool = False) -> int:
    changed: list[str] = []
    for path in tracked_comment_safe_files(root):
        relative = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        if path.suffix in MARKDOWN_EXTENSIONS:
            updated = _insert_markdown(text, relative)
        else:
            prefix = COMMENT_EXTENSIONS.get(path.suffix, "#")
            updated = _insert_comments(text, relative, prefix)
        if updated != text:
            changed.append(relative.as_posix())
            if not check:
                path.write_text(updated, encoding="utf-8")
    if check:
        if changed:
            sys.stdout.write(
                "missing inline L9_META (run tools/assurance/apply_l9_meta.py):\n"
                + "\n".join(f"  {name}" for name in changed)
                + "\n"
            )
            return 1
        sys.stdout.write("PASS: every comment-safe file carries inline L9_META\n")
        return 0
    sys.stdout.write(f"Applied L9_META to {len(changed)} files\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report files missing headers and exit non-zero without writing",
    )
    args = parser.parse_args()
    return apply(args.repo_root.resolve(), check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
