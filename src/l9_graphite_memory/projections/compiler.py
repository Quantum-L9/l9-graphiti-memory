# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/projections/compiler.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-26
"""Deterministic side-effect-free projection compiler."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .contracts import (
    CompiledProjection,
    CompiledProjectionTarget,
    ProjectionManifest,
)


def canonical_json(value: Any) -> str:
    """Return canonical UTF-8 JSON suitable for stable hashing."""
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_text(value: str) -> str:
    """Return a lowercase hexadecimal SHA-256 digest."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _dump_for_digest(value: Any) -> dict[str, Any]:
    dumped = value.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    if not isinstance(dumped, dict):
        raise TypeError("projection compiler expected a model mapping")
    return dumped


def compile_projection(manifest: ProjectionManifest) -> CompiledProjection:
    """Compile a strict manifest into an immutable deterministic artifact."""
    manifest_data = _dump_for_digest(manifest)
    manifest_digest = sha256_text(canonical_json(manifest_data))
    render_data = _dump_for_digest(manifest.spec.render)
    render_contract_digest = sha256_text(canonical_json(render_data))
    targets = tuple(
        CompiledProjectionTarget(
            identity=(
                f"{manifest.metadata.name}:v{manifest.metadata.version}:"
                f"{provider.type}:{provider.target}"
            ),
            provider_id=provider.id,
            provider_type=provider.type,
            target=provider.target,
            required=provider.required,
        )
        for provider in sorted(
            manifest.spec.providers,
            key=lambda item: (str(item.type), item.target, item.id),
        )
    )
    artifact_without_digest: dict[str, Any] = {
        "name": manifest.metadata.name,
        "version": manifest.metadata.version,
        "status": manifest.metadata.status,
        "source_event_types": list(manifest.spec.source.event_types),
        "minimum_schema_version": (manifest.spec.source.minimum_schema_version),
        "targets": [target.model_dump(mode="json", by_alias=True) for target in targets],
        "render": render_data,
        "embedding": _dump_for_digest(manifest.spec.embedding),
        "scope": _dump_for_digest(manifest.spec.scope),
        "replay": _dump_for_digest(manifest.spec.replay),
        "deletion": _dump_for_digest(manifest.spec.deletion),
        "slo": _dump_for_digest(manifest.spec.slo),
        "manifest_digest": manifest_digest,
        "render_contract_digest": render_contract_digest,
    }
    compiled_artifact_digest = sha256_text(canonical_json(artifact_without_digest))
    return CompiledProjection(
        name=manifest.metadata.name,
        version=manifest.metadata.version,
        status=manifest.metadata.status,
        source_event_types=manifest.spec.source.event_types,
        minimum_schema_version=(manifest.spec.source.minimum_schema_version),
        targets=targets,
        render=manifest.spec.render,
        embedding=manifest.spec.embedding,
        scope=manifest.spec.scope,
        replay=manifest.spec.replay,
        deletion=manifest.spec.deletion,
        slo=manifest.spec.slo,
        manifest_digest=manifest_digest,
        render_contract_digest=render_contract_digest,
        compiled_artifact_digest=compiled_artifact_digest,
    )


def compiled_projection_json(projection: CompiledProjection) -> str:
    """Serialize a compiled projection deterministically."""
    return canonical_json(
        projection.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
    )
