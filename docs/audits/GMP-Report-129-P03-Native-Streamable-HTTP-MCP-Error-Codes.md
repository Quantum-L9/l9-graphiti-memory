# GMP-129

**Task:** P03 native Streamable HTTP MCP error codes isError and bounded offload; P04 evidence-bound identity fail-closed
**Tier:** RUNTIME

> **Amended 2026-11-02 (integration remediation):** T4 and the Graphiti isError case of T8 were withdrawn from this PR. PR #105 owns the Graphiti error contract in `transport.py`; keeping both caused a textual conflict and duplicate ownership. The remote-client isError check (T3/T7) is unchanged. Unknown tools now resolve before principal checks, and an internal `KeyError` is no longer reported as a missing argument (`tests/unit/test_mcp_tool_key_error_mapping.py`).

## TODOs

- T1: src/l9_graphite_memory/server.py REPLACE Distinguish missing tool arguments from unknown tools
- T2: src/l9_graphite_memory/mcp_tools.py REPLACE Refuse caller-supplied identity and OAuth-admin grants on MCP tools
- T3: src/l9_graphite_memory/remote_client.py REPLACE Treat MCP isError as a remote client failure
- T4: src/l9_graphite_memory/transport.py REPLACE Treat Graphiti isError as a projection failure
- T5: src/l9_graphite_memory/contracts/identity.py REPLACE Add hosted identity coordinates that fail closed
- T6: tests/integration/test_remote_mcp_http.py REPLACE Cover missing-argument JSON-RPC code
- T7: tests/unit/test_remote_client.py REPLACE Cover remote client isError
- T8: tests/unit/test_http_mcp_transport_wire.py REPLACE Cover Graphiti isError and bounded tool offload
- T9: tests/unit/test_hosted_identity_coordinates.py REPLACE Cover hosted identity fail-closed rules
- T10: tests/unit/test_mcp_tool_offload.py REPLACE Cover tool offload does not stall the loop
