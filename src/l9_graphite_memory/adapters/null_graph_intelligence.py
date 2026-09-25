# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/adapters/null_graph_intelligence.py
#   layer: adapter
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Explicit no-intelligence adapter used when graph intelligence is disabled."""

from __future__ import annotations

from l9_graphite_memory.graph.ports import (
    GraphBackendHealth,
    GraphCapability,
    UnservedOperations,
)


class NullGraphIntelligence(UnservedOperations):
    """Serves no structural capability and says so; never fakes zero results."""

    name = "none"

    def capabilities(self) -> tuple[GraphCapability, ...]:
        return ()

    def health(self) -> GraphBackendHealth:
        return GraphBackendHealth(
            name=self.name,
            enabled=False,
            healthy=True,
            detail="graph intelligence disabled",
        )

    def close(self) -> None:
        return None
