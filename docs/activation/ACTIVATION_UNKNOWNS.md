<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/activation/ACTIVATION_UNKNOWNS.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Activation Unknown Register

The PR pack proves everything a sandbox can prove: the code merges cleanly at the pin, all 150 tests and 27 preflight gates pass, the wheel installs, the config lifecycle emits digest-bound receipts, and the exact generated command completes a live MCP handshake with all canonical tools and `memory.health: complete`. The following items **cannot** be proven by this pack alone and remain `UNKNOWN` until the activation evidence contract (`EVIDENCE_CONTRACT.yaml`) is satisfied on the operator's machine.

| # | Unknown | Resolved by | Playbook stage |
|---|---|---|---|
| U-01 | Operator's actual home directory and Cursor process user | Stage 0–1 receipts on the operator machine | E-00, E-01 |
| U-02 | Whether a project-level `.cursor/mcp.json` exists and shadows the global entry | `client cursor inspect` findings | E-01 |
| U-03 | Cursor version and exact UI labels (Settings → Tools & MCP naming varies) | Settings screenshot | E-06 |
| U-04 | Whether Cursor accepts the generated entry without local environmental restrictions (sandboxing, PATH, venv resolution) | Live tool call in the IDE | E-06 |
| U-05 | Live IDE tool visibility (22 tools listed and callable) | Settings screenshot + transcript | E-06 |
| U-06 | The operator's real namespace claims | Hydration transcript for the actual namespace | E-07 |
| U-07 | Live canonical data health on the operator's store | `memory.health` from inside Cursor matching terminal health | E-06, E-12 |
| U-08 | Graphiti or Zep projection availability (external blocker B-002 in repo evidence) | Provider-connected health/projection receipts | E-06, out of pack scope |
| U-09 | Guard soak duration and observed false-positive rate | Soak evidence and analysis | E-09 |
| U-10 | Approval to enable write gates | Explicit operator sign-off recorded in the activation report | E-11 |

Each row transitions from `UNKNOWN` to resolved only by attaching the named evidence to `ACTIVATION_REPORT.md`. The state machine refuses `FULLY_INSTANTIATED` while any row required by the evidence contract is open; U-08 is the one item that may legitimately remain open if the deployment intentionally runs local-store-only, in which case record it as a scoped exception rather than a resolution.
