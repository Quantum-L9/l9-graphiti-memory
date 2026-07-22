# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/enums.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Canonical enums shared by every adapter and service."""

from __future__ import annotations

from enum import Enum


class MemoryClass(str, Enum):
    IDENTITY = "identity"
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    DECISION = "decision"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    OBSERVATION = "observation"
    INSIGHT = "insight"
    META = "meta"


class QueryPattern(str, Enum):
    ENTITY_LOOKUP = "entity_lookup"
    REASONING_LINEAGE = "reasoning_lineage"
    TEMPORAL = "temporal"
    IDENTITY = "identity"
    EXPLORATORY = "exploratory"
    FACTUAL = "factual"
    DEFAULT = "default"


class MemoryState(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"
    DELETION_PENDING = "deletion_pending"
    DELETED = "deleted"


class EvidenceKind(str, Enum):
    EXPLICIT = "explicit"
    SOURCE_EXCERPT = "source_excerpt"
    TEST = "test"
    OBSERVATION = "observation"
    INFERENCE = "inference"
    AGGREGATION = "aggregation"
    GOVERNANCE_APPROVAL = "governance_approval"


class ConfidenceMethod(str, Enum):
    EXPLICIT = "explicit"
    EXTRACTED = "extracted"
    INFERRED = "inferred"
    AGGREGATED = "aggregated"
    CALIBRATED = "calibrated"


class WriteStatus(str, Enum):
    ADMITTED = "admitted"
    DUPLICATE = "duplicate"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class OperationStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class AuthorizationAction(str, Enum):
    READ = "read"
    WRITE = "write"
    PROMOTE = "promote"
    ARCHIVE = "archive"
    ADMIN = "admin"


class OutboxStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    RETRY = "retry"
    DEAD = "dead"


class DeletionStatus(str, Enum):
    DRY_RUN = "dry_run"
    PENDING_PROJECTION = "pending_projection"
    COMPLETE = "complete"
