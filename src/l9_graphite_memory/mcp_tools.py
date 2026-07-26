# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/mcp_tools.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""One machine-readable MCP tool inventory and its canonical handlers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from l9_graphite_memory.contracts import (
    AuthorizationAction,
    Confidence,
    ConsentGrant,
    DeletionRequest,
    EvidenceKind,
    EvidenceRef,
    HydrationRequest,
    MemoryAssertion,
    MemoryClass,
    MemoryPrincipal,
    MemorySearchRequest,
    MemoryWriteRequest,
    PhaseLockRequest,
    PromotionRequest,
    Provenance,
)
from l9_graphite_memory.curation.procedural import (
    PatternProceduralSynthesizer,
    ProceduralSynthesisWorker,
)
from l9_graphite_memory.errors import AuthorizationError
from l9_graphite_memory.extraction import SourceDistiller
from l9_graphite_memory.ingestion import RepositoryBootstrapper
from l9_graphite_memory.services import MemoryService


def _object_schema(
    properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _consent_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "subject_id": {"type": "string"},
            "purpose": {"type": "string"},
            "evidence_description": {"type": "string"},
            "source_id": {"type": "string"},
            "allowed_classes": {"type": "array", "items": {"type": "string"}},
            "expires_at": {"type": "string", "format": "date-time"},
        },
        ["subject_id", "purpose", "evidence_description"],
    )


CANONICAL_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "memory.ingest",
        "description": "Admit one governed, evidence-bearing memory record.",
        "inputSchema": _object_schema(
            {
                "namespace": {"type": "string"},
                "content": {"type": "string"},
                "memory_class": {"type": "string", "default": "observation"},
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "object": {"type": "string"},
                "source_id": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "valid_from": {"type": "string", "format": "date-time"},
                "valid_to": {"type": "string", "format": "date-time"},
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 1,
                },
                "source_trust": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 1,
                },
                "consent": _consent_schema(),
                "tags": {"type": "array", "items": {"type": "string"}},
                "supersedes": {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                },
                "references": {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                },
                "dry_run": {"type": "boolean", "default": False},
            },
            ["namespace", "content"],
        ),
    },
    {
        "name": "memory.search",
        "description": "Search authorized namespaces with temporal and class filters.",
        "inputSchema": _object_schema(
            {
                "query": {"type": "string"},
                "namespaces": {"type": "array", "items": {"type": "string"}},
                "memory_classes": {"type": "array", "items": {"type": "string"}},
                "valid_at": {"type": "string", "format": "date-time"},
                "recorded_before": {"type": "string", "format": "date-time"},
                "include_superseded": {"type": "boolean", "default": False},
                "include_archived": {"type": "boolean", "default": False},
                "min_confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 20,
                },
            },
            ["query", "namespaces"],
        ),
    },
    {
        "name": "memory.hydrate",
        "description": "Build a bounded, class-aware context bundle for a task.",
        "inputSchema": _object_schema(
            {
                "task": {"type": "string"},
                "namespaces": {"type": "array", "items": {"type": "string"}},
                "entities": {"type": "array", "items": {"type": "string"}},
                "topics": {"type": "array", "items": {"type": "string"}},
                "memory_classes": {"type": "array", "items": {"type": "string"}},
                "token_budget": {
                    "type": "integer",
                    "minimum": 128,
                    "maximum": 64000,
                    "default": 1200,
                },
                "max_records": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 40,
                },
            },
            ["task", "namespaces"],
        ),
    },
    {
        "name": "memory.get",
        "description": "Retrieve one authorized canonical memory record by UUID.",
        "inputSchema": _object_schema(
            {"record_id": {"type": "string", "format": "uuid"}}, ["record_id"]
        ),
    },
    {
        "name": "memory.conflicts",
        "description": "Find overlapping structured assertions with different values.",
        "inputSchema": _object_schema({"namespace": {"type": "string"}}, ["namespace"]),
    },
    {
        "name": "memory.phase_lock",
        "description": "Grant a task lock only after a successful conflict check.",
        "inputSchema": _object_schema(
            {
                "namespace": {"type": "string"},
                "task_signature": {"type": "string"},
                "ttl_seconds": {
                    "type": "integer",
                    "minimum": 60,
                    "maximum": 86400,
                    "default": 1800,
                },
            },
            ["namespace", "task_signature"],
        ),
    },
    {
        "name": "memory.verify_phase_lock",
        "description": "Verify that a phase lock is current, conflict-free, and bound to the current namespace snapshot.",
        "inputSchema": _object_schema(
            {
                "namespace": {"type": "string"},
                "task_signature": {"type": "string"},
            },
            ["namespace", "task_signature"],
        ),
    },
    {
        "name": "memory.lineage",
        "description": "Replay a record's supersession, reference, conflict, and provenance lineage.",
        "inputSchema": _object_schema(
            {
                "namespace": {"type": "string"},
                "record_id": {"type": "string", "format": "uuid"},
            },
            ["namespace", "record_id"],
        ),
    },
    {
        "name": "memory.retention",
        "description": "Evaluate or apply reference-aware retention without destructive deletion.",
        "inputSchema": _object_schema(
            {
                "namespace": {"type": "string"},
                "apply": {"type": "boolean", "default": False},
            },
            ["namespace"],
        ),
    },
    {
        "name": "memory.delete",
        "description": "Request verified administrative deletion with a durable tombstone receipt.",
        "inputSchema": _object_schema(
            {
                "record_id": {"type": "string", "format": "uuid"},
                "reason": {"type": "string"},
                "verification_reference": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
            },
            ["record_id", "reason", "verification_reference"],
        ),
    },
    {
        "name": "memory.promote",
        "description": "Promote a record through deterministic, default-deny curation rules.",
        "inputSchema": _object_schema(
            {
                "record_id": {"type": "string", "format": "uuid"},
                "target_class": {"type": "string"},
                "reason": {"type": "string"},
                "explicit_confirmation": {"type": "boolean", "default": False},
                "governance_approval": {"type": "boolean", "default": False},
                "test_success_count": {"type": "integer", "minimum": 0, "default": 0},
                "supporting_record_ids": {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                },
                "consent": _consent_schema(),
            },
            ["record_id", "target_class", "reason"],
        ),
    },
    {
        "name": "memory.bootstrap",
        "description": "Import repository docs and ADRs through canonical ingestion. Admin only.",
        "inputSchema": _object_schema(
            {
                "namespace": {"type": "string"},
                "repo_path": {"type": "string", "default": "."},
                "dry_run": {"type": "boolean", "default": False},
            },
            ["namespace"],
        ),
    },
    {
        "name": "memory.distill",
        "description": "Distill a local text file into evidence-bound atomic memory candidates. Admin only.",
        "inputSchema": _object_schema(
            {
                "namespace": {"type": "string"},
                "path": {"type": "string"},
                "repository": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
            },
            ["namespace", "path"],
        ),
    },
    {
        "name": "memory.synthesize_procedures",
        "description": "Create review-required procedural candidates from corroborated successful records.",
        "inputSchema": _object_schema(
            {
                "namespace": {"type": "string"},
                "source_record_ids": {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                    "minItems": 1,
                },
                "minimum_support": {"type": "integer", "minimum": 2, "default": 3},
                "dry_run": {"type": "boolean", "default": False},
            },
            ["namespace", "source_record_ids"],
        ),
    },
    {
        "name": "memory.health",
        "description": "Check canonical store, projection, schema, and outbox health.",
        "inputSchema": _object_schema({}),
    },
)

ALIASES: dict[str, str] = {
    "write": "memory.ingest",
    "search": "memory.search",
    "health": "memory.health",
    "bootstrap": "memory.bootstrap",
    "phase_lock": "memory.phase_lock",
    "verify_phase_lock": "memory.verify_phase_lock",
    "conflicts": "memory.conflicts",
}


def tool_definitions() -> list[dict[str, Any]]:
    definitions = list(CANONICAL_TOOLS)
    by_name = {item["name"]: item for item in CANONICAL_TOOLS}
    for alias, canonical in ALIASES.items():
        base = by_name[canonical]
        definitions.append(
            {
                **base,
                "name": alias,
                "description": f"Compatibility alias for {canonical}. {base['description']}",
            }
        )
    return definitions


def _dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _consent_from_payload(
    value: Any,
    *,
    namespace: str,
    memory_class: MemoryClass,
    principal: MemoryPrincipal,
) -> ConsentGrant | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("consent must be an object")  # noqa: TRY004
    return ConsentGrant(
        subject_id=str(value["subject_id"]),
        namespace=namespace,
        allowed_classes=tuple(
            MemoryClass(str(item))
            for item in value.get("allowed_classes", [memory_class.value])
        ),
        purpose=str(value["purpose"]),
        evidence=EvidenceRef(
            kind=EvidenceKind.EXPLICIT,
            description=str(value["evidence_description"]),
            source_id=str(value.get("source_id") or principal.audit_subject),
        ),
        expires_at=_dt(value.get("expires_at")),
    )


class MCPToolApplication:
    """Convert tool payloads to typed requests and call MemoryService."""

    def __init__(self, service: MemoryService) -> None:
        self.service = service

    def call(
        self, principal: MemoryPrincipal, name: str, arguments: dict[str, Any]
    ) -> Any:
        canonical = ALIASES.get(name, name)
        handlers = {
            "memory.ingest": self._ingest,
            "memory.search": self._search,
            "memory.hydrate": self._hydrate,
            "memory.get": self._get,
            "memory.conflicts": self._conflicts,
            "memory.phase_lock": self._phase_lock,
            "memory.verify_phase_lock": self._verify_phase_lock,
            "memory.lineage": self._lineage,
            "memory.retention": self._retention,
            "memory.delete": self._delete,
            "memory.promote": self._promote,
            "memory.bootstrap": self._bootstrap,
            "memory.distill": self._distill,
            "memory.synthesize_procedures": self._synthesize_procedures,
            "memory.health": self._health,
        }
        handler = handlers.get(canonical)
        if handler is None:
            raise KeyError(f"unknown tool: {name}")
        try:
            return handler(principal, arguments)
        except ValidationError as exc:
            raise ValueError(f"invalid {canonical} arguments: {exc}") from exc

    def _ingest(self, principal: MemoryPrincipal, args: dict[str, Any]) -> Any:
        subject = args.get("subject")
        predicate = args.get("predicate")
        object_value = args.get("object")
        assertion = None
        if any((subject, predicate, object_value)):
            if not all((subject, predicate, object_value)):
                raise ValueError(
                    "subject, predicate, and object must be supplied together"
                )
            assertion = MemoryAssertion(
                subject=str(subject), predicate=str(predicate), object=str(object_value)
            )
        memory_class = MemoryClass(str(args.get("memory_class", "observation")))
        consent = _consent_from_payload(
            args.get("consent"),
            namespace=str(args["namespace"]),
            memory_class=memory_class,
            principal=principal,
        )
        request = MemoryWriteRequest(
            namespace=str(args["namespace"]),
            memory_class=memory_class,
            content=str(args["content"]),
            assertion=assertion,
            provenance=Provenance(
                source="mcp",
                source_id=str(args.get("source_id")) if args.get("source_id") else None,
                source_agent_id=principal.agent_id,
                tool="memory.ingest",
                extraction_method="direct-mcp/v1",
                source_trust=float(args.get("source_trust", 1.0)),
            ),
            evidence=(
                EvidenceRef(
                    kind=EvidenceKind.EXPLICIT,
                    description="authenticated caller submitted this memory through MCP",
                    source_id=principal.audit_subject,
                ),
            ),
            confidence=Confidence(
                score=float(args.get("confidence", 1.0)), evidence_count=1
            ),
            valid_from=_dt(args.get("valid_from")) or datetime.now(timezone.utc),
            valid_to=_dt(args.get("valid_to")),
            tags=tuple(str(value) for value in args.get("tags", [])),
            idempotency_key=str(args.get("idempotency_key"))
            if args.get("idempotency_key")
            else None,
            supersedes=tuple(UUID(str(value)) for value in args.get("supersedes", [])),
            references=tuple(UUID(str(value)) for value in args.get("references", [])),
            consent=consent,
            dry_run=bool(args.get("dry_run", False)),
        )
        return self.service.write(principal, request)

    def _search(self, principal: MemoryPrincipal, args: dict[str, Any]) -> Any:
        request = MemorySearchRequest(
            query=str(args["query"]),
            namespaces=tuple(str(value) for value in args.get("namespaces", [])),
            memory_classes=tuple(
                MemoryClass(str(value)) for value in args.get("memory_classes", [])
            ),
            valid_at=_dt(args.get("valid_at")) or datetime.now(timezone.utc),
            recorded_before=_dt(args.get("recorded_before")),
            include_superseded=bool(args.get("include_superseded", False)),
            include_archived=bool(args.get("include_archived", False)),
            min_confidence=float(args.get("min_confidence", 0.0)),
            limit=int(args.get("limit", 20)),
        )
        return self.service.search(principal, request)

    def _hydrate(self, principal: MemoryPrincipal, args: dict[str, Any]) -> Any:
        return self.service.hydrate(
            principal,
            HydrationRequest(
                task=str(args["task"]),
                namespaces=tuple(str(value) for value in args.get("namespaces", [])),
                entities=tuple(str(value) for value in args.get("entities", [])),
                topics=tuple(str(value) for value in args.get("topics", [])),
                memory_classes=tuple(
                    MemoryClass(str(value)) for value in args.get("memory_classes", [])
                ),
                token_budget=int(args.get("token_budget", 1_200)),
                max_records=int(args.get("max_records", 40)),
            ),
        )

    def _get(self, principal: MemoryPrincipal, args: dict[str, Any]) -> Any:
        record = self.service.get(principal, UUID(str(args["record_id"])))
        return {
            "found": record is not None,
            "record": record.model_dump(mode="json") if record else None,
        }

    def _conflicts(self, principal: MemoryPrincipal, args: dict[str, Any]) -> Any:
        return self.service.conflicts(principal, str(args["namespace"]))

    def _phase_lock(self, principal: MemoryPrincipal, args: dict[str, Any]) -> Any:
        return self.service.phase_lock(
            principal,
            PhaseLockRequest(
                namespace=str(args["namespace"]),
                task_signature=str(args["task_signature"]),
                ttl_seconds=int(args.get("ttl_seconds", 1_800)),
            ),
        )

    def _verify_phase_lock(
        self, principal: MemoryPrincipal, args: dict[str, Any]
    ) -> Any:
        return self.service.verify_phase_lock(
            principal,
            str(args["namespace"]),
            str(args["task_signature"]),
        )

    def _lineage(self, principal: MemoryPrincipal, args: dict[str, Any]) -> Any:
        return self.service.lineage(
            principal,
            str(args["namespace"]),
            UUID(str(args["record_id"])),
        )

    def _retention(self, principal: MemoryPrincipal, args: dict[str, Any]) -> Any:
        return self.service.apply_retention(
            principal,
            str(args["namespace"]),
            apply=bool(args.get("apply", False)),
        )

    def _delete(self, principal: MemoryPrincipal, args: dict[str, Any]) -> Any:
        return self.service.delete(
            principal,
            DeletionRequest(
                record_id=UUID(str(args["record_id"])),
                reason=str(args["reason"]),
                verification_reference=str(args["verification_reference"]),
                dry_run=bool(args.get("dry_run", False)),
            ),
        )

    def _record_namespace(self, principal: MemoryPrincipal, record_id: UUID) -> str:
        record = self.service.get(principal, record_id)
        if record is None:
            raise ValueError(f"record not found: {record_id}")
        return record.namespace

    def _promote(self, principal: MemoryPrincipal, args: dict[str, Any]) -> Any:
        return self.service.promote(
            principal,
            PromotionRequest(
                record_id=UUID(str(args["record_id"])),
                target_class=MemoryClass(str(args["target_class"])),
                reason=str(args["reason"]),
                explicit_confirmation=bool(args.get("explicit_confirmation", False)),
                governance_approval=bool(args.get("governance_approval", False)),
                test_success_count=int(args.get("test_success_count", 0)),
                supporting_record_ids=tuple(
                    UUID(str(value)) for value in args.get("supporting_record_ids", [])
                ),
                consent=_consent_from_payload(
                    args.get("consent"),
                    namespace=self._record_namespace(
                        principal, UUID(str(args["record_id"]))
                    ),
                    memory_class=MemoryClass(str(args["target_class"])),
                    principal=principal,
                ),
            ),
        )

    def _bootstrap(self, principal: MemoryPrincipal, args: dict[str, Any]) -> Any:
        if not principal.is_admin:
            raise AuthorizationError(
                "memory.bootstrap requires administrator authority"
            )
        receipts = RepositoryBootstrapper(self.service).bootstrap(
            principal,
            Path(str(args.get("repo_path", "."))),
            namespace=str(args["namespace"]),
            dry_run=bool(args.get("dry_run", False)),
        )
        return {
            "receipt_count": len(receipts),
            "receipts": [item.model_dump(mode="json") for item in receipts],
        }

    def _distill(self, principal: MemoryPrincipal, args: dict[str, Any]) -> Any:
        if not principal.is_admin:
            raise AuthorizationError("memory.distill requires administrator authority")
        return SourceDistiller(self.service).distill_path(
            principal,
            Path(str(args["path"])),
            namespace=str(args["namespace"]),
            repository=str(args["repository"]) if args.get("repository") else None,
            dry_run=bool(args.get("dry_run", False)),
        )

    def _synthesize_procedures(
        self, principal: MemoryPrincipal, args: dict[str, Any]
    ) -> Any:
        namespace = str(args["namespace"])
        self.service.namespace_policy.require(
            principal, AuthorizationAction.PROMOTE, namespace
        )
        synthesizer = PatternProceduralSynthesizer(
            self.service.store,
            minimum_support=int(args.get("minimum_support", 3)),
        )
        return ProceduralSynthesisWorker(self.service, synthesizer).run(
            principal,
            namespace=namespace,
            source_record_ids=tuple(
                UUID(str(value)) for value in args["source_record_ids"]
            ),
            dry_run=bool(args.get("dry_run", False)),
        )

    def _health(self, _principal: MemoryPrincipal, _args: dict[str, Any]) -> Any:
        return self.service.health()
