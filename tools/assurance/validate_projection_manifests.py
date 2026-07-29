#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/validate_projection_manifests.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-26
"""Validate and deterministically compile projection manifests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from l9_graphite_memory.errors import ConfigurationError
from l9_graphite_memory.projections import (
    compile_projection,
    compiled_projection_json,
    load_projection_manifest,
)


def validate_path(path: Path) -> dict[str, object]:
    manifest = load_projection_manifest(path)
    first = compile_projection(manifest)
    second = compile_projection(manifest)
    first_json = compiled_projection_json(first)
    second_json = compiled_projection_json(second)
    if first_json != second_json:
        raise ConfigurationError(f"projection compilation is not deterministic: {path}")
    return {
        "path": str(path),
        "name": first.name,
        "version": first.version,
        "target_count": len(first.targets),
        "manifest_digest": first.manifest_digest,
        "render_contract_digest": first.render_contract_digest,
        "compiled_artifact_digest": first.compiled_artifact_digest,
        "deterministic": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[],
    )
    args = parser.parse_args(argv)
    paths = args.paths or sorted(Path("config/projections").glob("*.yaml"))
    if not paths:
        sys.stderr.write("ERROR: no projection manifests found\n")
        return 1
    results: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for path in paths:
        try:
            results.append(validate_path(path))
        except (ConfigurationError, OSError, ValueError) as exc:
            failures.append(
                {
                    "path": str(path),
                    "error": str(exc),
                }
            )
    payload = {
        "valid": not failures,
        "results": results,
        "failures": failures,
    }
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
