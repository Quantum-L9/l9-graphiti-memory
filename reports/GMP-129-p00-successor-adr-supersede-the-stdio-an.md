# GMP-129

**Task:** P00 successor ADR: supersede the stdio and signed-agent parts of ADR-038, ADR-064, ADR-082, ADR-083, and ADR-098
**Tier:** RUNTIME

## TODOs

- T1: docs/adr/ADR-100-native-oauth-mcp-full-cutover.md REPLACE Record ADR-100 native OAuth MCP full cutover
- T2: docs/adr/README.md REPLACE Index ADR-100 and note partial supersession
- T3: docs/adr/ADR-038-sdk-mcp-cli-and-http-surface.md REPLACE Point ADR-038 stdio and signed-agent provisions at ADR-100
- T4: docs/adr/ADR-064-cursor-client-instantiation-and-proof-boundary.md REPLACE Point ADR-064 stdio client provisions at ADR-100
- T5: docs/adr/ADR-082-consumer-control-plane-transport-parity.md REPLACE Point ADR-082 signed-agent remote consumer provisions at ADR-100
- T6: docs/adr/ADR-083-server-side-local-authorization-and-one-class-vocabulary.md REPLACE Point ADR-083 HMAC and bearer door provisions at ADR-100
- T7: docs/adr/ADR-098-remote-mcp-transport-and-signed-agent-http-identity.md REPLACE Point ADR-098 signed-agent HTTP identity at ADR-100
- T8: tools/assurance/validate_adrs.py REPLACE Extend ADR ledger expectation to 100
- T9: tools/assurance/generate_validation_evidence.py REPLACE Re-pin ADR validation evidence to 100
- T10: tests/regression/test_adr_100_oauth_cutover.py REPLACE Assert supersession pointers
