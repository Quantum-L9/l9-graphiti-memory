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
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPOSITORY = "Quantum-L9/l9-graphiti-memory"
RELEASE = "2.2.0"
EXCLUDED_ANY_PARTS = {".git", ".pytest_cache", "__pycache__", ".venv"}
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


def _tracked_paths(root: Path) -> frozenset[str]:
    """Return git-tracked paths (posix), or empty when git cannot answer.

    A release manifest describes committed repository content, and git already
    knows exactly what that is. Deriving the file set from a hand-maintained
    exclusion list instead let lint and type caches, editable-install
    ``*.egg-info`` and build output into the manifest, which made it churn
    per-machine and recorded files a clean checkout does not have.

    Mirrors ``check_recursive_alignment._tracked_paths``.
    """

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


def _is_repository_content(relative: Path, tracked: frozenset[str]) -> bool:
    """Whether one path counts as committed repository content.

    Git is authoritative when it can answer. The exclusion lists are the
    fallback for a checkout git cannot read, such as an unpacked release
    tarball.
    """

    if tracked:
        return relative.as_posix() in tracked
    if any(part in EXCLUDED_ANY_PARTS for part in relative.parts):
        return False
    return not (relative.parts and relative.parts[0] in EXCLUDED_TOP_LEVEL)


def _iter_files(root: Path, *, exclude_manifest_markdown: bool = False) -> tuple[Path, ...]:
    tracked = _tracked_paths(root)
    self_excluded = {"manifest.json"}
    if exclude_manifest_markdown:
        self_excluded.add("MANIFEST.md")
    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.as_posix() in self_excluded:
            continue
        if not _is_repository_content(relative, tracked):
            continue
        result.append(path)
    return tuple(sorted(result))


def _entry(root: Path, path: Path) -> dict[str, object]:
    relative = path.relative_to(root)
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
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _write_markdown(root: Path) -> None:
    entries = [_entry(root, path) for path in _iter_files(root, exclude_manifest_markdown=True)]
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
    lines.extend(f"| `{category}` | {counts[category]} |" for category in sorted(counts))
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
    (root / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate(root: Path) -> int:
    _write_markdown(root)
    entries = [_entry(root, path) for path in _iter_files(root)]
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
    (root / "manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    sys.stdout.write(f"Generated manifest for {len(entries)} files\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    return generate(parser.parse_args().repo_root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
