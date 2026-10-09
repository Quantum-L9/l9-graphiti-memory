#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/generate_manifest.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-10-02

"""Generate, or check, the cryptographic release manifest.

Apply mode (default) writes ``MANIFEST.md`` and ``manifest.json``; it is part
of explicit release PREPARATION. ``--check`` renders the same bytes in memory,
compares them with the committed artifacts, reports drift and writes nothing;
release validation runs only that mode.

The manifest owns inventory and provenance: identity, release version,
artifact classification, file inventory, categories, sizes, digests and L9
metadata. It states no validation or admission outcome; those are earned by
the validators that read it, never declared by the generator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import l9_meta

REPOSITORY = l9_meta.REPOSITORY
RELEASE = "2.6.0"
META_STATUS = "active"
META_UPDATED = "2026-07-22"
MANIFEST_MARKDOWN = "MANIFEST.md"
MANIFEST_JSON = "manifest.json"
EXCLUDED_ANY_PARTS = {".git", ".pytest_cache", "__pycache__", ".venv"}
EXCLUDED_TOP_LEVEL = {"build", "dist"}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def _iter_files(root: Path) -> tuple[Path, ...]:
    tracked = l9_meta.git_tracked(root)
    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.as_posix() in {MANIFEST_JSON, MANIFEST_MARKDOWN}:
            continue
        if not _is_repository_content(relative, tracked):
            continue
        result.append(path)
    return tuple(sorted(result))


def _meta(relative: Path) -> dict[str, object]:
    identity = l9_meta.structural_identity(relative)
    return {
        "l9_schema": int(identity["l9_schema"]),
        "repo": identity["repo"],
        "path": identity["path"],
        "layer": identity["layer"],
        "owner": identity["owner"],
        "status": META_STATUS,
        "version": RELEASE,
        "updated": META_UPDATED,
    }


def _entry(relative: Path, *, sha256: str, size_bytes: int) -> dict[str, object]:
    return {
        "category": _category(relative),
        "l9_meta": _meta(relative),
        "path": relative.as_posix(),
        "sha256": sha256,
        "size_bytes": size_bytes,
    }


def _file_entry(root: Path, path: Path) -> dict[str, object]:
    return _entry(path.relative_to(root), sha256=_sha256(path), size_bytes=path.stat().st_size)


def render_markdown(entries: list[dict[str, object]]) -> str:
    counts = Counter(str(entry["category"]) for entry in entries)
    header = l9_meta.render_block(
        l9_meta.canonical_fields(
            MANIFEST_MARKDOWN, status=META_STATUS, version=RELEASE, updated=META_UPDATED
        ),
        style="markdown",
    )
    lines = [
        *header,
        "",
        "# Manifest",
        "",
        "## Identity",
        "",
        f"- Repository: `{REPOSITORY}`",
        f"- Release: `{RELEASE}`",
        "- Artifact class: dependency package with optional service and constellation adapters",
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
    return "\n".join(lines) + "\n"


def render_manifest(entries: list[dict[str, object]]) -> str:
    payload = {
        "file_count": len(entries),
        "files": entries,
        "l9_meta": _meta(Path(MANIFEST_JSON)),
        "manifest_self_excluded": True,
        "release": RELEASE,
        "repository": REPOSITORY,
        "schema": "l9.release-manifest/v2",
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render(root: Path) -> tuple[str, str]:
    """Render ``(MANIFEST.md, manifest.json)`` for the tree under ``root``.

    Pure: nothing is written. The manifest entry for ``MANIFEST.md`` is taken
    from the bytes rendered here, not from whatever is on disk, so a check can
    compare the committed artifacts with the content the tree implies.
    """

    file_entries = [_file_entry(root, path) for path in _iter_files(root)]
    markdown = render_markdown(file_entries)
    markdown_bytes = markdown.encode("utf-8")
    markdown_entry = _entry(
        Path(MANIFEST_MARKDOWN),
        sha256=_sha256_bytes(markdown_bytes),
        size_bytes=len(markdown_bytes),
    )
    json_entries = sorted([*file_entries, markdown_entry], key=lambda item: str(item["path"]))
    return markdown, render_manifest(json_entries)


def generate(root: Path) -> int:
    markdown, manifest = render(root)
    (root / MANIFEST_MARKDOWN).write_text(markdown, encoding="utf-8")
    (root / MANIFEST_JSON).write_text(manifest, encoding="utf-8")
    count = json.loads(manifest)["file_count"]
    sys.stdout.write(f"Generated manifest for {count} files\n")
    return 0


def _drift(expected_json: str, actual_json: str) -> list[str]:
    try:
        actual = json.loads(actual_json)
    except json.JSONDecodeError:
        return ["manifest.json: not valid JSON"]
    expected = json.loads(expected_json)
    expected_files = {str(e["path"]): e for e in expected["files"]}
    actual_files = (
        {str(e.get("path")): e for e in actual.get("files", []) if isinstance(e, dict)}
        if isinstance(actual, dict)
        else {}
    )
    findings: list[str] = []
    for path in sorted(set(expected_files) | set(actual_files)):
        exp, act = expected_files.get(path), actual_files.get(path)
        if exp is None:
            findings.append(f"manifest.json lists a file the tree does not have: {path}")
        elif act is None:
            findings.append(f"manifest.json is missing a tracked file: {path}")
        elif exp != act:
            changed = sorted(key for key in exp if exp.get(key) != act.get(key))
            findings.append(f"manifest.json entry drifted: {path} ({', '.join(changed)})")
    if isinstance(actual, dict):
        for key in ("file_count", "l9_meta", "release", "repository", "schema"):
            if actual.get(key) != expected.get(key):
                findings.append(f"manifest.json field drifted: {key}")
    return findings


def check(root: Path) -> int:
    """Compare rendered expectation with the committed artifacts; write nothing."""

    expected_markdown, expected_manifest = render(root)
    failures: list[str] = []
    markdown_path = root / MANIFEST_MARKDOWN
    manifest_path = root / MANIFEST_JSON
    actual_markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.is_file() else ""
    actual_manifest = manifest_path.read_text(encoding="utf-8") if manifest_path.is_file() else ""
    if actual_markdown != expected_markdown:
        failures.append("MANIFEST.md differs from the content the tracked tree implies")
    if actual_manifest != expected_manifest:
        failures.append("manifest.json differs from the content the tracked tree implies")
        failures.extend(_drift(expected_manifest, actual_manifest))
    if failures:
        sys.stdout.write("\n".join(failures) + "\n")
        sys.stdout.write(
            "FAIL: manifest drift; run tools/assurance/generate_manifest.py during "
            "preparation and commit the result\n"
        )
        return 1
    count = json.loads(expected_manifest)["file_count"]
    sys.stdout.write(
        f"PASS: MANIFEST.md and manifest.json match the tracked tree ({count} files)\n"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the committed manifest artifacts with the tree; write nothing",
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    return check(root) if args.check else generate(root)


if __name__ == "__main__":
    raise SystemExit(main())
