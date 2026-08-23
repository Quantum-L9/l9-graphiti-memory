#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: docs/WIP/l9-bot-memory-integration-pr-pack/scripts/regenerate-manifest.py
#   layer: documentation
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-31

"""Regenerate this pack's own MANIFEST.md, MANIFEST.sha256, and manifest.json.

Each of the three carriers excludes only its own entry from its content and
lists the other two, so no file's digest depends on its own bytes. Run this
after adding, removing, or editing any file under the pack directory.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _entries(exclude: str) -> list[tuple[str, int, str]]:
    out = []
    for path in sorted(p for p in ROOT.rglob("*") if p.is_file()):
        rel = str(path.relative_to(ROOT))
        if rel == exclude:
            continue
        data = path.read_bytes()
        out.append((rel, len(data), hashlib.sha256(data).hexdigest()))
    return out


def main() -> int:
    md_rows = _entries("MANIFEST.md")
    lines = [
        "<!-- L9_META",
        "l9_schema: 1",
        "repo: Quantum-L9/l9-graphiti-memory",
        "path: docs/WIP/l9-bot-memory-integration-pr-pack/MANIFEST.md",
        "layer: documentation",
        "owner: memory-control-plane",
        "status: active",
        "version: 2.2.0",
        "updated: 2026-07-31",
        "/L9_META -->",
        "",
        "# Manifest",
        "",
        (
            "Generated file inventory. Each of `MANIFEST.md`, `MANIFEST.sha256`, "
            "and `manifest.json` excludes only its own entry and lists the other two."
        ),
        "",
        f"File count: **{len(md_rows)}**",
        "",
        "| Path | Bytes | SHA-256 |",
        "|---|---:|---|",
    ]
    lines.extend(f"| `{rel}` | {size} | `{digest}` |" for rel, size, digest in md_rows)
    (ROOT / "MANIFEST.md").write_text("\n".join(lines) + "\n")

    json_rows = _entries("manifest.json")
    manifest_json = {
        "schema": "l9.pack-manifest/v1",
        "file_count": len(json_rows),
        "files": [
            {"path": rel, "bytes": size, "sha256": digest} for rel, size, digest in json_rows
        ],
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest_json, indent=2) + "\n")

    sha_rows = _entries("MANIFEST.sha256")
    with (ROOT / "MANIFEST.sha256").open("w") as handle:
        for rel, _size, digest in sorted(sha_rows, key=lambda t: t[0]):
            handle.write(f"{digest}  {rel}\n")

    print(f"rows md={len(md_rows)} json={len(json_rows)} sha={len(sha_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
