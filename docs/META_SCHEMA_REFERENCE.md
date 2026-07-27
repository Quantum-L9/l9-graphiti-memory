<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/META_SCHEMA_REFERENCE.md
layer: reference
owner: memory-control-plane
status: active
version: 1.0.0
updated: 2026-07-27
generated_by: Manus AI pack validation
/L9_META -->
# Metadata Schema Reference: L9_META vs skill_schema

This document defines the two metadata header schemas encountered during the Phase 6 handoff
pack validation: the **L9-mandated `L9_META` header** enforced repository-wide in
`Quantum-L9/l9-graphiti-memory`, followed by the **`skill_schema` header** used by every file in
the `l9-deploy-phase6-operator` pack. All field definitions below are derived from the executable
sources of truth (`tools/assurance/apply_l9_meta.py`, `tools/assurance/check_l9_meta.py`,
`manifest.json` schema `l9.release-manifest/v2`, and the pack files themselves), not from
documentation alone.

---

## Part 1 — L9-Mandated Metadata: `L9_META` (l9_schema: 1)

### Contract

Every tracked file in the repository MUST carry metadata through at least one of two carriers,
and inline-capable files MUST carry both:

1. **Manifest carrier (all files):** an `l9_meta` object in `manifest.json`
   (schema `l9.release-manifest/v2`), keyed by repo-relative path with size and SHA-256.
2. **Inline carrier (text files):** an `L9_META` comment block within the **first 50 lines**
   of the file. Inline-capable extensions: `.py .sh .md .mdc .yaml .yml .toml .in` plus
   `.gitignore`. Exception: `.github/governance/*` (strict JSON, manifest-only).

Enforced by `check_l9_meta.py` in CI; auto-injected by `apply_l9_meta.py` when the literal
string `L9_META` is absent from the first 40 lines.

### Fields (all required, fixed order)

| Field | Type | Constraint | Purpose |
|---|---|---|---|
| `l9_schema` | int | Must be `1` | Schema version of the meta block itself |
| `repo` | string | Must equal `Quantum-L9/l9-graphiti-memory` exactly | Binds file to its home repository |
| `path` | string | Must equal the repo-relative POSIX path exactly | Prevents file relocation drift |
| `layer` | enum | Derived from path: `contract`, `port`, `integration`, `adapter`, `service`, `package`, `test`, `ci`, `skill`, `repository`, `operations`, ... | Architectural layer assignment |
| `owner` | string | `memory-control-plane` | Owning control plane |
| `status` | enum | `active` | Lifecycle state |
| `version` | semver | Repo release version (currently `2.2.0`) | Release binding |
| `updated` | date | ISO `YYYY-MM-DD` | Last stamped date |

### Canonical example — Markdown (HTML comment form)

```markdown
<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/EXAMPLE.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->
# Document Title
```

### Canonical example — Python / Shell / YAML / TOML (`#` comment form)

```python
#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/example.py
#   layer: operations
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22
```

### Canonical example — Manifest carrier (`manifest.json` entry)

```json
{
  "category": "ci",
  "l9_meta": {
    "l9_schema": 1,
    "layer": "ci",
    "owner": "memory-control-plane",
    "path": ".github/issues.json",
    "repo": "Quantum-L9/l9-graphiti-memory",
    "status": "active",
    "updated": "2026-07-22",
    "version": "2.2.0"
  },
  "path": ".github/issues.json",
  "sha256": "23cbdff3ae0c9491c419771321766af4f510cd954dc671404994e7c7e3771d28",
  "size_bytes": 5755
}
```

### Placement rules (from `apply_l9_meta.py`)

- Markdown with YAML frontmatter (`---` ... `---`): block inserted immediately **after** the
  closing frontmatter delimiter.
- ADR files (`docs/adr/ADR-*.md` starting with `# ADR-`): block inserted after the title line.
- Scripts with shebang (`#!`): block inserted on the line after the shebang.
- All other files: block inserted at the very top.
- CI failure modes: `missing manifest metadata carrier`, `invalid manifest l9_meta`,
  `missing inline L9_META`.

---

## Part 2 — Pack Metadata: `skill_schema` (as used in l9-deploy-phase6-operator)

### Contract

Every text file in the portable pack carries a `skill_schema: 1` header identifying its role
within the **skill pack**, not within any repository. The header is deliberately repo-agnostic:
it has no `repo` or `path` field, because the pack is a sealed, relocatable artifact whose
integrity is bound by its own `MANIFEST.sha256` (72 hashed files) rather than by location.
The entrypoint `SKILL.md` uses YAML frontmatter; all other files use comment headers.

### Fields

| Field | Type | Required | Purpose |
|---|---|---|---|
| `skill_schema` | int | yes (`1`) | Schema version of the skill header |
| `name` | string | SKILL.md only | Skill identifier (`l9-deploy-phase6-operator`) |
| `description` | string | SKILL.md only | Trigger/usage description |
| `parent` | string | all non-entrypoint files | Owning skill (`l9-deploy-phase6-operator`) |
| `layer` | enum | yes | `control_plane`, `reference`, `script`, `schema`, `test`, `asset` |
| `role` | string | yes | Specific function, e.g. `phase6_control_cli`, `executable_decision_policy`, `pack_validator`, `evidence_integrity_library`, `oidc_cryptographic_verifier` |
| `tags` | list | optional | Search/routing tags |
| `owner` | string | yes | `igor_beylin` |
| `status` | enum | yes | `active` |
| `version` | semver | yes | Per-file version (2.0.0–3.2.0 across the pack) |
| `updated` | date | yes | ISO `YYYY-MM-DD` (2026-07-26) |
| `sources` | list | SKILL.md only | Provenance references |

### Example — SKILL.md entrypoint (YAML frontmatter form)

```markdown
---
name: l9-deploy-phase6-operator
description: execute and independently validate the l9-deploy protected staging lifecycle ...
skill_schema: 1
layer: control_plane
role: skill_entrypoint
tags: [l9-deploy, phase6, staging, oidc, rollback, evidence-authority]
owner: igor_beylin
status: active
version: 3.1.0
updated: 2026-07-26
sources:
  - source-evidence/PLAN_LOCKED.md
  - references/repository-baseline-manifest.json
---
# L9 Deploy Phase 6 Operator
```

### Example — Markdown reference (HTML comment form)

```markdown
<!--
skill_schema: 1
parent: l9-deploy-phase6-operator
layer: reference
role: operator_runbook
tags: [runbook, staging, evidence, recovery]
owner: igor_beylin
status: active
version: 3.2.0
updated: 2026-07-26
-->
# Phase 6 Operator Runbook
```

### Example — Python / Shell script (`#` comment form)

```python
#!/usr/bin/env python3
# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: phase6_control_cli
# tags: [phase6, evidence, policy, ledger, validation, provenance]
# owner: igor_beylin
# status: active
# version: 3.0.0
# updated: 2026-07-26
# Purpose: derive Phase 6 decisions from signed, content-bound, source-constrained evidence.
```

### Example — JSON Schema (`$comment` form, since JSON has no comments)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.quantum-l9.invalid/l9/deploy/phase6-input/v2",
  "$comment": "skill_schema=1; parent=l9-deploy-phase6-operator; layer=schema; role=input_contract; owner=igor_beylin; status=active; version=2.0.0; updated=2026-07-26"
}
```

---

## Part 3 — Why the Two Schemas Collide

| Dimension | `L9_META` (repo) | `skill_schema` (pack) |
|---|---|---|
| Identity anchor | Repository + exact path | Parent skill, location-independent |
| Integrity anchor | `manifest.json` (l9.release-manifest/v2) | Pack `MANIFEST.sha256` (exact byte state) |
| Injection trigger | Literal string `L9_META` absent in first 40 lines | n/a (authored at build time) |
| Owner | `memory-control-plane` | `igor_beylin` |
| Repo binding | `repo:` + `path:` mandatory | Deliberately absent (portable) |

Because no pack file contains the literal string `L9_META`, the repo's injector treats all 56
inline-capable pack files as *missing meta* and prepends its own block — which changes their
bytes and invalidates the pack's `MANIFEST.sha256`. Conversely, the pack headers cannot satisfy
`check_l9_meta.py` because they lack `repo:` and `path:` bindings. The two schemas are each
internally sound but mutually exclusive on the same bytes; this is why the pack is archived in
the repository as a sealed zip (`release-work/handoffs/`) rather than as loose files.
