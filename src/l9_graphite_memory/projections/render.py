# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/projections/render.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-26
"""Deterministic canonical rendering for projection providers."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from l9_graphite_memory.errors import ProjectionError

from .contracts import CompiledProjection


class RenderedProjection(BaseModel):
    """Immutable deterministic rendered projection payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    template: str
    template_digest: str
    normalized_text: str
    metadata: dict[str, Any]
    content_digest: str
    embedding_cache_key: str | None


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        return {
            str(key): _normalize(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }
    if isinstance(value, tuple | list):
        return [_normalize(item) for item in value]
    return value


def _record_mapping(record: Mapping[str, Any] | BaseModel) -> dict[str, Any]:
    if isinstance(record, BaseModel):
        value = record.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=False,
        )
    else:
        value = dict(record)
    return {str(key): item for key, item in value.items()}


def render_projection(
    projection: CompiledProjection,
    record: Mapping[str, Any] | BaseModel,
) -> RenderedProjection:
    """Render declared canonical fields with no ambient dependencies."""
    record_data = _record_mapping(record)
    missing = [
        field
        for field in projection.render.fields
        if field not in record_data
    ]
    if missing:
        raise ProjectionError(
            "record is missing declared projection fields: "
            + ", ".join(sorted(missing))
        )
    metadata = {
        field: _normalize(record_data[field])
        for field in projection.render.fields
    }
    lines = [
        f"{field}={_canonical_json(metadata[field])}"
        for field in projection.render.fields
    ]
    normalized_text = unicodedata.normalize("NFC", "\n".join(lines))
    content_digest = _digest(normalized_text)
    embedding_cache_key: str | None = None
    if projection.embedding.cache_policy == "content-addressed-v1":
        embedding_cache_key = _digest(
            f"{projection.render_contract_digest}\x1f"
            f"{projection.embedding.model}\x1f"
            f"{normalized_text}"
        )
    return RenderedProjection(
        template=projection.render.template,
        template_digest=projection.render_contract_digest,
        normalized_text=normalized_text,
        metadata=metadata,
        content_digest=content_digest,
        embedding_cache_key=embedding_cache_key,
    )
