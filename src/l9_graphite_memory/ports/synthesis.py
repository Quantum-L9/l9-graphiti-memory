# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ports/synthesis.py
#   layer: port
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Optional governed procedural synthesis port."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SynthesizedProcedure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=300)
    condition: str = Field(min_length=1, max_length=4_000)
    action: str = Field(min_length=1, max_length=4_000)
    confidence: float = Field(ge=0.0, le=1.0)
    source_record_ids: tuple[UUID, ...]


class ProceduralSynthesizer(Protocol):
    def synthesize(
        self, source_record_ids: tuple[UUID, ...]
    ) -> tuple[SynthesizedProcedure, ...]: ...
