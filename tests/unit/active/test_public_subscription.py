# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/active/test_public_subscription.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from l9_graphite_memory.active import AgentScope, AgentSubscription


def test_public_subscription_contract():
    subscription = AgentSubscription(AgentScope("test-deployment"))
    assert subscription.scope.deployment_id == "test-deployment"
