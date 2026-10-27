# GMP-129

**Task:** P05 Graphiti provider error transport
**Tier:** RUNTIME

## TODOs

- proj-error: src/l9_graphite_memory/transport.py REPLACE Honor Graphiti isError, classify breaker faults, re-arm half-open, and refuse phantom projection links
- proj-error.2: src/l9_graphite_memory/circuit_breaker.py REPLACE Honor Graphiti isError, classify breaker faults, re-arm half-open, and refuse phantom projection links
- proj-error.3: src/l9_graphite_memory/adapters/graphiti_projection.py REPLACE Honor Graphiti isError, classify breaker faults, re-arm half-open, and refuse phantom projection links
- proj-error.4: tests/unit/test_graphiti_error_transport.py REPLACE Honor Graphiti isError, classify breaker faults, re-arm half-open, and refuse phantom projection links
- proj-error.5: tests/integration/test_graphiti_http_projection_loop.py REPLACE Honor Graphiti isError, classify breaker faults, re-arm half-open, and refuse phantom projection links
- proj-error.6: tools/assurance/generate_validation_evidence.py REPLACE Honor Graphiti isError, classify breaker faults, re-arm half-open, and refuse phantom projection links
