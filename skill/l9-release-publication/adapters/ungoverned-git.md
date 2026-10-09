<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: skill/l9-release-publication/adapters/ungoverned-git.md
layer: skill
owner: memory-control-plane
status: active
version: 2.6.0
updated: 2026-07-22
/L9_META -->

# Ungoverned git

Load this adapter only when the push is evaluated on a machine that does not have `ops/autonomy/first_publication_gate.py`.

## Decision change

Do not write a publish-path receipt. Do not set `L9_LOCAL_PUSH_AUTHORIZED`. Push the existing tag ref once:

```bash
git push origin refs/tags/<tag>
```

Still forbidden: `--force`, `--tags`, deleting the tag, and creating a new tag object through the host API.

## Unchanged

Local and remote identity checks still come from [verify_release_tag.py](../scripts/verify_release_tag.py). Environment approval, digest checks, and the host Release still follow the control plane. If the gate's presence cannot be determined, do not use this adapter; stop with transport `Unknown`.
