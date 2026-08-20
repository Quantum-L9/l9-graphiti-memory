# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/authz/policy.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Namespace policy with exact and glob-based grants."""

from __future__ import annotations

from fnmatch import fnmatchcase

from l9_graphite_memory.contracts import (
    AuthorizationAction,
    AuthorizationReceipt,
    MemoryPrincipal,
)
from l9_graphite_memory.errors import AuthorizationError


class NamespacePolicy:
    """Authorize a server-derived principal against a namespace."""

    def _patterns_for(
        self, principal: MemoryPrincipal, action: AuthorizationAction
    ) -> tuple[str, ...]:
        if action is AuthorizationAction.READ:
            return principal.read_namespaces
        if action is AuthorizationAction.WRITE:
            return principal.write_namespaces
        if action is AuthorizationAction.PROMOTE:
            return principal.promote_namespaces
        if action is AuthorizationAction.MAINTAIN:
            return principal.maintain_namespaces
        if action in {AuthorizationAction.ARCHIVE, AuthorizationAction.ADMIN}:
            return ("*",) if principal.is_admin else ()
        return ()

    @staticmethod
    def _matches(namespace: str, patterns: tuple[str, ...]) -> bool:
        return any(fnmatchcase(namespace, pattern) for pattern in patterns)

    def evaluate(
        self,
        principal: MemoryPrincipal,
        action: AuthorizationAction,
        namespace: str,
    ) -> AuthorizationReceipt:
        if principal.is_admin:
            return AuthorizationReceipt(
                principal_id=principal.principal_id,
                action=action,
                namespace=namespace,
                allowed=True,
                reasons=("principal is administrator",),
            )
        patterns = self._patterns_for(principal, action)
        allowed = self._matches(namespace, patterns)
        reason = (
            f"namespace matched {action.value} grant"
            if allowed
            else f"namespace did not match any {action.value} grant"
        )
        return AuthorizationReceipt(
            principal_id=principal.principal_id,
            action=action,
            namespace=namespace,
            allowed=allowed,
            reasons=(reason,),
        )

    def require(
        self,
        principal: MemoryPrincipal,
        action: AuthorizationAction,
        namespace: str,
    ) -> AuthorizationReceipt:
        receipt = self.evaluate(principal, action, namespace)
        if not receipt.allowed:
            raise AuthorizationError(
                f"principal {principal.principal_id!r} is not authorized to {action.value} {namespace!r}"
            )
        return receipt
