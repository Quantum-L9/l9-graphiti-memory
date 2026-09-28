# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/observability/graph_metrics.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Process-local graph-intelligence metrics and structured operation logs (ADR-089).

Metric names follow the campaign observability contract so a Prometheus (or
other) exporter can publish them unchanged. The registry holds numbers only:
it never records memory content, credentials, raw vectors, or query text, and
the structured log line carries operation identity, scope digest, algorithm,
counts, timing, result digest, and error classes only.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from typing import Any

from .logging import get_logger

_LOG = get_logger("l9_graphite_memory.graph")

Labels = tuple[tuple[str, str], ...]


def _labels(**values: str) -> Labels:
    return tuple(sorted(values.items()))


class GraphMetrics:
    """Thread-safe counters, gauges, and summaries for graph intelligence."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, Labels], float] = {}
        self._gauges: dict[tuple[str, Labels], float] = {}
        self._summaries: dict[tuple[str, Labels], dict[str, float]] = {}

    def inc(self, name: str, amount: float = 1.0, **labels: str) -> None:
        key = (name, _labels(**labels))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + amount

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            self._gauges[(name, _labels(**labels))] = value

    def observe(self, name: str, value: float, **labels: str) -> None:
        key = (name, _labels(**labels))
        with self._lock:
            summary = self._summaries.setdefault(key, {"count": 0.0, "sum": 0.0, "max": 0.0})
            summary["count"] += 1
            summary["sum"] += value
            summary["max"] = max(summary["max"], value)

    def value(self, name: str, **labels: str) -> float:
        key = (name, _labels(**labels))
        with self._lock:
            if key in self._counters:
                return self._counters[key]
            return self._gauges.get(key, 0.0)

    def summary(self, name: str, **labels: str) -> dict[str, float]:
        with self._lock:
            return dict(self._summaries.get((name, _labels(**labels)), {}))

    def snapshot(self) -> dict[str, Any]:
        def render(items: Iterable[tuple[tuple[str, Labels], Any]]) -> list[dict[str, Any]]:
            return [
                {"name": name, "labels": dict(labels), "value": value}
                for (name, labels), value in sorted(items, key=lambda item: item[0])
            ]

        with self._lock:
            return {
                "counters": render(self._counters.items()),
                "gauges": render(self._gauges.items()),
                "summaries": render(((key, dict(value)) for key, value in self._summaries.items())),
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._summaries.clear()

    # -- graph-intelligence vocabulary ----------------------------------------

    def record_operation(
        self,
        *,
        operation: str,
        status: str,
        latency_ms: float,
        node_count: int,
        edge_count: int,
        unsupported_reasons: Iterable[str],
        failure_classes: Iterable[str],
        provider: str,
        scope_digest: str,
        algorithm: str | None,
        result_digest: str,
    ) -> None:
        failures = list(failure_classes)
        self.inc("memory_graph_query_total", operation=operation, status=status)
        self.observe("memory_graph_query_latency_ms", latency_ms, operation=operation)
        self.observe("memory_graph_result_nodes", node_count, operation=operation)
        self.observe("memory_graph_result_edges", edge_count, operation=operation)
        for reason in unsupported_reasons:
            self.inc("memory_graph_rehydration_drop_total", reason=reason)
        if status == "PARTIAL":
            self.inc("memory_graph_partial_receipt_total", operation=operation)
        for failure in failures:
            if failure.startswith("provider_error"):
                self.inc(
                    "memory_graph_provider_failure_total", provider=provider, operation=operation
                )
            if failure == "gds_catalog_cleanup_failed":
                self.inc("memory_graph_gds_cleanup_failure_total")
        _LOG.info(
            "graph_intelligence_operation",
            extra={
                "operation": operation,
                "status": status,
                "scope_digest": scope_digest,
                "algorithm": algorithm,
                "nodes": node_count,
                "edges": edge_count,
                "latency_ms": round(latency_ms, 3),
                "result_digest": result_digest,
                "failure_classes": failures,
            },
        )

    def record_scope_denied(self, operation: str) -> None:
        self.inc("memory_graph_scope_denied_total")
        _LOG.info("graph_intelligence_scope_denied", extra={"operation": operation})


#: Default process-wide registry used by the runtime composition.
GRAPH_METRICS = GraphMetrics()
