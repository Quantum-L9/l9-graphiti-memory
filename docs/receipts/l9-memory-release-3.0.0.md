<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/receipts/l9-memory-release-3.0.0.md
layer: documentation
owner: memory-control-plane
status: active
version: 3.0.0
updated: 2026-11-14
/L9_META -->

# l9-graphite-memory 3.0.0 release admission

Admits package `3.0.0` for publication. This record is prepared by the release coordinator and is not a decision until the decision owner merges it on the default branch (ADR-094). It does not move or recreate any existing tag.

| Coordinate | Value |
|---|---|
| Package | `l9-graphite-memory` `3.0.0` |
| Admitted source | `e46412c08c2b8954f0cfdbbd0bc199d39d076f8f` |
| Merged pull request | https://github.com/Quantum-L9/l9-graphiti-memory/pull/125 |
| Schema | `MEMORY_SCHEMA_VERSION` `2.2.0` |
| Control plane | `memory-control-plane/v1` |
| Authority | `Quantum-L9/.github@d4397e53f8f4c23458a80f87db9552463ad9e26f` |
| Topology | `sha256:db3f58851bd27d7932dfa22b0e25361cb5d50d68f9807e5f5a5627c62e29699f` |
| Product manifest | `sha256:0cb5638ef34bfab1d14ce93161ded9844ea0070fdcfccdbeb1fe036980bda8ba` |
| Wheel | `l9_graphite_memory-3.0.0-py3-none-any.whl` |
| Wheel sha256 | `2cf576f6405cb1b5230c717df55b0395ed9b8b98c65a28a194df9ba972467398` |
| Sdist | `l9_graphite_memory-3.0.0.tar.gz` |
| Sdist sha256 | `4b44eeed4f9fc36040608693cca67dc3b71754ddde911328c270e713d808494c` |
| Build recipe | `scripts/build_release_artifacts.sh`, `SOURCE_DATE_EPOCH=1784592000` |
| Release tag | `v3.0.0`, annotated, not yet created; to be created on the admitted source |
| Source CI | https://github.com/Quantum-L9/l9-graphiti-memory/actions/runs/43616161429 (pull request #125 head, tree identical to the admitted source) |

## How the digests were obtained

The repository's single build recipe was run at the admitted source in three independent environments, and all three produced the two digests above:

- CI `validate (3.13)` and `validate (3.10)` on pull request #125's head `fe340200c9fb2cc1d8d71ecb345890ae3e4560a6`, whose tree is identical to the admitted source (`git diff` between the two is empty): Python 3.13.18 with zlib 1.4, and Python 3.10.22 with zlib 1.3.2.
- A build from a `git archive` export of the admitted source on a separate machine: Python 3.13.18 with zlib 1.3. Two further builds of that tree under different file timestamps and umasks (022 and 002) gave the same digests.

Before pull request #125 the sdist digest differed on every build of the same commit, which is why no digest from an earlier commit is recorded here.

## What this record does not claim

- No `v3.0.0` tag exists at the time of writing. The tag names the admitted source above, not this receipt's commit.
- Nothing is published: no PyPI release, no container image, no deployment.
- The publication-mode validation that `publish.yml` runs against the pinned semantic authority has not been run for this source; that run is the release job's, and it fails closed.
- Hosted provider, production migration and credential-rotation proof are outside local and CI evidence (the five external blockers `scripts/validate_release.sh` records).
