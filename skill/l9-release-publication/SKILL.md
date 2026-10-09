---
name: l9-release-publication
description: Publish one already-admitted annotated release tag and finish the package workflow and GitHub Release. use when a merged source already has a fixed local annotated tag and the operator asks to publish that exact tag. do not use when the version or source still needs a pull request, or for a production deploy or governance rebind.
disable-model-invocation: true
metadata:
  skill_schema: 1
  layer: control_plane
  role: skill_entrypoint
  tags: [l9, release, publication, tag, github]
  owner: igor_beylin
  status: active
  version: "1.1.0"
  updated: "2026-10-09"
  license: Proprietary
---

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: skill/l9-release-publication/SKILL.md
layer: skill
owner: memory-control-plane
status: active
version: 2.6.0
updated: 2026-07-22
/L9_META -->


# Release publication

## Purpose

Publish an annotated tag that already names an admitted commit, then finish the one workflow that tag starts and the host Release that workflow does not create. The tag object is the release identity. A new pull request, a rebuilt tag, or a second workflow run is a different release.

## Activation boundary

Use this skill only when the operator names an existing annotated tag and its admitted tag-object SHA and peeled commit. Reject version bumps, source repairs, new pull requests, tag moves, production deployment, and governance rebind.

## Authority

1. The operator's latest instruction naming the tag, the tag-object SHA, and the peeled commit.
2. The local annotated tag object.
3. The remote tag object returned by the host.
4. The repository's release decision for required assets, then the workflow run that the tag push started.
5. `Unknown`. Inference never supplies a SHA, a digest, or a publication claim.

## Sequence

1. Run [verify_release_tag.py](scripts/verify_release_tag.py) against the local repository. Exit 1 means stop. Do not delete, move, or recreate the tag.
2. Run the same script with `--remote owner/name`. `REMOTE_ABSENT` is the only result that permits a push. `MATCH` means the tag is already on the host; go to step 5. Any other result stops the publication.
3. Publish that one ref. Load [publication-plane.md](references/publication-plane.md) and follow it. Write the receipt, then push, as two commands. No `--force` and no `--tags`. `make pr` pushes the current branch and cannot publish a tag. Do not create the tag object through the host API.
4. Run the script again with `--remote` and `--require-remote`. Continue only on `MATCH` for both the tag object and the peeled commit.
5. Watch the single workflow run created by that tag push. Do not dispatch another run. If the run is waiting on an environment reviewer, stop and give the operator the run URL, the job URL, the environment name, and the reviewer. Resume that same run after the operator approves it.
6. After that run succeeds, compare its artifact digests to the admitted checksums. Record package publication from the run and the package registry. A local rebuild is not publication evidence.
7. Create the host Release only after step 6 succeeds. Read [github-release.md](references/github-release.md). Bind the Release to the peeled commit and attach the assets the repository's release decision names.
8. Confirm the Release tag, target commit, and asset names. Report `RELEASE_VERIFIED` only when steps 4, 6, and 8 all hold.

## Adapters

The core sequence assumes the L9 publication plane evaluates the push. When that gate is not installed, load [ungoverned-git.md](adapters/ungoverned-git.md) and do not write a publish-path receipt. If it is unknown whether the gate is installed, stop and label the transport `Unknown`.

## Fail closed

- A pending environment approval is not success.
- A successful package workflow without the host Release is not `RELEASE_VERIFIED`.
- A remote tag whose object or peel differs is a stop. Do not force it onto the admitted object.
- A receipt written in the same command as the push is not in force for that push. The hook reads the receipt before the command runs.
- A transport failure after a publish-path receipt is written still requires the receipt to be removed before the stop is reported.
- Do not approve an environment on the operator's behalf, including when the API says the current user can approve.
- Do not approve or cancel older waiting runs of the same workflow.

## Verification

```bash
python3 scripts/verify_release_tag.py \
  --repo-dir <checkout> \
  --tag <tag> \
  --tag-object <annotated-tag-sha> \
  --peeled-commit <admitted-commit-sha>
```

Add `--remote owner/name` before the push. Add `--require-remote` after it. The script prints one JSON object. Exit 0 is `MATCH`, exit 2 is `REMOTE_ABSENT`, exit 1 is a mismatch, exit 3 is a transport block.

## After use

This pack was compiled through `extract_expertise` and the compiler `enforcement-gates`. The `skill_intelligence_report` records activation and failure controls; it is not publication authority. When a run misses a trigger, false-triggers, or the operator corrects the transport, change the smallest signal in that report and rerun `validate_exemplary_skill.py`. Do not widen activation to cover source pull requests.
