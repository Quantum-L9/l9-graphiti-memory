# l9-graphiti-memory repository-owned Make implementation.
#
# REPOSITORY-OWNED: hand-maintained, never generated, never rewritten by Core's
# repository-execution reconcile. The root Makefile is Core's generated make-v1
# facade (Quantum-L9/l9-ci-core tools/l9_repo/facades/make-v1.mk); it routes
# setup / validate / check / test to the repo-* leaves below and runs every
# recipe under `bash -eu -o pipefail -c`.
#
# The leaves reproduce what .github/workflows/ci.yml's `validate` job runs, in
# its order, so `make <phase>` and CI cannot drift apart silently:
#
#   setup    -> the job's "Sync locked environment" step
#   check    -> ruff check, mypy, the active-memory public API gate, and the
#               scripts/validate_release.sh assurance validators that need no
#               external service
#   test     -> the full pytest suite (the run scripts/validate_release.sh and
#               the coverage step make)
#   validate -> check, then the active-memory subsystem tests, then
#               scripts/validate_release.sh, exactly as the CI job sequences them
#
# Core runs each phase as its own `make` process, so nothing here relies on
# state a previous phase exported: every phase puts the locked environment on
# PATH itself. Without PostgreSQL, Redis, Neo4j or model keys the suite's
# existing environment-gated cases skip, as they do in CI's `validate` job for
# the backends it does not provide.
#
# This file implements no organization governance and no publication.

# CI installs uv with astral-sh/setup-uv and pins no uv version (the action's
# default resolves the latest release), so uv is installed only when absent,
# unpinned the same way, into an untracked bootstrap environment under build/.
# Set UV_VERSION to pin one.
UV_VERSION ?=
UV_BOOTSTRAP := $(CURDIR)/build/uv-bootstrap
UV_REQUIREMENT := uv$(if $(UV_VERSION),==$(UV_VERSION))

# The locked environment `uv sync` creates, put first on PATH for every recipe
# the way CI's "Put uv venv on PATH" step does.
#
# setup-uv also leaves uv itself on PATH for every later step of CI's validate
# job, and what runs there depends on it: the installed-wheel proofs
# (tests/integration/remote_mcp_harness.py, scripts/validate_release.sh)
# install the built wheel with `uv pip install --target`, and the venv
# `uv sync` creates carries no pip to fall back on. Core runs each phase as its
# own make process, so a uv that repo-setup had to bootstrap must be on PATH
# here, for every phase, or validate runs in a different environment from the
# one CI's job gives the same tests. It is appended, never prepended: a uv
# already on PATH still wins, and the bootstrap's own python and pip never
# shadow the locked environment's.
VENV := $(CURDIR)/.venv
export PATH := $(VENV)/bin:$(PATH):$(UV_BOOTSTRAP)/bin
export PYTHONPATH := $(CURDIR)/src

# The extras CI's `validate` job syncs. Changing one here and not in ci.yml (or
# the reverse) is drift.
UV_SYNC_EXTRAS := --extra dev --extra server --extra postgres --extra active --extra zep

# V-001 (ADR-101, tools/assurance/generate_validation_evidence.py) admits only
# the skip reasons declared in tools/assurance/suite_skip_allowlist.json for the
# selected profile. CI's validate job provides PostgreSQL, Redis and the pinned
# semantic authority and runs the strict default `ci` profile; Core runs these
# phases on a runner with none of them, which is what the repository's declared
# `local` profile (SKIP-101..104) exists for. No skip is added by this choice.
# A caller that provides CI's services sets L9_SUITE_PROFILE=ci to get the
# strict verdict through `make validate`.
L9_SUITE_PROFILE ?= local
export L9_SUITE_PROFILE

.PHONY: \
	repo-setup \
	repo-validate \
	repo-suite-base \
	repo-check \
	repo-test \
	repo-test-active

# ---------------------------------------------------------------------------
# Portable make-v1 ABI.
# ---------------------------------------------------------------------------
repo-setup: ## Sync the locked environment CI's validate job uses
	@uv_bin="$$(command -v uv || true)"; \
	if [ -z "$$uv_bin" ]; then \
		echo "uv not found; installing $(UV_REQUIREMENT) into $(UV_BOOTSTRAP)"; \
		python3 -m venv "$(UV_BOOTSTRAP)"; \
		"$(UV_BOOTSTRAP)/bin/python" -m pip install --quiet "$(UV_REQUIREMENT)"; \
		uv_bin="$(UV_BOOTSTRAP)/bin/uv"; \
	fi; \
	"$$uv_bin" --version; \
	"$$uv_bin" sync --frozen --no-install-project --no-build $(UV_SYNC_EXTRAS)

# The static steps of CI's validate job, then the assurance validators that
# scripts/validate_release.sh runs and that need no external service, in that
# script's order. The product-topology and ProductManifest checks are not here:
# they need the pinned semantic authority checkout (L9_SEMANTIC_AUTHORITY_ROOT),
# and scripts/validate_release.sh, run by repo-validate, owns that decision.
repo-check: ## ruff check, mypy, active-memory public API, assurance validators
	ruff check .
	mypy src/l9_graphite_memory
	python tools/assurance/check_active_memory_public_api.py
	python3 tools/assurance/validate_adrs.py
	python3 tools/assurance/validate_projection_manifests.py config/projections/facts-v8.yaml
	python3 tools/assurance/validate_harvest_coverage.py
	python3 tools/assurance/check_layer_boundaries.py
	python3 tools/assurance/check_recursive_alignment.py
	python3 tools/assurance/check_memory_write_bypass.py
	python3 tools/assurance/check_config_drift.py
	python3 tools/assurance/audit_package_wiring.py
	python3 tools/assurance/check_source_quality.py
	python3 tools/assurance/check_secrets.py

# CI's "Test active-memory subsystem" step.
repo-test-active: ## The active-memory subsystem tests CI runs as their own step
	pytest tests/unit/active tests/conformance/active tests/external_runtime -v

# The full suite, without writing a pytest cache into the tree.
repo-test: ## Run the full pytest suite
	pytest -q -p no:cacheprovider

# CI's validate job in its order: static gates, the active-memory subsystem
# tests, then release validation, which runs the full suite again together
# with the validators, the wheel build, the installed-wheel smoke and the
# evidence generation. The full suite therefore runs once here and once more in
# repo-test. That is deliberate: Core runs the phases as separate processes and
# a stamp that skipped a phase because another had passed would be the kind of
# coverage claim l9.contract/validation-and-correctness@1 forbids.
repo-validate: repo-suite-base repo-check repo-test-active ## base, check, active-memory tests, scripts/validate_release.sh
	bash scripts/validate_release.sh

# V-001 (ADR-101) compares the suite collected here with the suite collected at
# the merge-base of HEAD and L9_SUITE_BASE_REF (default origin/main), and an
# unresolvable base is UNRESOLVED, which fails the evidence check closed. CI's
# validate job has that base because it checks out with fetch-depth: 0. Core's
# repository execution checks out only the candidate revision, depth 1, with
# no origin/main ref, so this makes the same base resolvable first:
#
#   - a caller-set L9_SUITE_BASE_REF is honoured as given: it must already
#     resolve with a merge-base, or this fails (nothing here knows what to
#     fetch for an arbitrary ref);
#   - when the base already resolves and has a merge-base, nothing is fetched
#     (a full clone stays offline);
#   - otherwise refs/heads/main is fetched from origin into
#     refs/remotes/origin/main, unshallowing a shallow checkout so the
#     merge-base exists, and the result is re-checked;
#   - a failed fetch, or a base still without a merge-base, fails with the
#     reason. It never substitutes HEAD or skips the comparison.
#
# Without a git work tree (the release tarball) there is no base to make, and
# scripts/validate_release.sh records that itself.
SUITE_BASE_DEFAULT := origin/main

repo-suite-base: ## Make the V-001 merge-base (L9_SUITE_BASE_REF, default origin/main) resolvable
	@if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
		echo "suite base: no git work tree; scripts/validate_release.sh records the base as UNRESOLVED"; \
		exit 0; \
	fi; \
	ref="$${L9_SUITE_BASE_REF:-$(SUITE_BASE_DEFAULT)}"; \
	resolved() { git rev-parse --verify --quiet "$$ref^{commit}" >/dev/null && git merge-base HEAD "$$ref" >/dev/null 2>&1; }; \
	if resolved; then \
		echo "suite base: $$ref resolves; merge-base $$(git merge-base HEAD "$$ref")"; \
		exit 0; \
	fi; \
	if [ "$$ref" != "$(SUITE_BASE_DEFAULT)" ]; then \
		echo "suite base: L9_SUITE_BASE_REF=$$ref does not resolve to a commit with a merge-base with HEAD; fetch it or unset L9_SUITE_BASE_REF" >&2; \
		exit 1; \
	fi; \
	unshallow=""; \
	if [ "$$(git rev-parse --is-shallow-repository)" = "true" ]; then unshallow="--unshallow"; fi; \
	echo "suite base: fetching refs/heads/main from origin into refs/remotes/origin/main $${unshallow:+(unshallowing)}"; \
	if ! git fetch --no-tags $$unshallow origin "+refs/heads/main:refs/remotes/origin/main"; then \
		echo "suite base: fetching main from origin failed; V-001 needs the merge-base with origin/main (ADR-101). Fetch it, or set L9_SUITE_BASE_REF to a resolvable base" >&2; \
		exit 1; \
	fi; \
	if ! resolved; then \
		echo "suite base: origin/main was fetched but has no merge-base with HEAD" >&2; \
		exit 1; \
	fi; \
	echo "suite base: $$ref resolves; merge-base $$(git merge-base HEAD "$$ref")"
