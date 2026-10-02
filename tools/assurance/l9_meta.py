#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/l9_meta.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-10-02

"""Structural L9 metadata mechanics: the one derivation and parsing owner.

This module is an internal mechanical helper for the assurance tools
(``apply_l9_meta.py``, ``check_l9_meta.py``, ``generate_manifest.py``). It
owns, and nothing else may re-derive:

- repository identity and owner;
- path normalization and the layer derived from a path;
- parsing of one inline ``L9_META`` block (comment or Markdown style);
- comparison of an inline block's structural identity with the identity the
  file's real location implies;
- rendering a block without touching unrelated file content.

It is not a release-admission system. It issues no verdicts about a release;
it only answers "what must this file's structural metadata say, and does it".
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPOSITORY = "Quantum-L9/l9-graphiti-memory"
OWNER = "memory-control-plane"
SCHEMA = "1"

# Fields whose value is a mechanical function of where the file sits.
STRUCTURAL_KEYS: tuple[str, ...] = ("l9_schema", "repo", "path", "layer", "owner")
# Artifact fields: preparation may populate them for a missing header, but
# reconciliation of an existing header never rewrites them from location.
ARTIFACT_KEYS: tuple[str, ...] = ("status", "version", "updated")
CANONICAL_KEY_ORDER: tuple[str, ...] = STRUCTURAL_KEYS + ARTIFACT_KEYS

# An inline block must start within this many lines of the top of the file.
HEAD_LINES = 50

COMMENT_EXTENSIONS: Mapping[str, str] = {
    ".py": "#",
    ".sh": "#",
    ".yaml": "#",
    ".yml": "#",
    ".toml": "#",
    ".in": "#",
}
COMMENT_NAMES: Mapping[str, str] = {".gitignore": "#"}
MARKDOWN_EXTENSIONS = frozenset({".md", ".mdc"})
MARKDOWN_OPEN = "<!-- L9_META"
MARKDOWN_CLOSE = "/L9_META -->"

# Strict-JSON documents that use a .yaml extension for readability but are
# parsed with json.loads (which rejects comments) by the PR pack's own
# validate-pack.sh. Metadata travels through the manifest only.
STRICT_JSON_PATHS = frozenset(
    {
        "docs/WIP/l9-bot-memory-integration-pr-pack/PACK_CONTRACT.yaml",
        "docs/WIP/l9-bot-memory-integration-pr-pack/CONVERGENCE_REPORT.yaml",
        "docs/WIP/l9-bot-memory-integration-pr-pack/PR_STACK.yaml",
    }
)
# Whole subtrees of strict-JSON documents: resolve-governance parses
# .github/governance/* with json.loads, which rejects a comment header.
STRICT_JSON_PREFIXES: tuple[str, ...] = (".github/governance/",)

# Never repository content, whatever the checkout looks like.
EXCLUDED_PARTS = frozenset(
    {
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
)
# Machine-local runtime state the L4 publish path writes into the governed
# `.l9/` namespace. `.l9/` also holds committed governance artifacts, so these
# are excluded by prefix rather than by path part.
MACHINE_LOCAL_PREFIXES: tuple[str, ...] = (".l9/autonomy/", ".l9/pr/")
# The manifest carries metadata for every file and cannot carry a comment.
MANIFEST_SELF = frozenset({"manifest.json"})

# Vendored packs validated by their own exact-state checksum contract
# (tools/phase6/MANIFEST.sha256, executed by tests/regression/
# test_phase6_operator.py). Their inline headers were stamped `repository` when
# vendored and are byte-locked by that contract, so the layer this repository
# derives for them is the layer they carry: a vendored pack is repository
# content, not this repository's own assurance layer.
VENDORED_PREFIXES: tuple[str, ...] = ("tools/phase6/",)

_KEY_VALUE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*?)\s*$")


class MetaError(ValueError):
    """An inline L9_META block exists but cannot be admitted as written."""


@dataclass(frozen=True)
class InlineMeta:
    """One parsed inline block and where it sits in the file's lines."""

    start: int
    end: int
    style: str
    prefix: str
    fields: tuple[tuple[str, str], ...]

    def get(self, key: str) -> str | None:
        for name, value in self.fields:
            if name == key:
                return value
        return None


def normalize_path(relative: str | PurePosixPath | Path) -> PurePosixPath:
    return PurePosixPath(Path(relative).as_posix())


def layer_for(relative: str | PurePosixPath | Path) -> str:
    """Derive the architectural layer from the repository-relative path."""

    rel = normalize_path(relative)
    posix = rel.as_posix()
    parts = rel.parts
    if not parts:
        return "repository"
    if posix.startswith(VENDORED_PREFIXES):
        return "repository"
    if parts[0] == "src":
        # A `contracts/` package and a `contracts.py` module both carry the
        # contract layer; the module form is how a sub-package declares its
        # own contract surface.
        if "contracts" in parts or rel.stem == "contracts":
            return "contract"
        if "ports" in parts:
            return "port"
        if "integrations" in parts:
            return "integration"
        if "adapters" in parts:
            return "adapter"
        if "services" in parts:
            return "service"
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


def structural_identity(relative: str | PurePosixPath | Path) -> dict[str, str]:
    """The structural fields the file at ``relative`` must carry."""

    rel = normalize_path(relative)
    return {
        "l9_schema": SCHEMA,
        "repo": REPOSITORY,
        "path": rel.as_posix(),
        "layer": layer_for(rel),
        "owner": OWNER,
    }


def comment_prefix(relative: str | PurePosixPath | Path) -> str | None:
    """The comment prefix for a comment-style carrier, or None for Markdown."""

    rel = normalize_path(relative)
    if rel.name in COMMENT_NAMES:
        return COMMENT_NAMES[rel.name]
    return COMMENT_EXTENSIONS.get(rel.suffix)


def is_markdown(relative: str | PurePosixPath | Path) -> bool:
    return normalize_path(relative).suffix in MARKDOWN_EXTENSIONS


def is_inline_capable(relative: str | PurePosixPath | Path) -> bool:
    """Whether a tracked file must carry an inline L9_META block."""

    rel = normalize_path(relative)
    posix = rel.as_posix()
    if posix in MANIFEST_SELF or posix in STRICT_JSON_PATHS:
        return False
    if posix.startswith(STRICT_JSON_PREFIXES):
        return False
    return is_markdown(rel) or comment_prefix(rel) is not None


def is_excluded(relative: str | PurePosixPath | Path) -> bool:
    """Paths that are never repository content for metadata purposes."""

    rel = normalize_path(relative)
    posix = rel.as_posix()
    if any(
        part in EXCLUDED_PARTS
        or part.endswith(".egg-info")
        or part == ".coverage"
        or part.startswith(".coverage.")
        or part == "coverage.xml"
        for part in rel.parts
    ):
        return True
    return posix.startswith(MACHINE_LOCAL_PREFIXES)


def git_tracked(root: Path) -> frozenset[str]:
    """Git-tracked paths (posix), or empty when git cannot answer.

    Git is authoritative when it can answer. The exclusion lists are the
    fallback for a checkout git cannot read, such as an unpacked tarball.
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


def repository_files(root: Path) -> tuple[Path, ...]:
    """Files that count as repository content under ``root``, sorted."""

    tracked = git_tracked(root)
    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if tracked and relative.as_posix() not in tracked:
            continue
        if is_excluded(relative):
            continue
        result.append(path)
    return tuple(sorted(result))


def _marker_lines(lines: list[str], prefix: str | None) -> list[int]:
    markers: list[int] = []
    comment_marker = f"{prefix} L9_META" if prefix else None
    for index, line in enumerate(lines[:HEAD_LINES]):
        stripped = line.strip()
        if stripped == MARKDOWN_OPEN or (comment_marker and stripped == comment_marker):
            markers.append(index)
    return markers


def parse_inline(text: str, relative: str | PurePosixPath | Path) -> InlineMeta | None:
    """Parse the one inline block of ``text``.

    Returns None when no block starts within the head window. Raises
    :class:`MetaError` for a duplicate, unterminated, empty, repeated-key or
    otherwise malformed block: a block that cannot be read is never guessed.
    """

    rel = normalize_path(relative)
    prefix = None if is_markdown(rel) else comment_prefix(rel)
    lines = text.splitlines()
    markers = _marker_lines(lines, prefix)
    if not markers:
        return None
    if len(markers) > 1:
        raise MetaError(f"duplicate L9_META block (lines {markers[0] + 1} and {markers[1] + 1})")
    start = markers[0]
    fields: list[tuple[str, str]] = []
    seen: set[str] = set()
    if lines[start].strip() == MARKDOWN_OPEN:
        style = "markdown"
        index = start + 1
        closed = False
        while index < len(lines):
            stripped = lines[index].strip()
            if stripped == MARKDOWN_CLOSE:
                closed = True
                index += 1
                break
            match = _KEY_VALUE.match(stripped)
            if not match:
                raise MetaError(f"malformed L9_META line {index + 1}: {lines[index]!r}")
            key, value = match.group(1), match.group(2)
            if key in seen:
                raise MetaError(f"repeated L9_META key: {key}")
            seen.add(key)
            fields.append((key, value))
            index += 1
        if not closed:
            raise MetaError("unterminated L9_META block")
        end = index
        used_prefix = ""
    else:
        style = "comment"
        assert prefix is not None
        index = start + 1
        while index < len(lines):
            line = lines[index]
            if not line.startswith(prefix):
                break
            body = line[len(prefix) :]
            if not body.startswith(" "):
                break
            match = _KEY_VALUE.match(body.strip())
            if not match:
                break
            key, value = match.group(1), match.group(2)
            if key in seen:
                raise MetaError(f"repeated L9_META key: {key}")
            seen.add(key)
            fields.append((key, value))
            index += 1
        end = index
        used_prefix = prefix
    if not fields:
        raise MetaError("empty L9_META block")
    return InlineMeta(start=start, end=end, style=style, prefix=used_prefix, fields=tuple(fields))


def compare(
    meta: InlineMeta, relative: str | PurePosixPath | Path
) -> tuple[tuple[str, str | None, str], ...]:
    """Structural fields whose inline value differs from the derived identity.

    Each item is ``(field, actual, expected)``; an absent field reports
    ``actual=None``. An empty tuple means the block is structurally valid.
    """

    expected = structural_identity(relative)
    mismatches: list[tuple[str, str | None, str]] = []
    for key in STRUCTURAL_KEYS:
        actual = meta.get(key)
        if actual != expected[key]:
            mismatches.append((key, actual, expected[key]))
    return tuple(mismatches)


def compare_manifest_meta(
    meta: Mapping[str, object], relative: str | PurePosixPath | Path
) -> tuple[tuple[str, str | None, str], ...]:
    """Structural mismatches of a manifest-carried ``l9_meta`` object."""

    expected = structural_identity(relative)
    mismatches: list[tuple[str, str | None, str]] = []
    for key in STRUCTURAL_KEYS:
        raw = meta.get(key)
        actual = None if raw is None else str(raw)
        if actual != expected[key]:
            mismatches.append((key, actual, expected[key]))
    return tuple(mismatches)


def canonical_fields(
    relative: str | PurePosixPath | Path,
    *,
    status: str,
    version: str,
    updated: str,
) -> list[tuple[str, str]]:
    """A complete block for a file that has none: structural plus artifact."""

    identity = structural_identity(relative)
    return [
        *((key, identity[key]) for key in STRUCTURAL_KEYS),
        ("status", status),
        ("version", version),
        ("updated", updated),
    ]


def reconcile_fields(
    meta: InlineMeta, relative: str | PurePosixPath | Path
) -> list[tuple[str, str]]:
    """Structural fields corrected; artifact and extra fields preserved verbatim."""

    identity = structural_identity(relative)
    existing = dict(meta.fields)
    result: list[tuple[str, str]] = [(key, identity[key]) for key in STRUCTURAL_KEYS]
    for key in ARTIFACT_KEYS:
        if key in existing:
            result.append((key, existing[key]))
    for key, value in meta.fields:
        if key not in CANONICAL_KEY_ORDER:
            result.append((key, value))
    return result


def render_block(fields: Iterable[tuple[str, str]], *, style: str, prefix: str = "#") -> list[str]:
    """Render block lines in the repository's one inline format."""

    pairs = list(fields)
    if style == "markdown":
        return [MARKDOWN_OPEN, *(f"{key}: {value}" for key, value in pairs), MARKDOWN_CLOSE]
    if style != "comment":
        raise ValueError(f"unknown L9_META style: {style}")
    return [f"{prefix} L9_META", *(f"{prefix}   {key}: {value}" for key, value in pairs)]


def reconcile_text(text: str, relative: str | PurePosixPath | Path) -> str:
    """Return ``text`` with its inline block's structural identity corrected.

    Only the block's lines change; every other byte of the file is kept. The
    caller decides whether a change is wanted (``apply``) or only reported
    (``check``). Raises :class:`MetaError` when there is no admissible block.
    """

    meta = parse_inline(text, relative)
    if meta is None:
        raise MetaError("no inline L9_META block to reconcile")
    lines = text.splitlines()
    block = render_block(reconcile_fields(meta, relative), style=meta.style, prefix=meta.prefix)
    lines[meta.start : meta.end] = block
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
