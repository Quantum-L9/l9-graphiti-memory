# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/episode_contract.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Legacy EpisodeContract compatibility model."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from l9_graphite_memory.admission.normalization import normalize_candidate

FORBIDDEN_GROUPS = {"main", "default", "", "test"}


class EpisodeContract(BaseModel):
    """Validate v1 episode payloads before translating them into v2 requests."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=200)
    episode_body: str = Field(min_length=1, max_length=64_000)
    source: Literal["text", "json", "message"]
    source_description: str = Field(max_length=500)
    reference_time: datetime
    group_id: str = Field(min_length=3, max_length=300)
    kind: str | None = None
    pii_redaction: bool = True

    @field_validator("reference_time")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        if aware > datetime.now(timezone.utc) + timedelta(hours=1):
            raise ValueError(
                "reference_time cannot be more than one hour in the future"
            )
        return aware

    @field_validator("group_id")
    @classmethod
    def validate_group(cls, value: str) -> str:
        if value in FORBIDDEN_GROUPS:
            raise ValueError(f"forbidden group_id: {value}")
        return value

    def to_mcp_payload(self) -> dict[str, object]:
        content = (
            normalize_candidate(self.episode_body).redacted_content
            if self.pii_redaction
            else self.episode_body
        )
        return {
            "name": self.name,
            "episode_body": content,
            "source": self.source,
            "source_description": self.source_description,
            "reference_time": self.reference_time.isoformat(),
            "group_id": self.group_id,
            "kind": self.kind,
        }
