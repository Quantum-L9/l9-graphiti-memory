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
from .repository import RepositoryBootstrapper

__all__ = [
    "DocumentIngestor",
    "IngestedChunk",
    "ProfileIngestor",
    "RepositoryBootstrapper",
]
