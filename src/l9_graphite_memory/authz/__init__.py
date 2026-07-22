# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/authz/__init__.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Authentication and namespace authorization."""

from .authenticator import TokenAuthenticator, build_local_principal
from .policy import NamespacePolicy

__all__ = ["NamespacePolicy", "TokenAuthenticator", "build_local_principal"]
