#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/generate_manifest.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Generate a cryptographic release manifest with L9 metadata for every file."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPOSITORY = "Quantum-L9/l9-graphiti-memory"
RELEASE = "2.2.0"
EXCLUDED_ANY_PARTS = {
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    ".venv",
}
EXCLUDED_TOP_LEVEL = {"build", "dist"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _category(relative: Path) -> str:
    parts = relative.parts
    if parts[0] == ".github":
        return "ci"
    if parts[0] == "src":
        return "production_source"
    if parts[0] == "tests":
        return "tests"
    if parts[0] == "tools":
        return "assurance"
    if parts[0] == "hooks":
        return "hooks"
    if parts[0] == "scripts":
        return "operations"
    if parts[0] in {"config", "rules"}:
        return "configuration"
    if parts[0] == "skill":
        return "skill"
    if parts[0] == "validation":
        return "validation_evidence"
    if parts[0] == "docs" and len(parts) > 1 and parts[1] == "adr":
        return "architecture_decisions"
    if parts[0] == "docs":
        return "documentation"
    return "repository_root"


def _layer(relative: Path) -> str:
    category = _category(relative)
    if category == "production_source" and "contracts" in relative.parts:
        return "contract"
    if category == "production_source" and "ports" in relative.parts:
        return "port"
    if category == "production_source" and "integrations" in relative.parts:
        return "integration"
    if category == "production_source" and "adapters" in relative.parts:
        return "adapter"
    if category == "production_source" and "services" in relative.parts:
        return "service"
    return category


def _iter_files(
    root: Path, *, exclude_manifest_markdown: bool = False
) -> tuple[Path, ...]:
    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(
            part in EXCLUDED_ANY_PARTS
            or part.endswith(".egg-info")
            or part == ".coverage"
            or part.startswith(".coverage.")
            or part == "coverage.xml"
            for part in relative.parts
        ):
            continue
        if relative.parts and relative.parts[0] in EXCLUDED_TOP_LEVEL:
            continue
        if relative.as_posix() == "manifest.json":
            continue
        if exclude_manifest_markdown and relative.as_posix() == "MANIFEST.md":
            continue
        result.append(path)
    return tuple(sorted(result))


def _entry(
    root: Path, path: Path, *, override_bytes: bytes | None = None
) -> dict[str, object]:
    relative = path.relative_to(root)
    if override_bytes is None:
        digest = _sha256(path)
        size = path.stat().st_size
    else:
        digest = hashlib.sha256(override_bytes).hexdigest()
        size = len(override_bytes)
    return {
        "category": _category(relative),
        "l9_meta": {
            "l9_schema": 1,
            "repo": REPOSITORY,
            "path": relative.as_posix(),
            "layer": _layer(relative),
            "owner": "memory-control-plane",
            "status": "active",
            "version": RELEASE,
            "updated": "2026-07-22",
        },
        "path": relative.as_posix(),
        "sha256": digest,
        "size_bytes": size,
    }


def _markdown_content(root: Path) -> str:
    entries = [
        _entry(root, path) for path in _iter_files(root, exclude_manifest_markdown=True)
    ]
    counts = Counter(str(entry["category"]) for entry in entries)
    lines = [
        "<!-- L9_META",
        "l9_schema: 1",
        f"repo: {REPOSITORY}",
        "path: MANIFEST.md",
        "layer: repository_root",
        "owner: memory-control-plane",
        "status: active",
        f"version: {RELEASE}",
        "updated: 2026-07-22",
        "/L9_META -->",
        "",
        "# Manifest",
        "",
        "## Identity",
        "",
        f"- Repository: `{REPOSITORY}`",
        f"- Release: `{RELEASE}`",
        "- Artifact class: dependency package with optional service and constellation adapters",
        "- Local validation outcome: `PASS`",
        "- Production release outcome: `BLOCKED_ON_EXTERNAL_VALIDATION`",
        "",
        "## Responsibility map",
        "",
        "| Plane | Owner paths |",
        "|---|---|",
        "| contracts and temporal law | `src/l9_graphite_memory/contracts/`, `schema/` |",
        "| canonical memory control | `services/memory_service.py`, `admission/`, `authz/` |",
        "| storage and projections | `ports/`, `adapters/`, `services/outbox_worker.py` |",
        "| constellation boundary | `ports/constellation.py`, `integrations/constellation.py` |",
        "| local receipt guard | `memory_guard.py`, compatibility hooks |",
        "| assurance | `tools/assurance/`, `tests/`, `validation/` |",
        "",
        "## Inventory summary",
        "",
        "| Category | Files |",
        "|---|---:|",
    ]
    lines.extend(
        f"| `{category}` | {counts[category]} |" for category in sorted(counts)
    )
    lines.extend(
        [
            "",
            f"- Hashed inventory files below: **{len(entries)}**",
            "- `MANIFEST.md` is hashed by `manifest.json`.",
            "- `manifest.json` excludes its own digest to avoid self-reference.",
            "- Every manifest entry carries canonical `l9_meta`, including non-commentable files.",
            "",
            "## File inventory",
            "",
            "| Path | Category | Layer | Bytes | SHA-256 |",
            "|---|---|---|---:|---|",
        ]
    )
    for entry in entries:
        meta = entry["l9_meta"]
        assert isinstance(meta, dict)
        lines.append(
            f"| `{entry['path']}` | `{entry['category']}` | `{meta['layer']}` | "
            f"{entry['size_bytes']} | `{entry['sha256']}` |"
        )
    return "\n".join(lines) + "\n"


def _manifest_content(root: Path, *, markdown_text: str) -> tuple[str, int]:
    markdown_bytes = markdown_text.encode("utf-8")
    entries = [
        _entry(
            root,
            path,
            override_bytes=(
                markdown_bytes
                if path.relative_to(root).as_posix() == "MANIFEST.md"
                else None
            ),
        )
        for path in _iter_files(root)
    ]
    payload = {
        "file_count": len(entries),
        "files": entries,
        "l9_meta": {
            "l9_schema": 1,
            "repo": REPOSITORY,
            "path": "manifest.json",
            "layer": "repository_root",
            "owner": "memory-control-plane",
            "status": "active",
            "version": RELEASE,
            "updated": "2026-07-22",
        },
        "manifest_self_excluded": True,
        "release": RELEASE,
        "repository": REPOSITORY,
        "schema": "l9.release-manifest/v2",
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n", len(entries)


def generate(root: Path, *, check: bool = False) -> int:
    markdown_text = _markdown_content(root)
    manifest_text, count = _manifest_content(root, markdown_text=markdown_text)
    artifacts = {"MANIFEST.md": markdown_text, "manifest.json": manifest_text}
    if check:
        stale: list[str] = []
        for name, content in artifacts.items():
            try:
                current: str | None = (root / name).read_text(encoding="utf-8")
            except FileNotFoundError:
                current = None
            if current != content:
                stale.append(name)
        if stale:
            sys.stdout.write(
                "stale release manifest (run tools/assurance/generate_manifest.py): "
                + ", ".join(sorted(stale))
                + "\n"
            )
            return 1
        sys.stdout.write(f"PASS: release manifest current for {count} files\n")
        return 0
    for name, content in artifacts.items():
        (root / name).write_text(content, encoding="utf-8")
    sys.stdout.write(f"Generated manifest for {count} files\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report stale manifest artifacts and exit non-zero without writing",
    )
    args = parser.parse_args()
    return generate(args.repo_root.resolve(), check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
