# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/schema/__init__.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from . import upcasters as _upcasters  # Register built-in schema migrations.

"""Schema registry and read-time upcasting."""

from .registry import SchemaRegistry, schema_registry

__all__ = ["SchemaRegistry", "schema_registry"]
