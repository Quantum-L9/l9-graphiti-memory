# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ingestion/__init__.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Canonical ingestion adapters."""

from .document import DocumentIngestor, IngestedChunk
from .profiles import ProfileIngestor
from .publication_identity import (
    PublicationIdentityError,
    verify_publication_identity,
)
from .repository import RepositoryBootstrapper
from .topology_publication import (
    TopologyCandidateResult,
    TopologyPlanError,
    TopologyPublicationBatchReceipt,
    TopologyPublicationPlanModel,
    VerifiedBundle,
    execute_topology_publication,
    load_publication_plan,
    load_verified_bundle,
    validate_publication_inputs,
    validate_topology_binding,
)

__all__ = [
    "DocumentIngestor",
    "IngestedChunk",
    "ProfileIngestor",
    "PublicationIdentityError",
    "RepositoryBootstrapper",
    "TopologyCandidateResult",
    "TopologyPlanError",
    "TopologyPublicationBatchReceipt",
    "TopologyPublicationPlanModel",
    "VerifiedBundle",
    "execute_topology_publication",
    "load_publication_plan",
    "load_verified_bundle",
    "validate_publication_inputs",
    "validate_topology_binding",
    "verify_publication_identity",
]
