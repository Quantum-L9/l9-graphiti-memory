# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/projections/__init__.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-26
"""Projection manifests, deterministic compilation and rendering, and runtime targets."""

from .compiler import (
    canonical_json,
    compile_projection,
    compiled_projection_json,
    sha256_text,
)
from .contracts import (
    CompiledProjection,
    CompiledProjectionTarget,
    ProjectionManifest,
    TargetMode,
)
from .manifest import (
    load_projection_manifest,
    parse_projection_manifest,
    parse_projection_manifest_data,
)
from .render import RenderedProjection, render_projection
from .runtime import ProjectionRuntime, ProjectionTargetBinding

__all__ = [
    "CompiledProjection",
    "CompiledProjectionTarget",
    "ProjectionManifest",
    "ProjectionRuntime",
    "ProjectionTargetBinding",
    "RenderedProjection",
    "TargetMode",
    "canonical_json",
    "compile_projection",
    "compiled_projection_json",
    "load_projection_manifest",
    "parse_projection_manifest",
    "parse_projection_manifest_data",
    "render_projection",
    "sha256_text",
]
