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

Create the Release only after the tag-triggered workflow has succeeded and its digests match the admitted artifacts. A waiting or failed run has no Release step.

## Find the run

List workflow runs for the tag. Keep the run whose event is the tag push and whose head SHA is the peeled commit. Ignore older waiting runs. Do not start `workflow_dispatch` while that run exists.

If the job is waiting on an environment, report:

- workflow run URL
- job URL
- environment name
- required reviewer

Stop there. The operator approves that run. Continue on the same run id.

## Package evidence

Read the successful run's digest file and the package-registry publish step. Compare each digest to the admitted checksum. A mismatch stops the Release. Do not rebuild locally and publish that rebuild as the run's artifact.

## Release entry

Search governance `ops/scripts` and `ops/make` for a command that creates the host Release. If the repository documents one, use that command. If none exists, create the Release with the host API bound to the peeled commit, and say that the repository command was absent. Absence is not permission to skip the Release.

For `Quantum-L9/l9-graphiti-memory`, ADR-022 requires the Release to include a source ZIP, wheel, sdist, manifest, change summary, and validation report. The observed `.github/workflows/publish.yml` triggers on `push` of `v*` and on `workflow_dispatch`, runs job `validate-and-publish` in environment `release`, publishes the package, and does not create the Release. Attach the workflow's built wheel, sdist, manifest, change summary, and validation report, plus a source archive of the peeled commit. Confirm the Release tag resolves to that commit and lists those assets before reporting `RELEASE_VERIFIED`.

For any other repository, read its workflow and release decision before naming assets. If the decision is missing, stop and label the required asset set `Unknown`.
