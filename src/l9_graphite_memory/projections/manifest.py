# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/projections/manifest.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-26
"""Strict loading and parsing of projection manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from l9_graphite_memory.errors import ConfigurationError

from .contracts import ProjectionManifest


def parse_projection_manifest_data(data: Any) -> ProjectionManifest:
    """Validate an already-decoded projection-manifest value."""
    if not isinstance(data, dict):
        raise ConfigurationError("projection manifest root must be a mapping")
    try:
        return ProjectionManifest.model_validate(data)
    except ValidationError as exc:
        raise ConfigurationError(f"invalid projection manifest: {exc}") from exc


def parse_projection_manifest(raw: str) -> ProjectionManifest:
    """Parse and validate a YAML projection manifest."""
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigurationError(
            f"projection manifest is not valid YAML: {exc}"
        ) from exc
    return parse_projection_manifest_data(data)


def load_projection_manifest(path: str | Path) -> ProjectionManifest:
    """Read and validate a projection manifest from disk."""
    manifest_path = Path(path).expanduser()
    if not manifest_path.is_file():
        raise ConfigurationError(
            f"projection manifest does not exist: {manifest_path}"
        )
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(
            f"could not read projection manifest {manifest_path}: {exc}"
        ) from exc
    return parse_projection_manifest(raw)
