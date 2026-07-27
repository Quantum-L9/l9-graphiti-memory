<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: tools/phase6/references/SECRET_SAFETY.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

<!--
skill_schema: 1
parent: l9-deploy-phase6-operator
layer: reference
role: secret_safety_policy
tags: [secrets, canary, redaction, leakage]
owner: igor_beylin
status: active
version: 1.0.0
updated: 2026-07-26
-->
# Secret and Canary Safety

- Use only reversible, non-customer staging test secrets.
- Generate the canary immediately before the scenario and keep it only in process memory or the authorized secret manager.
- Never pass the canary as a command-line argument.
- Disable shell tracing before secret operations.
- Do not hash individual secret values into state or receipts.
- Scan raw downloaded logs and artifacts before wider distribution.
- The scanner checks exact, URL-encoded, Base64, and shell-escaped variants without printing the canary.
- Delete local raw secret-bearing material after the scan and preserve only the redacted result.
- Any canary match is an immediate NO-GO and incident.
