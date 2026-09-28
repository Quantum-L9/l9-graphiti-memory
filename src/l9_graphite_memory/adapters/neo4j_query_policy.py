# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/adapters/neo4j_query_policy.py
#   layer: adapter
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Static Cypher template registry and mutation guard for graph intelligence.

Graphiti is the exclusive semantic graph-model writer (ADR-085). The
graph-intelligence adapter therefore never composes Cypher at run time and
never accepts query text from a caller: every statement it can execute is a
named, module-level constant registered here, and registration refuses any
template that could persist a mutation. Relationship types, labels, and other
request values reach the database only as bound parameters.

The guard is lexical and deliberately conservative. It is backed at run time
by read-access sessions (the server rejects writes in a read transaction with
``Neo.ClientError.Statement.AccessMode``) and, in deployment, by a separate
least-privilege credential.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from l9_graphite_memory.errors import GraphQueryPolicyViolation


class TemplateKind(str, Enum):
    READ = "read"
    GDS_CATALOG = "gds_catalog"
    GDS_STREAM = "gds_stream"


# Persistent-mutation and escape-hatch constructs. Word boundaries keep
# property names such as ``created_at`` or ``offset`` from matching.
_FORBIDDEN: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("CREATE", re.compile(r"\bCREATE\b", re.IGNORECASE)),
    ("MERGE", re.compile(r"\bMERGE\b", re.IGNORECASE)),
    ("SET", re.compile(r"\bSET\b", re.IGNORECASE)),
    ("DELETE", re.compile(r"\bDELETE\b", re.IGNORECASE)),
    ("REMOVE", re.compile(r"\bREMOVE\b", re.IGNORECASE)),
    ("FOREACH", re.compile(r"\bFOREACH\b", re.IGNORECASE)),
    ("LOAD CSV", re.compile(r"\bLOAD\s+CSV\b", re.IGNORECASE)),
    ("DROP INDEX/CONSTRAINT", re.compile(r"\bDROP\s+(INDEX|CONSTRAINT)\b", re.IGNORECASE)),
    ("CALL IN TRANSACTIONS", re.compile(r"\bIN\s+TRANSACTIONS\b", re.IGNORECASE)),
    ("GDS write mode", re.compile(r"\.write\b", re.IGNORECASE)),
    ("GDS mutate mode", re.compile(r"\.mutate\b", re.IGNORECASE)),
    ("GDS export", re.compile(r"\bgds\.graph\.export\b", re.IGNORECASE)),
    (
        "GDS write-back",
        re.compile(r"\bgds\.graph\.(nodeProperties|relationship)\.write\b", re.IGNORECASE),
    ),
    ("APOC", re.compile(r"\bapoc\.", re.IGNORECASE)),
    ("dbms procedure", re.compile(r"\bdbms\.(?!components\b)", re.IGNORECASE)),
    ("db mutation procedure", re.compile(r"\bdb\.(create|index\.fulltext\.create)", re.IGNORECASE)),
)
# A template names parameters with ``$name``; string formatting markers mean
# the text was meant to be composed at run time, which is forbidden.
_COMPOSITION_MARKERS = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}|%\(|%s")


@dataclass(frozen=True)
class QueryTemplate:
    name: str
    kind: TemplateKind
    cypher: str

    def __post_init__(self) -> None:
        audit_cypher_template(self.name, self.cypher, self.kind)


def audit_cypher_template(name: str, cypher: str, kind: TemplateKind) -> None:
    """Refuse a template that could mutate persistent graph state."""

    if not re.fullmatch(r"[a-z][a-z0-9_]*_v[0-9]+", name):
        raise GraphQueryPolicyViolation(f"template name {name!r} must be snake_case with _vN")
    if not cypher.strip():
        raise GraphQueryPolicyViolation(f"template {name} is empty")
    for label, pattern in _FORBIDDEN:
        if pattern.search(cypher):
            raise GraphQueryPolicyViolation(f"template {name} contains forbidden {label}")
    if _COMPOSITION_MARKERS.search(cypher):
        raise GraphQueryPolicyViolation(f"template {name} contains run-time composition markers")
    if (
        kind is not TemplateKind.GDS_CATALOG
        and re.search(r"\bgds\.graph\.", cypher)
        and not re.search(r"\bgds\.graph\.list\b", cypher)
    ):
        raise GraphQueryPolicyViolation(
            f"template {name} touches the GDS catalog but is not a catalog template"
        )


class QueryRegistry:
    """Immutable name -> template map. There is no way to run text by value."""

    def __init__(self, templates: tuple[QueryTemplate, ...]) -> None:
        by_name: dict[str, QueryTemplate] = {}
        for template in templates:
            if template.name in by_name:
                raise GraphQueryPolicyViolation(f"duplicate template {template.name}")
            by_name[template.name] = template
        self._templates: Mapping[str, QueryTemplate] = MappingProxyType(by_name)

    def get(self, name: str) -> QueryTemplate:
        try:
            return self._templates[name]
        except KeyError as exc:
            raise GraphQueryPolicyViolation(f"unregistered query template {name!r}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._templates))

    def templates(self) -> tuple[QueryTemplate, ...]:
        return tuple(self._templates[name] for name in self.names())
