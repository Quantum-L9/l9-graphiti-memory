# ADR-101: Derived Suite Validation Replaces the V-001 Pass-Count Pin

**Date:** 2026-11-02
**Decision owner:** Quantum-L9 memory architecture, from the operator decision of 2026-11-02
**Applies to:** release validation evidence check V-001 in `Quantum-L9/l9-graphiti-memory`

## Status

Accepted

## Context

V-001 is the release evidence check for the full test suite. Until this
record it was an exact pin: `tools/assurance/generate_validation_evidence.py`
passed V-001 only when the pytest log contained one literal count, last
`1959 passed`. More than seventy re-pins are recorded in that file's comment
history, each one hand arithmetic over collected tests and CI skips.

The pin protected three things:

- a run with a failure was unlikely to print the exact count;
- a test silently lost (deleted, or no longer collected) lowered the count;
- a CI environment that lost a backend service (PostgreSQL, Redis) skipped
  that service's legs and lowered the count.

It also had costs that grew with the suite:

- every pull request that added a test edited the same line, so any two such
  pull requests conflicted, and resolving the conflict by picking one side's
  number was always wrong;
- the count was a property of the environment as much as of the suite, so a
  local run could never pass without reproducing CI exactly;
- the pin checked only one substring. `1959 passed, 1 failed` matched it, as
  did a run in which skips silently replaced passes elsewhere.

`AGENTS.md` invariant 8 ("no release claim without executable validation")
requires V-001 to stay executable evidence. It does not require a pinned
count.

## Decision

V-001 is derived from the run instead of compared with a number. It passes
only when all four rules hold, judged from inputs the release script writes
into the evidence root and from two declarations committed in the candidate.

**Inputs.** `scripts/validate_release.sh` writes:

- `logs/pytest.txt`: the full run's terminal output (pytest's `-ra` summary);
- `logs/pytest_junit.xml`: the same run's JUnit report (`--junitxml`);
- `logs/pytest_collect.txt`: `pytest --collect-only -q` at the candidate;
- `logs/suite_base.txt`: the merge-base of `HEAD` with `L9_SUITE_BASE_REF`
  (default `origin/main`), or `UNRESOLVED: <reason>`;
- `logs/pytest_collect_base.txt`: `pytest --collect-only -q` over the
  merge-base tree, exported read-only with `git archive` into the temporary
  root and collected in the same environment.

The declarations are `tools/assurance/suite_skip_allowlist.json` (schema
`l9.suite-skip-allowlist/v1`) and `tools/assurance/suite_declared_removals.json`
(schema `l9.suite-declared-removals/v1`).

**Rules.**

1. Zero failed and zero errors: in the terminal summary, in every JUnit case,
   and in collection.
2. Accounting closes: every collected node id has a reported outcome in the
   JUnit report, every reported case was collected (a module-level collection
   skip excepted), and the terminal summary's passed, skipped and xfailed
   counts equal the JUnit report's.
3. Every skip reason is declared: each skipped case's reason must fully match
   an allow-list entry of kind `skip` whose profiles include the active one.
   Each entry carries an id, a regular expression, its profiles, and a
   justification.
4. The collected set does not shrink: a node id collected at the merge-base
   but not at the candidate fails, unless the declared-removals file names it
   with a reason.

**xfail and xpass.** An xfailed case is treated like a skip of kind `xfail`
and must match an `xfail` entry; none are declared, so any xfail fails. Any
xpass fails: a non-strict xpass is a passing JUnit case, so rule 1 reads the
terminal summary's `xpassed` count, and rule 2's count comparison disagrees
as well; a strict xpass is a failure.

**Profiles.** The active profile is `L9_SUITE_PROFILE`, default `ci`. The
`ci` profile admits only the skips CI's service-backed validate job is
expected to produce (no Neo4j, no Graphiti endpoint, no Cursor-Governance
checkout, no constellation SDK, no server control for outage cases). A skip
for a missing PostgreSQL DSN, Redis URL, semantic authority, or locked extra
is admitted only by the explicit `local` profile. This keeps the protection
the pin gave against a CI environment that silently lost a service.

**Fail closed.** A violated rule is FAIL. A missing, unreadable, or malformed
input, an unknown profile, an unresolved merge-base, a base collection that
did not exit 0 or reported errors, or an empty base collection is UNKNOWN.
Neither is PASS, and either blocks the release report.

**Without git history.** Where git is absent, the directory is not a work
tree, the base ref does not resolve, or `HEAD` has no merge-base with it, the
release script records `UNRESOLVED` with the reason and V-001 is UNKNOWN. A
local clone without `origin/main` can name another base with
`L9_SUITE_BASE_REF`. CI's validate job checks out with `fetch-depth: 0`, which
fetches every branch, so `origin/main` resolves there; on a pull request the
merge-base of the merge ref with `origin/main` is the current main tip.

The exact-count comment history in the generator is deleted and replaced by
a pointer to this record.

## Alternatives Considered

### Option A: Keep the exact pin and re-pin on every pull request

- Pros: no new mechanism; the count is easy to read
- Cons: every test-adding pull request conflicts with every other; the
  number cannot be produced locally; the substring match accepts a failing run

### Option B: A committed, tracked list of every collected node id

- Pros: exact, and shrinkage is a visible diff
- Cons: a hand-maintained inventory of about two thousand lines that every
  test-adding pull request edits, which is the same conflict class; ADR-099
  retired tracked inventories for this reason

### Option C: A minimum count instead of an exact one

- Pros: additions no longer conflict
- Cons: a deleted test offset by an added one passes; skips replacing passes
  pass; failures are still read from a substring

### Option D: Derived rules over the run's machine-readable outcomes, with a base comparison

- Pros: no number to maintain; failures, unaccounted tests, undeclared skips,
  and lost tests each fail on their own; the declarations change only when a
  skip reason or a removal is genuinely new
- Cons: depends on git history for the base comparison; the allow-list must be
  edited when a new skip reason is introduced

## Rejected Alternatives

Options A, B and C are rejected for the reasons above. Option D is selected.

## Invariants

- V-001 is PASS only when all four rules are evaluated and hold.
- No input that is missing, unreadable, malformed, or undeterminable yields
  PASS.
- A skip reason not on the allow-list for the active profile fails V-001.
- A node id collected at the merge-base and not at the candidate fails V-001
  unless declared removed.
- No pass count is maintained by hand in the generator.
- `AGENTS.md` invariant 8 is preserved: V-001 remains executable validation
  evidence, and the release report still blocks on it.
- Release validation stays observational: the base tree is exported into the
  temporary root, and no tracked byte is written.

## Consequences

Adding tests no longer requires editing the generator, so the V-001 conflict
between concurrent pull requests disappears. Introducing a new skip reason,
removing a test, or adding an xfail now requires an explicit, reviewed entry
with a justification. A local `scripts/validate_release.sh` run without CI's
services fails V-001 under the default `ci` profile, as it did under the pin;
`L9_SUITE_PROFILE=local` makes that run diagnostic. The release script now
collects the suite twice more (candidate and merge-base), which costs a few
seconds of collection.

The allow-list's `ci` entries were derived from a CI-shaped local run
(PostgreSQL 16, Redis 7, the bound semantic authority, the validate job's
extras) and the suite's skip sites. If CI produces a skip reason not listed,
V-001 fails in CI, visibly, and the entry is added with its justification.

## Security Impact

None on runtime authorization, storage, or credentials. The base tree is read
with `git archive` and collected, which imports the base's test modules in the
validation environment, the same trust the candidate's own tests already
have; the base is a commit of this repository's default branch.

## Migration Impact

No runtime, schema, or client migration. Open pull requests that edit the
V-001 pin drop that hunk when they refresh from main; resolving a conflict by
choosing either side's number is never correct. Contract impact: release
validation evidence only. Wiring path: `scripts/validate_release.sh` writes
the inputs; `tools/assurance/generate_validation_evidence.py` evaluates them;
the two declaration files live beside the generator. V-003 is re-pinned to 101
for this record, as for every ADR.

## Validation Requirements

- `tests/regression/test_validation_evidence_v001.py` proves: a clean run
  passes where the retired pin would fail; a failure or an error fails while
  the retired pin's count is printed; an xpass and an undeclared xfail fail; a
  collected test without an outcome fails; a summary disagreeing with the
  JUnit report fails; an undeclared skip reason fails; a local-only skip fails
  in the `ci` profile; a dropped test fails without a declaration and passes
  with one; each missing input, an unresolved base, a failed base collection,
  a malformed allow-list, a truncated collection, and an unknown profile are
  never PASS; real pytest output is accounted for; and the release script's
  base resolution records `UNRESOLVED` without git history.
- `bash scripts/validate_release.sh` produces V-001 PASS in CI's environment.
- `python tools/assurance/validate_adrs.py` reports a contiguous ledger
  through ADR-101.

## Rollback Conditions

If the derived check proves unable to evaluate in CI (for example a base that
cannot be collected), the rollback is a new ADR, not a silent return to a
count. Reverting this change restores the pin at whatever count main then
collects, re-measured from a CI run; it never restores `1959` by assumption.

## Supersedes / Superseded By

Supersedes the exact pass-count pin for V-001 recorded in the
`generate_validation_evidence.py` comment history (no prior ADR recorded that
pin as a decision). ADR-021 (testing and adapter conformance) and ADR-022
(release, publishing, and rollback) are unchanged. Superseded by none.
