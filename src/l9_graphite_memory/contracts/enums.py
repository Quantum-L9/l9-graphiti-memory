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
    # Least-privilege authority for scheduled canonical-memory maintenance.
    # It permits consolidating, superseding, and archiving records that are
    # already canonical. It does not permit ingestion, deletion, or
    # administration (ADR-075).
    MAINTAIN = "maintain"
    ADMIN = "admin"


class MaintenanceOperation(str, Enum):
    """Bounded set of transformations scheduled maintenance may perform."""

    DEDUPE = "dedupe"
    REFINE = "refine"
    SUPERSEDE = "supersede"
    ARCHIVE = "archive"
    RECONCILE = "reconcile"
    # Review records admission held for a safety or PII signal and release
    # the ones a reviewer clears; escalate the serious ones for a person
    # (ADR-080).
    REVIEW_QUARANTINE = "review_quarantine"


class QuarantineVerdict(str, Enum):
    """Outcome of one automated review of a quarantined record (ADR-080)."""

    #: The record is safe to serve; release it to ACTIVE under MAINTAIN.
    RELEASE = "release"
    #: Not enough confidence either way; leave it quarantined and review again.
    HOLD = "hold"
    #: A serious finding a person has to decide; leave it quarantined and report it.
    ESCALATE = "escalate"


class MaintenanceStatus(str, Enum):
    PLANNED = "planned"
    APPLIED = "applied"
    FAILED = "failed"


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
