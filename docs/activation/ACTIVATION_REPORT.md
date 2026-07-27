<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/activation/ACTIVATION_REPORT.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Activation Report — Fill As You Execute the Playbook

This report instantiates the handoff template `l9.cursor-memory-instantiation.activation-report/v1`. Fields already proven by the PR pack's sandbox execution are pre-filled with their observed values so you can see exactly what a passing entry looks like; every field that only your machine and your Cursor IDE can prove is marked `UNKNOWN` and must be replaced with your observed value (or the path to your saved receipt) as you complete each stage. The report is complete when `status` can honestly be set to `FULLY_INSTANTIATED` per Stage 12 of the playbook.

```yaml
schema: l9.cursor-memory-instantiation.activation-report/v1
activation_run_id: UNKNOWN            # e.g. cursor-activation-2026-07-28-01
bindings:
  repository_sha: UNKNOWN             # your merged tip; pack base was 24bf45264dbae7d61269a4865db2ba8b1adbaf71
  package_version: "2.2.0"            # confirm from your wheel/venv
  python_executable: UNKNOWN          # `which python` from Stage 0 venv
  home_directory_digest: UNKNOWN      # sha256 of $HOME string if required by your evidence store
  config_path: UNKNOWN                # expected: $HOME/.cursor/mcp.json
  config_post_sha256: UNKNOWN         # from your E-03 install receipt post_sha256
  generated_command_sha256: UNKNOWN   # sha256 of the joined command_argv from your receipt
evidence:
  baseline: UNKNOWN                   # E-00: health JSON path (reference: pack showed status complete, 22 tools)
  install: UNKNOWN                    # E-03: receipt path (reference: activation_evidence/live_install_receipt.json)
  mcp_probe: UNKNOWN                  # E-04: receipt path (reference: activation_evidence/live_probe_receipt.json,
                                      #   status complete, health complete, 22 tools, exit 0)
  cursor_live: UNKNOWN                # E-06: settings screenshot + redacted transcript paths
  hydration: UNKNOWN                  # E-07: transcript path with packet/conflict counts
  write: UNKNOWN                      # E-08: write receipt + idempotent replay outcome
  guard_soak: UNKNOWN                 # E-09: soak window, hook observations, false-positive analysis
  phase_lock: UNKNOWN                 # E-10: lock + verify receipts
  gate_enablement: UNKNOWN            # E-11: operator sign-off record and persistence mechanism used
derived_state: UNINSTALLED            # advance per ACTIVATION_STATE_MACHINE.yaml; never skip states
unresolved_unknowns:
  - operator home directory and Cursor process user
  - presence of project-level .cursor/mcp.json shadows on the operator machine
  - Cursor version and exact UI labels
  - Cursor acceptance of the generated entry under local environmental restrictions
  - live IDE tool visibility
  - operator's real namespace claims
  - live canonical data health on the operator store
  - Graphiti or Zep projection availability
  - guard soak duration and false-positive rate
  - approval to enable write gates
status: UNKNOWN                       # terminal value must be FULLY_INSTANTIATED or a diagnosed blocker
```

Remove items from `unresolved_unknowns` only when the corresponding evidence field holds a real receipt. The pack's own receipts under `activation_evidence/` prove the machine-provable half of the loop (sandbox install, exact-command probe, installed-wheel lifecycle); they are references for shape and passing values, and they do not substitute for your live IDE evidence.
