<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: skill/l9-release-publication/references/publication-plane.md
layer: skill
owner: memory-control-plane
status: active
version: 2.6.0
updated: 2026-07-22
/L9_META -->

# Publication plane

Read `ops/autonomy/first_publication_gate.py` and `ops/autonomy/breakglass_receipt.py` in the governance checkout before pushing. The rules below are the observed behavior of those files. If the files disagree with this note, the files win and this note is stale.

## What the gate classifies

A `git push` of `refs/tags/<tag>` has no open pull request for that ref. The gate treats it as a first publication and denies it. `PR_REMEDIATE=0 make pr` is the branch path. Its inner push is `git push -u origin HEAD`. It cannot publish an annotated tag. Opening another source pull request does not move the tag.

## What the hook can see

`breakglass_reason()` allows the push when it returns a non-empty reason. It returns immediately when `L9_LOCAL_PUSH_AUTHORIZED` is set in the hook process. A variable prefix on the pushed command is not that process environment. The hook also accepts `active_publish_path_reason()`, which reads the receipt file, default `~/.l9/autonomy/publish-path-override.json`.

## Authorized push

Write the receipt only after the operator has ordered publication of the already-verified tag object. Run the write by itself:

```bash
python3 ops/autonomy/breakglass_receipt.py \
  --write --issuer ops --hours 1 \
  --reason 'publish existing annotated tag <tag> object <tag-object> peeled <commit>; no force, no recreate'
```

Confirm the status line says the grant is in force. The verifier must already have been run with `--remote owner/name --bind-origin`, and that result must be `REMOTE_ABSENT` or `MATCH` for the same `owner/name`. `--bind-origin` fails when `origin` is a different repository. Do not push until that check passes.

Then, in a later command, push exactly one ref to that bound origin:

```bash
git push origin refs/tags/<tag>
```

Do not join the write and the push with `&&` or any other single shell command. The publication-plane hook inspects the push before that command runs, so a receipt created inside the same command does not exist yet. A `L9_LOCAL_PUSH_AUTHORIZED` prefix on the push is also invisible to the hook.

No `--force`, no `--tags`, no tag rewrite. Delete the receipt as soon as the push command returns, including when the push fails or the hook rejects it:

```bash
rm -f ~/.l9/autonomy/publish-path-override.json
python3 ops/autonomy/breakglass_receipt.py --status
```

Confirm the status says no publish-path breakglass is in force.

## Denied substitutes

- Recreating the tag with the host API. A new tag object has a different SHA even when the message looks the same.
- Pointing `refs/tags/<tag>` at a SHA that is not already the admitted tag object.
- Leaving the receipt in place after the attempt.
- Using the receipt to push anything other than that one tag ref.
