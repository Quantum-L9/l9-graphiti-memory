# GMP-129

**Task:** P01 sensitive admission: PII normalization, explicit evidence, consent time
**Tier:** RUNTIME

## TODOs

- data-01: src/l9_graphite_memory/admission/normalization.py REPLACE Stop bare epochs and nine-digit ids from collapsing to PII placeholders
- data-01.2: src/l9_graphite_memory/admission/engine.py REPLACE Stop bare epochs and nine-digit ids from collapsing to PII placeholders
- data-01.3: src/l9_graphite_memory/admission/policy.py REPLACE Stop bare epochs and nine-digit ids from collapsing to PII placeholders
- data-01.4: tests/unit/test_normalization.py REPLACE Stop bare epochs and nine-digit ids from collapsing to PII placeholders
- data-04: src/l9_graphite_memory/mcp_tools.py REPLACE Stop MCP and generated-data from minting explicit evidence
- data-04.2: src/l9_graphite_memory/services/generated_data.py REPLACE Stop MCP and generated-data from minting explicit evidence
- data-05: src/l9_graphite_memory/contracts/privacy.py REPLACE Check consent issued time instead of defaulting granted_at to now
- data-05.2: src/l9_graphite_memory/mcp_tools.py REPLACE Check consent issued time instead of defaulting granted_at to now
- data-05.3: tests/unit/test_sensitive_admission.py REPLACE Check consent issued time instead of defaulting granted_at to now
