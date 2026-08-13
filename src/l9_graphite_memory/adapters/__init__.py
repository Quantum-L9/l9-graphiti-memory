# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/adapters/__init__.py
#   layer: adapter
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Concrete record stores and projections.

The canonical control plane is ``MemoryService``; the supported way to obtain a
store is :func:`build_store`, which returns a ``RecordStore`` bound to the
service. The concrete ``InMemoryRecordStore`` / ``SQLiteRecordStore`` classes are
intentionally left out of ``__all__`` so ``from ...adapters import *`` does not
advertise them as a public write surface (their canonical-mutation methods now
require the service-issued write capability regardless — see
``ports.service_capability`` and ADR-036). They remain importable from their
submodules for tests and store-contract conformance work.
"""

from .factory import build_projection, build_store
from .graphiti_projection import GraphitiProjection

# Concrete stores remain importable from this package for tests and store-contract
# conformance, but are intentionally kept out of ``__all__`` (redundant-alias
# re-export) so ``from ...adapters import *`` does not advertise them as a public
# write surface. Their canonical-mutation methods require the service-issued write
# capability regardless (ports.service_capability, ADR-036).
from .in_memory_store import InMemoryRecordStore as InMemoryRecordStore
from .null_projection import NullProjection
from .sqlite_store import SQLiteRecordStore as SQLiteRecordStore

__all__ = [
    "GraphitiProjection",
    "NullProjection",
    "build_projection",
    "build_store",
]
