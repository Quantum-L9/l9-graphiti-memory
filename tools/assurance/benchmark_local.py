#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/benchmark_local.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Deterministic local latency benchmark for the canonical in-memory control path."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass

from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
from l9_graphite_memory.authz import NamespacePolicy
from l9_graphite_memory.contracts import (
    HydrationRequest,
    MemoryPrincipal,
    MemorySearchRequest,
    MemoryWriteRequest,
    Provenance,
)
from l9_graphite_memory.services import MemoryService


@dataclass(frozen=True)
class Metric:
    samples: int
    p50_ms: float
    p95_ms: float
    max_ms: float
    threshold_p95_ms: float
    passed: bool


def _metric(values_ns: list[int], threshold_ms: float) -> Metric:
    values_ms = sorted(value / 1_000_000 for value in values_ns)
    p50 = statistics.median(values_ms)
    p95_index = max(0, min(len(values_ms) - 1, round(0.95 * (len(values_ms) - 1))))
    p95 = values_ms[p95_index]
    return Metric(
        samples=len(values_ms),
        p50_ms=round(p50, 4),
        p95_ms=round(p95, 4),
        max_ms=round(max(values_ms), 4),
        threshold_p95_ms=threshold_ms,
        passed=p95 <= threshold_ms,
    )


def _timed(callable_):
    started = time.perf_counter_ns()
    result = callable_()
    return time.perf_counter_ns() - started, result


def run(iterations: int) -> dict[str, object]:
    namespace = "benchmark"
    principal = MemoryPrincipal(
        principal_id="benchmark",
        tenant_id="benchmark",
        agent_id="benchmark",
        read_namespaces=(namespace,),
        write_namespaces=(namespace,),
        promote_namespaces=(namespace,),
        is_admin=True,
        auth_method="benchmark",
    )
    service = MemoryService(
        InMemoryRecordStore(), NullProjection(), namespace_policy=NamespacePolicy()
    )
    service.initialize()
    write_times: list[int] = []
    search_times: list[int] = []
    hydrate_times: list[int] = []
    for index in range(iterations):
        elapsed, receipt = _timed(
            lambda index=index: service.write(
                principal,
                MemoryWriteRequest(
                    namespace=namespace,
                    content=f"benchmark memory record {index} about deterministic retrieval",
                    provenance=Provenance(source="local-benchmark", source_trust=1.0),
                    idempotency_key=f"benchmark:{index}",
                ),
            )
        )
        assert receipt.record_id is not None
        write_times.append(elapsed)
    for _ in range(iterations):
        elapsed, receipt = _timed(
            lambda: service.search(
                principal,
                MemorySearchRequest(
                    query="deterministic retrieval", namespaces=(namespace,), limit=20
                ),
            )
        )
        assert receipt.status.value == "complete"
        search_times.append(elapsed)
    for _ in range(max(10, iterations // 4)):
        elapsed, result = _timed(
            lambda: service.hydrate(
                principal,
                HydrationRequest(
                    task="use deterministic retrieval context",
                    namespaces=(namespace,),
                    token_budget=1200,
                ),
            )
        )
        assert result.status.value == "complete"
        hydrate_times.append(elapsed)
    metrics = {
        "write": _metric(write_times, 100.0),
        "search": _metric(search_times, 250.0),
        "hydrate": _metric(hydrate_times, 500.0),
    }
    return {
        "status": "PASS" if all(metric.passed for metric in metrics.values()) else "FAIL",
        "scope": "in-memory canonical path only; external provider latency is not measured",
        "iterations": iterations,
        "metrics": {name: asdict(metric) for name, metric in metrics.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=40)
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Accepted for assurance-tool interface compatibility",
    )
    args = parser.parse_args()
    if args.iterations < 10:
        parser.error("iterations must be at least 10")
    report = run(args.iterations)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
