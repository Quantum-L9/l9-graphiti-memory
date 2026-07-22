# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/lineage/replay.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Deterministic provenance and supersession lineage reconstruction."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from l9_graphite_memory.contracts import MemoryRecord, MemoryState
from l9_graphite_memory.ports import RecordStore


class LineageIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_type: str
    record_id: UUID
    related_id: UUID | None = None
    detail: str


class LineageReplay(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    root_record_id: UUID
    ordered_record_ids: tuple[UUID, ...]
    edges: tuple[tuple[UUID, UUID, str], ...]
    issues: tuple[LineageIssue, ...] = ()
    complete: bool
    policy_version: str = "memory-lineage/v1"


class LineageReplayer:
    def __init__(self, store: RecordStore) -> None:
        self.store = store

    @staticmethod
    def _uuid(value: str | None) -> UUID | None:
        if not value:
            return None
        try:
            return UUID(value)
        except ValueError:
            return None

    def replay(
        self,
        tenant_id: str,
        namespace: str,
        root_record_id: UUID,
    ) -> LineageReplay:
        records = self.store.list_records(
            tenant_id,
            namespace,
            states=tuple(MemoryState),
            limit=100_000,
        )
        by_id = {record.record_id: record for record in records}
        issues: list[LineageIssue] = []
        edges: list[tuple[UUID, UUID, str]] = []
        visited: set[UUID] = set()
        active: set[UUID] = set()
        ordered: list[UUID] = []

        def parents(record: MemoryRecord) -> tuple[tuple[UUID, str], ...]:
            values: list[tuple[UUID, str]] = []
            values.extend((item, "supersedes") for item in record.supersedes)
            values.extend((item, "references") for item in record.references)
            values.extend((item, "conflicts_with") for item in record.conflicts_with)
            source_id = self._uuid(record.provenance.source_id)
            if source_id is not None:
                values.append((source_id, "derived_from"))
            return tuple(dict.fromkeys(values))

        def visit(record_id: UUID) -> None:
            if record_id in active:
                issues.append(
                    LineageIssue(
                        issue_type="cycle",
                        record_id=record_id,
                        detail="lineage cycle detected",
                    )
                )
                return
            if record_id in visited:
                return
            record = by_id.get(record_id)
            if record is None:
                issues.append(
                    LineageIssue(
                        issue_type="orphan",
                        record_id=root_record_id,
                        related_id=record_id,
                        detail="referenced record is missing from the authorized namespace",
                    )
                )
                return
            active.add(record_id)
            for parent_id, relationship in parents(record):
                edges.append((record_id, parent_id, relationship))
                visit(parent_id)
            active.remove(record_id)
            visited.add(record_id)
            ordered.append(record_id)

        visit(root_record_id)
        return LineageReplay(
            root_record_id=root_record_id,
            ordered_record_ids=tuple(ordered),
            edges=tuple(edges),
            issues=tuple(issues),
            complete=not issues,
        )
