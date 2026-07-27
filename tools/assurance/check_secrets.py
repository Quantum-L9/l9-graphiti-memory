#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/check_secrets.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-27

"""Fail when committed production files contain high-confidence credential material."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

SCAN_ROOTS = (
    ".github",
    "config",
    "docs",
    "hooks",
    "scripts",
    "skill",
    "src",
    "tools",
)
TEXT_SUFFIXES = {".json", ".md", ".py", ".sh", ".toml", ".yaml", ".yml"}
SKIP_PARTS = {"__pycache__", ".git", ".pytest_cache", "validation", "dist", "build"}
SKIP_FILES = {"tools/assurance/check_secrets.py"}
PLACEHOLDER_FRAGMENTS = (
    "<runtime-secret-token>",
    "<secret>",
    "${",
    "...",
    "***",
    "changeme",
    "example",
    "placeholder",
    "redacted",
    "runtime-secret",
    "never-persist",
    "test-",
    "your_",
    "your-",
)

PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")
CREDENTIAL_URL = re.compile(
    r"(?i)\b(?:postgres(?:ql)?|mysql|redis|mongodb(?:\+srv)?)://[^\s/:]+:[^\s/@]+@"
)
LIVE_TOKEN = re.compile(
    r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[opsu]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|xox[baprs]-[A-Za-z0-9-]{20,})\b"
)
SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|client[_-]?secret|password|access[_-]?token|auth[_-]?token|private[_-]?key)\b\s*(?:=|:)\s*[\"']([^\"']+)[\"']"
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    excerpt: str


def _placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return not lowered or any(fragment in lowered for fragment in PLACEHOLDER_FRAGMENTS)


def _files(repo_root: Path):
    for relative_root in SCAN_ROOTS:
        root = repo_root / relative_root
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            relative = path.relative_to(repo_root)
            if str(relative) in SKIP_FILES or any(
                part in SKIP_PARTS for part in relative.parts
            ):
                continue
            yield path, relative
    for name in ("pyproject.toml", "README.md", "RUNBOOK.md", "SECURITY.md"):
        path = repo_root / name
        if path.is_file():
            yield path, Path(name)


def scan(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path, relative in _files(repo_root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if PRIVATE_KEY.search(line):
                findings.append(
                    Finding(str(relative), line_number, "SECRET001", stripped[:240])
                )
            if CREDENTIAL_URL.search(line) and not _placeholder(line):
                findings.append(
                    Finding(str(relative), line_number, "SECRET002", stripped[:240])
                )
            if LIVE_TOKEN.search(line) and not _placeholder(line):
                findings.append(
                    Finding(str(relative), line_number, "SECRET003", stripped[:240])
                )
            for match in SENSITIVE_ASSIGNMENT.finditer(line):
                value = match.group(1)
                if len(value) >= 8 and not _placeholder(value):
                    findings.append(
                        Finding(str(relative), line_number, "SECRET004", stripped[:240])
                    )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    args = parser.parse_args()
    findings = scan(args.repo_root.resolve())
    report = {
        "status": "PASS" if not findings else "FAIL",
        "files_scanned_roots": list(SCAN_ROOTS),
        "finding_count": len(findings),
        "findings": [asdict(item) for item in findings],
    }
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
