# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/graph/scope.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""GraphScopeKey v1: tenant-safe graph projection group identity.

Canonical memory identity is ``tenant_id + namespace + record_id``. A graph
provider group that is keyed on the namespace alone lets two tenants that use
the same namespace string share one provider group, and graph traversal or
analytics widens that leak from isolated hits to whole neighborhoods. Every
provider-side group identity is therefore derived from both scope components,
server-side, through this one function (ADR-084).

The derivation is::

    material = canonical_json({"namespace": namespace, "tenant_id": tenant_id})
    digest   = sha256(material encoded as UTF-8)
    group_id = "l9g-v1-" + digest_hex

The output is deterministic, collision resistant, does not expose the raw
tenant identity, and is restricted to ``[a-z0-9-]`` because Graphiti v0.30.2
rejects any group id outside ``^[a-zA-Z0-9_-]+$`` on both episode writes and
search. Callers never supply a final group id: the only inputs are the
server-derived tenant and a namespace the principal is already authorized for.
"""

from __future__ import annotations

import hashlib
import json
import re

GRAPH_SCOPE_SCHEME = "l9g-v1"
GRAPH_SCOPE_SCHEME_VERSION = 1
_GROUP_ID_PREFIX = f"{GRAPH_SCOPE_SCHEME}-"
_GROUP_ID_PATTERN = re.compile(r"^l9g-v1-[0-9a-f]{64}$")


def _require_component(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"graph scope {name} must be a non-empty string")
    return value


def graph_scope_material(tenant_id: str, namespace: str) -> bytes:
    """Return the canonical, sorted, compact UTF-8 JSON scope material."""

    tenant = _require_component("tenant_id", tenant_id)
    ns = _require_component("namespace", namespace)
    return json.dumps(
        {"namespace": ns, "tenant_id": tenant},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def graph_scope_digest(tenant_id: str, namespace: str) -> str:
    """Return the SHA-256 hex digest binding one tenant to one namespace."""

    return hashlib.sha256(graph_scope_material(tenant_id, namespace)).hexdigest()


def graph_group_id(tenant_id: str, namespace: str) -> str:
    """Return the provider group id for one tenant/namespace scope."""

    return _GROUP_ID_PREFIX + graph_scope_digest(tenant_id, namespace)


def graph_group_ids(tenant_id: str, namespaces: tuple[str, ...]) -> tuple[str, ...]:
    """Return the exact derived group ids for authorized namespaces, in order.

    Duplicate namespaces collapse; no wildcard or prefix group is ever
    produced, so a multi-namespace read spans exactly the authorized set.
    """

    seen: dict[str, None] = {}
    for namespace in namespaces:
        seen.setdefault(graph_group_id(tenant_id, namespace), None)
    return tuple(seen)


def is_graph_group_id(value: str) -> bool:
    """Return whether ``value`` has the GraphScopeKey v1 group-id shape."""

    return isinstance(value, str) and bool(_GROUP_ID_PATTERN.fullmatch(value))
