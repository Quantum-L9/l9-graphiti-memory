<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/activation/CURSOR_FULL_ACTIVATION_PLAYBOOK.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Cursor Full Activation Playbook — L9 Graphiti Memory

**Scope.** Turn on L9 memory in Cursor after the PR from this pack is merged, and close the instantiation loop with receipts. This playbook separates what the repository already proves mechanically (Stages 0–4 emit machine receipts) from what only you and a live Cursor IDE can prove (Stages 5–12). The state machine in `ACTIVATION_STATE_MACHINE.yaml` and the evidence contract in `EVIDENCE_CONTRACT.yaml` govern this document: **no stage may be marked done without its named evidence, and no stage may be skipped.** Record outcomes in `ACTIVATION_REPORT.md` as you go.

**Ground truth used by this playbook** (verified against the merged code): the CLI surface is `l9-memory client cursor {inspect,install,verify,status,uninstall}` (equivalently `python3 -m l9_graphite_memory.cli client cursor …`); the managed config target is `~/.cursor/mcp.json`, entry key `l9-graphite-memory`, command `<current-python> -m l9_graphite_memory.server --transport stdio`; every mutating operation writes a digest-bound backup `~/.cursor/mcp.json.l9-backup-<timestamp>`; the server exposes **22 tools** (15 canonical `memory.*` tools plus 7 compatibility aliases: `write`, `search`, `health`, `bootstrap`, `phase_lock`, `verify_phase_lock`, `conflicts`); the probe requires all 15 canonical tools and a `memory.health` status of `complete` or `partial` (never `failed`); the write gate is `L9_MEMORY_WRITE_GATES` read by `memory_guard.py`; the receipt-guard hooks are installed by `scripts/activate_guard.sh` into `~/.local/share/l9-memory/hooks`.

---

## Stage 0 — Establish the release (evidence: `E-00`)

Run in a terminal (Cursor's integrated terminal is fine):

```bash
REPO="$HOME/src/l9-graphiti-memory"        # adjust to your checkout
cd "$REPO"
git fetch origin main && git checkout main && git pull --ff-only
PINNED_RELEASE_SHA="$(git rev-parse HEAD)"
python3 -m venv .venv && . .venv/bin/activate
python -m pip install --upgrade pip && python -m pip install .
l9-memory health
```

Record `PINNED_RELEASE_SHA`, `which python`, `l9-memory --version` if available (package version should be `2.2.0`), and the full health JSON. **Gate:** health `status` must be `complete` (or `partial` with understood reasons). A `failed` canonical status blocks everything; consult `RUNBOOK.md` before proceeding.

## Stage 1 — Inspect the effective Cursor configuration (evidence: `E-01`)

```bash
l9-memory client cursor inspect > /tmp/e01_inspect.json; cat /tmp/e01_inspect.json
find "$HOME" -maxdepth 4 -path '*/.cursor/mcp.json' -print 2>/dev/null
```

The inspect receipt reports the resolved global path, whether a managed entry already exists, entry state (`absent`, `managed`, `foreign`, `ambiguous`), any project-scope shadows, and findings (symlink targets, malformed JSON, duplicate entries are fail-closed findings). **Gate:** no `blocking` finding. If a project-level `.cursor/mcp.json` defines `l9-graphite-memory`, resolve the shadow first — project scope overrides global in Cursor.

## Stage 2 — Dry-run the install (evidence: `E-02`)

```bash
l9-memory client cursor install --dry-run > /tmp/e02_plan.json; cat /tmp/e02_plan.json
```

Review the plan receipt: resolved path, existing-entry status, the exact `command`/`args` that will be written, the proposed post-write digest, preserved sibling server names, and the backup plan. **Gate:** the command must point at the interpreter from Stage 0's venv, and the plan must contain no secret or authorization material of any kind (stdio mode requires none).

## Stage 3 — Install atomically (evidence: `E-03`)

```bash
l9-memory client cursor install > "$HOME/l9-activation/e03_install_receipt.json"
mkdir -p "$HOME/l9-activation" 2>/dev/null || true   # create first if needed
stat -c '%a %U %s' "$HOME/.cursor/mcp.json"
python -m json.tool "$HOME/.cursor/mcp.json" >/dev/null && echo JSON_OK
```

Store the receipt **outside the repository**. **Gate:** receipt shows `"managed_entry_present": true`, records pre/post SHA-256 digests and a backup path; the file is user-owned with restricted mode (600); JSON parses. Installs are idempotent — re-running reports the already-converged state rather than rewriting. Never hand-edit the managed entry afterward (AGENTS.md invariant 9).

## Stage 4 — Verify the exact generated command (evidence: `E-04`)

```bash
l9-memory client cursor verify > "$HOME/l9-activation/e04_probe_receipt.json"
echo "exit=$?"
```

The probe launches the *exact* command written to the config in an isolated environment, performs the MCP handshake (`initialize` → `notifications/initialized` → `tools/list`), asserts all 15 canonical tools (22 listed with aliases), calls `memory.health`, then terminates and reaps the child. **Gate:** exit code 0 and receipt fields `"status": "complete"`, `"required_tools_present": true`, `"missing_tools": []`, `"health_status": "complete"`, `"stderr_excerpt"` free of secrets (redaction is automatic). A reference passing receipt from pack assembly is at `activation_evidence/live_probe_receipt.json`.

## Stage 5 — Reload Cursor (evidence: `E-05`)

Fully quit and reopen Cursor, or run **Command Palette → “Developer: Reload Window”**. Configuration on disk is *not* evidence that Cursor loaded it. Evidence for this stage is the next stage's screenshot/transcript — Stage 5 has no standalone receipt but must still be performed.

## Stage 6 — Prove visibility inside Cursor (evidence: `E-06`)

Open **Cursor Settings → Tools & MCP** (older builds: Settings → MCP) and confirm `l9-graphite-memory` appears with a green/enabled indicator and 22 tools. Then, in a Cursor Agent conversation, send:

```text
Use l9-graphite-memory to call memory.health. Return the canonical-store,
projection, schema, and outbox statuses exactly as reported, without guessing.
```

**Gate:** the agent performs a real tool call (visible in the tool-call UI) and the reported statuses match a fresh `l9-memory health` run in the terminal. Save a screenshot of the MCP settings panel and the redacted transcript into `~/l9-activation/`.

## Stage 7 — Hydrate before work (evidence: `E-07`)

In the same Cursor conversation:

```text
Use memory.hydrate for the active repository namespace with the task
"verify Cursor memory instantiation". Then call memory.conflicts for the same
namespace. Report packet counts and conflict counts exactly; do not treat a
partial or failed retrieval as an empty result.
```

**Gate:** hydration returns a well-formed packet response (zero packets is acceptable on a fresh store; a `failed` retrieval status is not), and `memory.conflicts` completes. Save the transcript.

## Stage 8 — Prove a governed, idempotent write (evidence: `E-08`)

First ask the agent to *propose* the observation without writing (review namespace, memory class, provenance, evidence, confidence, and idempotency key). Then execute:

```text
Use memory.ingest to write a non-sensitive durable observation recording that
Cursor memory instantiation was verified on <date> at release <PINNED_RELEASE_SHA>,
with idempotency_key "cursor-activation-<PINNED_RELEASE_SHA>". Report the full
write receipt. Then call memory.ingest again with the identical payload and
idempotency_key, and report whether a duplicate canonical record was created.
```

**Gate:** first call returns a durable write receipt; the replay returns an idempotent no-duplicate outcome (same canonical record, no second insert). Never store tokens, private reasoning, raw secrets, personal sensitive data, or unverified conclusions (AGENTS.md law).

## Stage 9 — Install the receipt guard and soak in observe mode (evidence: `E-09`)

```bash
cd "$REPO" && bash scripts/activate_guard.sh          # installs hooks to ~/.local/share/l9-memory/hooks
export L9_MEMORY_WRITE_GATES=0                        # observation mode
```

Work normally in Cursor for a bounded soak period (a working session at minimum). Collect hydration receipts, phase-lock events, and guard observations from the hooks directory. **Gate:** all false positives diagnosed and explained before any enforcement. Note `scripts/activate_gate.sh` is a deprecated wrapper for the same guard — use `activate_guard.sh`.

## Stage 10 — Verify phase lock (evidence: `E-10`)

In Cursor (or via CLI):

```text
Use memory.phase_lock to create a lock for the bounded task
"cursor-activation-soak", then memory.verify_phase_lock for the same lock.
Report both receipts exactly.
```

**Gate:** lock created and verified cleanly. A lock denial, conflict, partial retrieval, or failed verification **blocks** write-gate activation until resolved.

## Stage 11 — Enable write gates only with explicit approval (evidence: `E-11`)

Only after E-09 and E-10 pass, and only with the operator's explicit sign-off recorded in `ACTIVATION_REPORT.md`:

```bash
export L9_MEMORY_WRITE_GATES=1
```

Persist this only in an approved machine-level environment mechanism (shell profile, systemd user environment, or OS keychain-backed env manager). **Never** add it to the repository, to `~/.cursor/mcp.json`, or to any committed file — the config-drift and secrets gates will reject it, and invariant 9 forbids it.

## Stage 12 — Convergence check and closure (evidence: `E-12`)

```bash
l9-memory client cursor status > "$HOME/l9-activation/e12_status.json"
l9-memory client cursor verify > "$HOME/l9-activation/e12_verify.json"
l9-memory health               > "$HOME/l9-activation/e12_health.json"
```

**Gate (all simultaneously true):** status receipt shows installed + verified; probe receipt `complete` with exit 0; canonical health `complete`; plus, from the live IDE: one Cursor-side health call (E-06), one hydration (E-07), one idempotent write receipt (E-08), and one phase-lock verification (E-10). When and only when all named evidence exists, record the terminal state in `ACTIVATION_REPORT.md`:

> state: FULLY_INSTANTIATED

## Failure and rollback at any stage

Any failed gate sends the state machine to `DIAGNOSE` (see `ACTIVATION_STATE_MACHINE.yaml`), never silently forward. The reversible escape hatch is always available and receipt-verified:

```bash
l9-memory client cursor uninstall && l9-memory client cursor status
```

which removes only the managed entry, preserves all other servers, and records digests; backups at `~/.cursor/mcp.json.l9-backup-<timestamp>` allow byte-exact restore. Repository-level rollback is documented in the pack's `ROLLBACK.md`.
