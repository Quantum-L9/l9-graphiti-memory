# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/graph/algorithm_policy.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Algorithm maturity gates for graph intelligence (ADR-086).

Graph algorithms produce advisory projection intelligence and never create
authority. Each operation has a closed set of admissible algorithms, each with
a declared maturity. ``production`` runs when the capability is configured;
``beta`` and ``alpha`` run only when the deployment's maturity ceiling admits
them, and link prediction additionally requires its feature flag. A requested
algorithm outside its operation's set is rejected before any provider call;
there is no silent substitution (GI-032).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from l9_graphite_memory.errors import GraphQueryPolicyViolation

from .contracts import GraphAlgorithmIdentity, GraphOperation


class AlgorithmMaturity(str, Enum):
    NATIVE = "native"
    PRODUCTION = "production"
    BETA = "beta"
    ALPHA = "alpha"


_MATURITY_RANK = {
    AlgorithmMaturity.NATIVE: 0,
    AlgorithmMaturity.PRODUCTION: 0,
    AlgorithmMaturity.BETA: 1,
    AlgorithmMaturity.ALPHA: 2,
}


@dataclass(frozen=True)
class GraphAlgorithm:
    id: str
    operation: GraphOperation
    maturity: AlgorithmMaturity
    requires_analytics: bool
    default: bool = False


ALGORITHMS: tuple[GraphAlgorithm, ...] = (
    # Candidate retrieval through the existing Graphiti projection strategies.
    GraphAlgorithm(
        "graphiti-graph-search", GraphOperation.SEARCH, AlgorithmMaturity.NATIVE, False, True
    ),
    GraphAlgorithm(
        "graphiti-semantic-search",
        GraphOperation.SEMANTIC_SEARCH,
        AlgorithmMaturity.NATIVE,
        False,
        True,
    ),
    GraphAlgorithm(
        "bounded-traversal", GraphOperation.TRAVERSE, AlgorithmMaturity.NATIVE, False, True
    ),
    GraphAlgorithm(
        "bounded-neighborhood", GraphOperation.NEIGHBORHOOD, AlgorithmMaturity.NATIVE, False, True
    ),
    GraphAlgorithm("shortest-path", GraphOperation.PATH, AlgorithmMaturity.NATIVE, False, True),
    GraphAlgorithm("louvain", GraphOperation.COMMUNITY, AlgorithmMaturity.PRODUCTION, True, True),
    GraphAlgorithm("leiden", GraphOperation.COMMUNITY, AlgorithmMaturity.PRODUCTION, True),
    GraphAlgorithm("pagerank", GraphOperation.CENTRALITY, AlgorithmMaturity.PRODUCTION, True, True),
    GraphAlgorithm("degree", GraphOperation.CENTRALITY, AlgorithmMaturity.PRODUCTION, True),
    GraphAlgorithm("betweenness", GraphOperation.CENTRALITY, AlgorithmMaturity.PRODUCTION, True),
    GraphAlgorithm(
        "fastrp", GraphOperation.STRUCTURAL_EMBEDDING, AlgorithmMaturity.PRODUCTION, True, True
    ),
    GraphAlgorithm(
        "fastrp-cosine",
        GraphOperation.STRUCTURAL_SIMILARITY,
        AlgorithmMaturity.PRODUCTION,
        True,
        True,
    ),
    GraphAlgorithm(
        "adamic-adar", GraphOperation.LINK_PREDICTION, AlgorithmMaturity.ALPHA, True, True
    ),
    GraphAlgorithm(
        "common-neighbors", GraphOperation.LINK_PREDICTION, AlgorithmMaturity.ALPHA, True
    ),
    GraphAlgorithm(
        "resource-allocation", GraphOperation.LINK_PREDICTION, AlgorithmMaturity.ALPHA, True
    ),
)
_BY_ID = {algorithm.id: algorithm for algorithm in ALGORITHMS}


#: Deterministic V1 parameters: fixed seed, single-threaded GDS execution, and
#: a fixed FastRP dimension, so identical scopes give identical receipts.
FASTRP_EMBEDDING_DIMENSION = 64
RANDOM_SEED = 42


def algorithm_parameters(algorithm: GraphAlgorithm) -> dict[str, Any]:
    """Provider-neutral parameters bound into the algorithm config digest."""

    if algorithm.id in {"fastrp", "fastrp-cosine"}:
        return {"embedding_dimension": FASTRP_EMBEDDING_DIMENSION, "random_seed": RANDOM_SEED}
    if algorithm.id == "leiden":
        return {"random_seed": RANDOM_SEED}
    return {}


@dataclass(frozen=True)
class AlgorithmPolicy:
    """Deployment-level gates (ADR-086). Profiles narrow this, never widen it."""

    maturity_ceiling: AlgorithmMaturity = AlgorithmMaturity.PRODUCTION
    link_prediction_enabled: bool = False

    def resolve(self, operation: GraphOperation, requested: str | None) -> GraphAlgorithm:
        candidates = [algorithm for algorithm in ALGORITHMS if algorithm.operation is operation]
        if not candidates:
            raise GraphQueryPolicyViolation(f"{operation.value} has no graph algorithm")
        if requested is None:
            algorithm = next(a for a in candidates if a.default)
        else:
            found = _BY_ID.get(requested)
            if found is None or found.operation is not operation:
                raise GraphQueryPolicyViolation(
                    f"algorithm {requested!r} is not admissible for {operation.value}"
                )
            algorithm = found
        if operation is GraphOperation.LINK_PREDICTION and not self.link_prediction_enabled:
            raise GraphQueryPolicyViolation("link prediction is disabled for this deployment")
        if _MATURITY_RANK[algorithm.maturity] > _MATURITY_RANK[self.maturity_ceiling]:
            raise GraphQueryPolicyViolation(
                f"algorithm {algorithm.id} is {algorithm.maturity.value}; the deployment "
                f"admits at most {self.maturity_ceiling.value}"
            )
        return algorithm


def algorithm_identity(algorithm: GraphAlgorithm, config: dict[str, Any]) -> GraphAlgorithmIdentity:
    """Bind the algorithm id, maturity, and its exact configuration by digest."""

    material = json.dumps(
        {"algorithm": algorithm.id, "config": config}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return GraphAlgorithmIdentity(
        id=algorithm.id,
        maturity=algorithm.maturity.value,
        config_digest=hashlib.sha256(material).hexdigest(),
    )
