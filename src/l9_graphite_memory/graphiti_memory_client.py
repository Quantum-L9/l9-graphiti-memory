# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/graphiti_memory_client.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Compatibility module for the v1 Graphiti CLI import path."""

from __future__ import annotations

from .cli import main

__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
