from l9_graphite_memory.active import AgentScope, AgentSubscription


def test_public_subscription_contract():
    subscription = AgentSubscription(AgentScope("test-deployment"))
    assert subscription.scope.deployment_id == "test-deployment"
