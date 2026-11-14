# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/public_probe.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 3.0.0
#   updated: 2026-11-14

"""The bodies of the unauthenticated ``/healthz`` and ``/readyz`` probes.

The probes stay unauthenticated: the deployment platform, the container
HEALTHCHECK and the runbook call them without a credential. Their bodies are
therefore public, and are built here by **allowlist**, never by dumping the
internal report and removing what looks sensitive. Every component reduces to
its name, its health/readiness booleans and, where one exists, a stable
machine reason code. No count (records, backlog, catalog sizes), no path, no
URL and nothing derived from an exception's text reaches them, so a field a
future adapter adds to its health dictionary cannot reach a public body
without a change to this module (U-011).

The full report remains available to an authenticated caller through the
``memory.health`` MCP tool; the detail of a failure goes to the server log
through :mod:`l9_graphite_memory.redaction`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from l9_graphite_memory.contracts.receipts import HealthReport, ReadinessFamily, ReadinessReport

# Booleans a component may publish. Anything else is dropped.
_PUBLIC_FLAGS = ("configured", "enabled", "selected", "required", "healthy", "ready")
# A reason code is a short lowercase identifier: it cannot carry text.
_REASON_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
# The one family detail a consumer reads (the carrier proof): a boolean.
_PUBLIC_FAMILY_DETAIL = ("shared_store",)


def _name(value: object) -> str | None:
    return value if isinstance(value, str) and _REASON_CODE.fullmatch(value) else None


def public_component(component: Mapping[str, Any]) -> dict[str, Any]:
    """Name, health booleans and a reason code; nothing else."""

    body: dict[str, Any] = {}
    name = _name(component.get("name"))
    if name is not None:
        body["name"] = name
    for flag in _PUBLIC_FLAGS:
        value = component.get(flag)
        if isinstance(value, bool):
            body[flag] = value
    reason = component.get("reason")
    if isinstance(reason, str) and _REASON_CODE.fullmatch(reason):
        body["reason"] = reason
    return body


def _public_family(family: ReadinessFamily) -> dict[str, Any]:
    detail = {
        key: family.detail[key]
        for key in _PUBLIC_FAMILY_DETAIL
        if isinstance(family.detail.get(key), bool)
    }
    return {
        "name": family.name,
        "selected": family.selected,
        "required": family.required,
        "healthy": family.healthy,
        "ready": family.ready,
        # Family reasons are composed from the family name and a fixed phrase
        # (runtime._family); they carry no adapter text.
        "reasons": list(family.reasons),
        "detail": detail,
    }


def public_health(report: HealthReport) -> dict[str, Any]:
    """The public ``/healthz`` body."""

    return {
        "status": report.status.value,
        "package_version": report.package_version,
        "schema_version": report.schema_version,
        "contract_version": report.contract_version,
        "store": public_component(report.store),
        "projection": public_component(report.projection),
        "gate": public_component(report.gate),
        # Fixed phrases composed by MemoryService.health; no adapter text.
        "degraded_reasons": list(report.degraded_reasons),
        "checked_at": report.checked_at.isoformat(),
    }


def public_readiness(
    health: HealthReport, readiness: ReadinessReport, *, graph_present: bool
) -> dict[str, Any]:
    """The public ``/readyz`` body: the public health body plus readiness."""

    body = public_health(health)
    if graph_present:
        graph = readiness.family("graph")
        body["graph"] = {
            "enabled": graph.selected,
            "healthy": graph.healthy,
            "required": graph.required,
            "ready": graph.ready,
        }
    body["active_memory"] = {
        "store": _public_family(readiness.family("active_store")),
        "bus": _public_family(readiness.family("awareness_bus")),
    }
    body["readiness"] = {
        "status": readiness.status.value,
        "ready": readiness.ready,
        "full_capability": readiness.full_capability,
        "package_version": readiness.package_version,
        "schema_version": readiness.schema_version,
        "contract_version": readiness.contract_version,
        "families": [_public_family(family) for family in readiness.families],
        "degraded_reasons": list(readiness.degraded_reasons),
        "checked_at": readiness.checked_at.isoformat(),
    }
    return body
