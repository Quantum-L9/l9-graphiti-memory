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

# The locked environment `uv sync` creates, put first on PATH for every recipe
# the way CI's "Put uv venv on PATH" step does.
VENV := $(CURDIR)/.venv
export PATH := $(VENV)/bin:$(PATH)
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

# CI installs uv with astral-sh/setup-uv and pins no uv version (the action's
# default resolves the latest release), so uv is installed only when absent,
# unpinned the same way, into an untracked bootstrap environment under build/.
# Set UV_VERSION to pin one.
UV_VERSION ?=
UV_BOOTSTRAP := $(CURDIR)/build/uv-bootstrap
UV_REQUIREMENT := uv$(if $(UV_VERSION),==$(UV_VERSION))

.PHONY: \
	repo-setup \
	repo-validate \
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
repo-validate: repo-check repo-test-active ## check, active-memory tests, scripts/validate_release.sh
	bash scripts/validate_release.sh
