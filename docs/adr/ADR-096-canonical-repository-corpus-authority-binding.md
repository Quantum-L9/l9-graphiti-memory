# ADR-096: Canonical Repository Corpus Authority Binding

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-096-canonical-repository-corpus-authority-binding.md
layer: adr
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-10-08
/L9_META -->


**Date:** 2026-10-02 (renumbered from a draft ADR-085 on 2026-10-08; ADR-085 is the tenant-safe graph scope key)
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.5+

## Status
Accepted
## Context
Quantum-L9 organization governance now has a canonical repository registry and
RepositoryClass catalog in `Quantum-L9/.github`.
The repository registry owns stable repository identity, lifecycle, and class
assignment. The repository-class catalog owns the organization obligations that
follow from each class.
The L9 RepositoryClass requires membership in logical memory namespace `l9`.
The organization-level repository view
`l9.repository-view/memory-namespace-l9@1` resolves that corpus.
Before this decision, `l9-graphiti-memory` could identify repositories through
local resolution configuration and repository bootstrap logic, but those
surfaces were not authoritative organization membership ledgers. Maintaining
another repository list here would create a second source of truth and allow
organization membership to drift from `.github`.
The memory system nevertheless needs a local, executable answer to a different
question: whether a repository is eligible to enter the shared L9 repository
corpus and which authorized runtime namespace represents that corpus.
## Decision
1. `Quantum-L9/.github` remains the sole canonical owner of repository identity,
   lifecycle, RepositoryClass assignment, and L9 repository membership.
2. `l9-graphiti-memory` consumes
   `l9.repository-view/memory-namespace-l9@1` as a deterministic generated
   projection.
3. The generated projection is stored as packaged resource
   `src/l9_graphite_memory/resources/repository_corpus.yaml`.
4. The projection remains globally non-canonical and has authority class
   `derived`.
5. Every generated projection has a deterministic packaged receipt at
   `src/l9_graphite_memory/resources/repository_corpus.receipt.yaml`.
6. The receipt binds:
   - canonical source repository,
   - canonical source revision,
   - repository-registry artifact and digest,
   - repository-class artifact and digest,
   - organization repository-view coordinate,
   - generated output digest,
   - deterministic generator identity.
7. The local authored contract
   `repository_corpus_binding.yaml` makes the verified derived projection
   governing for exactly three downstream decisions:
   - L9 repository-corpus membership,
   - L9 repository-ingestion eligibility,
   - binding of logical namespace `l9` to runtime namespace `project-group/l9`.
8. "Derived" and "governing" are independent dimensions. The projection is
   derived because its facts originate upstream. It is governing downstream
   because this repository explicitly binds the relevant local decisions to
   that verified projection.
9. A current projected L9 repository is eligible for organization-corpus
   ingestion only in `project-group/l9`.
10. A repository absent from the projected corpus cannot be ingested into
    `project-group/l9`.
11. A projected repository whose lifecycle is `superseded` or `retired`
    remains historically resolvable but is not eligible for new ingestion.
12. `RepositoryBootstrapper` enforces the governing projection before source
    distillation begins.
13. The bootstrapper canonicalizes an admitted repository to the repository
    coordinate carried by the projection. Local path names and Git remotes are
    observations used only to resolve that canonical coordinate.
14. Membership must never be inferred from:
    - repository naming,
    - an `l9-` prefix,
    - Quantum-L9 organization hosting,
    - repository shape,
    - local directory names,
    - `group_registry.yaml`,
    - provider state,
    - existing memory records.
15. `group_registry.yaml` remains a repository-discovery aid only. It is not
    an L9 membership authority.
16. Repository membership controls source eligibility only. It does not admit
    any memory assertion. Every assertion still passes through the canonical
    `MemoryService` authorization, validation, admission, and persistence path.
17. Repository content remains authoritative in its source repository.
    Distilled memory records are derived representations.
18. Graphiti, Zep, semantic indexes, and other provider projections remain
    rebuildable downstream projections and cannot establish repository
    membership.
19. Missing, malformed, stale, conflicting, or unverifiable projection state
    fails closed for L9 organization-corpus ingestion.
20. Agents must regenerate the projection from `.github`; they may not repair
    generated projection files manually.
## Alternatives Considered
- Maintain a hand-authored repository list in `l9-graphiti-memory`.
- Reuse `group_registry.yaml` as the organization repository registry.
- Infer L9 repositories from the `l9-` naming prefix.
- Treat every repository hosted in the Quantum-L9 organization as an L9 memory
  source.
- Read `.github` dynamically on every ingestion request.
- Copy the canonical repository registry into this repository and treat the copy
  as locally canonical.
- Allow callers to choose the namespace of a projected L9 repository.
## Rejected Alternatives
A hand-authored local list creates competing authority and inevitable drift.
`group_registry.yaml` describes local resolution behavior and therefore cannot
be promoted into organization semantic authority.
Name-prefix and organization-hosting inference make membership implicit and
cannot represent deliberate exclusions, external forks, auxiliary
repositories, retirement, or historical identity.
Dynamic remote reads on each ingestion operation make runtime correctness
depend on network availability and mutable remote state.
Copying the canonical registry and treating the copy as canonical transfers
authority incorrectly.
Allowing callers to select arbitrary namespaces for L9 repositories defeats
the organization-level namespace obligation and permits fragmentation of the
shared corpus.
## Invariants
- `.github` is canonical for repository membership.
- The downstream corpus artifact is always derived.
- The local binding is canonical only for this repository's use of the
  projection.
- The generated corpus and receipt are deterministic.
- The committed output digest must equal the receipt output digest.
- Every projected repository carries its canonical registry id, coordinate,
  lifecycle, and class reference.
- Every projected repository has class
  `l9.repository-class/l9@1`.
- Only current projected repositories are ingestion eligible.
- Current projected L9 repositories use `project-group/l9`.
- Nonmembers cannot enter `project-group/l9`.
- Repository content authority remains with the source repository.
- Memory assertion admission remains with `MemoryService`.
- Provider projections never become canonical memory or membership authority.
- Invalid authority state fails closed.
## Consequences
A repository can enter or leave the active L9 memory corpus by changing one
canonical class assignment or lifecycle fact in `.github` and regenerating the
projection.
No Graphiti-memory-maintained repository membership list is required.
The installed Python wheel carries the same governing corpus projection and
receipt as source-checkout operation.
Repository bootstrapping becomes stricter for repositories in the L9 corpus:
their shared organization namespace cannot be locally overridden.
A stale generated projection becomes a visible conformance failure instead of
silent membership drift.
Historical repositories remain identifiable without receiving new ingestion.
## Security Impact
This decision narrows authority.
A caller cannot place an arbitrary repository into the shared L9 namespace by
choosing a namespace string.
The projected corpus contains repository identity and lifecycle metadata only.
It contains no credentials, secrets, source contents, access tokens, or memory
records.
Existing principal derivation, namespace authorization, consent, admission,
and canonical write-path controls remain unchanged.
## Migration Impact
Generate the first `repository_corpus.yaml` and
`repository_corpus.receipt.yaml` from the admitted `.github` repository
registry and repository-class artifacts.
Repository bootstrap calls for projected L9 repositories must use
`project-group/l9`.
Any local repository-membership semantics currently encoded in
`group_registry.yaml` must be treated as discovery hints only and may be
removed once all callers resolve identity through the projected corpus.
Existing memory records are not automatically moved, rewritten, or deleted by
this decision.
Repository removal, retirement, or reclassification stops future corpus
ingestion but does not automatically erase historical canonical memory.
Deletion remains governed by the existing memory lifecycle.
## Validation Requirements
- `tests/unit/test_repository_corpus.py` validates projection and binding
  resolution, coordinate normalization, lifecycle behavior, and fail-closed
  authority rules.
- `tests/integration/test_repository_corpus_ingestion.py` validates the
  downstream namespace boundary.
- `tools/assurance/check_repository_corpus_governance.py` validates the
  generated artifact, receipt digest, governing binding, repository entries,
  and bootstrap enforcement wiring.
- `tools/authority/project_l9_repository_corpus.py --check` proves that the
  committed projection exactly matches the pinned canonical `.github` inputs.
- The installed wheel must contain `repository_corpus.yaml`,
  `repository_corpus.receipt.yaml`, and `repository_corpus_binding.yaml`.
- `bash scripts/preflight.sh`.
- `bash scripts/validate_release.sh`.
## Rollback Conditions
Roll back this decision if corpus enforcement can admit an unregistered
repository to `project-group/l9`, reject a valid current repository because of
non-authoritative local state, accept a generated artifact whose receipt digest
does not match, or allow a projected L9 repository to bypass the canonical
MemoryService write path.
Rollback must not promote `group_registry.yaml`, memory records, provider
state, repository names, or organization hosting into replacement membership
authority.
A rollback may disable organization-corpus ingestion while preserving existing
canonical memory and historical records.
## Supersedes / Superseded By
Extends ADR-001, ADR-005, ADR-006, ADR-036, ADR-037, ADR-042, ADR-043,
ADR-059, ADR-062, ADR-063, ADR-078, and ADR-084.
Supersedes no existing canonical-memory decision.
Superseded by none.
