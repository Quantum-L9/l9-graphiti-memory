<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: skill/l9-release-publication/references/github-release.md
layer: skill
owner: memory-control-plane
status: active
version: 2.6.0
updated: 2026-07-22
/L9_META -->

# Host Release after the workflow

Create the Release only after the publishing workflow run for the tag has succeeded and its digests match the admitted artifacts. A waiting or failed run has no Release step.

## Find the run

List workflow runs for the tag. Start with the run whose event is the tag push and whose head SHA is the peeled commit. Ignore older waiting runs. Do not start `workflow_dispatch` while that run is in progress or waiting.

For `Quantum-L9/l9-graphiti-memory`, publication has two passes (ADR-022, amendment 2026-10-15). The tag-push run stops at `Verify the exact-release admission` when no receipt `docs/receipts/l9-memory-release-<version>.md` on the default branch matches the built bytes, and prints the observed tuple. Report that tuple and stop; the receipt merges under the repository's merge authority, not through this skill. After it merges, start `publish.yml` once through `workflow_dispatch` with input `release_tag` set to the same tag; that run checks out the tag, rebuilds, and publishes only if the rebuilt digests equal the receipt. The publishing run is the one whose PyPI step ran. A dispatch for any other reason is not part of this sequence. Since the ADR-022 amendment of 2026-11-14 the build is reproducible: when the receipt already merged before the tag push (its digests computed with `SOURCE_DATE_EPOCH=1784592000 bash scripts/build_release_artifacts.sh <dir>` on a clean checkout of the admitted commit), the tag-push run passes the gate and publishes in one pass, and no dispatch follows.

If the job is waiting on an environment, report:

- workflow run URL
- job URL
- environment name
- required reviewer

Stop there. The operator approves that run. Continue on the same run id. Each pass waits on the `release` environment separately.

## Package evidence

Read the publishing run's digest file and the package-registry publish step. Compare each digest to the admitted checksum. A mismatch stops the Release. Do not rebuild locally and publish that rebuild as the run's artifact.

## Release entry

Search governance `ops/scripts` and `ops/make` for a command that creates the host Release. If the repository documents one, use that command. If none exists, create the Release with the host API bound to the peeled commit, and say that the repository command was absent. Absence is not permission to skip the Release.

For `Quantum-L9/l9-graphiti-memory`, ADR-022 requires the Release to include a source ZIP, wheel, sdist, change summary, and validation report. ADR-022 also lists a manifest; ADR-099 (2026-10-15) retired that repository inventory, and it is no longer generated or uploaded with release artifacts, so no manifest asset exists to attach. The observed `.github/workflows/publish.yml` triggers on `push` of `v*` and on `workflow_dispatch` (input `release_tag`), runs job `validate-and-publish` in environment `release`, publishes the package, and does not create the Release. Attach the workflow's built wheel, sdist, change summary, and validation report, plus a source archive of the peeled commit. Confirm the Release tag resolves to that commit and lists those assets before reporting `RELEASE_VERIFIED`.

For any other repository, read its workflow and release decision before naming assets. If the decision is missing, stop and label the required asset set `Unknown`.
