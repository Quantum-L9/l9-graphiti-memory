# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_group_resolver.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

import subprocess
from pathlib import Path

import pytest
import yaml

from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.group_resolver import load_registry, resolve_group


def test_packaged_registry_is_available() -> None:
    registry = load_registry(MemorySettings())
    assert "l9-graphiti-memory" in registry["repos"]


def test_explicit_group_is_deterministic(tmp_path: Path) -> None:
    result = resolve_group(tmp_path, explicit="repo-a", settings=MemorySettings())
    assert result.group_id == "repo-a"
    assert not result.readonly


def test_forbidden_group_is_readonly(tmp_path: Path) -> None:
    result = resolve_group(tmp_path, explicit="main", settings=MemorySettings())
    assert result.group_id is None
    assert result.readonly


def test_local_resolution_does_not_grant_admin_by_default(tmp_path: Path) -> None:
    from l9_graphite_memory.runtime import local_principal_for_resolution

    settings = MemorySettings()
    resolution = resolve_group(tmp_path, explicit="repo-a", settings=settings)
    principal = local_principal_for_resolution(settings, resolution)
    assert principal.write_namespaces == ("repo-a",)
    assert principal.is_admin is False


def test_local_admin_requires_explicit_setting(tmp_path: Path) -> None:
    from l9_graphite_memory.runtime import local_principal_for_resolution

    settings = MemorySettings(local_is_admin=True)
    resolution = resolve_group(tmp_path, explicit="repo-a", settings=settings)
    principal = local_principal_for_resolution(settings, resolution)
    assert principal.is_admin is True


def test_configured_local_namespaces_constrain_explicit_group_id(
    tmp_path: Path,
) -> None:
    """Issue #20: --group-id must not widen configured local_write_namespaces."""
    from l9_graphite_memory.authz import NamespacePolicy
    from l9_graphite_memory.contracts import AuthorizationAction
    from l9_graphite_memory.errors import AuthorizationError
    from l9_graphite_memory.runtime import local_principal_for_resolution

    settings = MemorySettings(
        local_principal_id="restricted-agent",
        local_agent_id="restricted-agent",
        local_is_admin=False,
        local_read_namespaces=("l9-graphiti-memory",),
        local_write_namespaces=("l9-graphiti-memory",),
        local_promote_namespaces=(),
    )
    resolution = resolve_group(tmp_path, explicit="some-disallowed-namespace", settings=settings)
    principal = local_principal_for_resolution(settings, resolution)

    assert principal.is_admin is False
    assert principal.write_namespaces == ("l9-graphiti-memory",)
    assert principal.read_namespaces == ("l9-graphiti-memory",)
    assert "some-disallowed-namespace" not in principal.write_namespaces

    policy = NamespacePolicy()
    denied = policy.evaluate(principal, AuthorizationAction.WRITE, "some-disallowed-namespace")
    assert denied.allowed is False
    assert "principal is administrator" not in denied.reasons
    assert any("did not match" in reason for reason in denied.reasons)

    allowed = policy.require(principal, AuthorizationAction.WRITE, "l9-graphiti-memory")
    assert allowed.allowed is True

    with pytest.raises(AuthorizationError):
        policy.require(principal, AuthorizationAction.WRITE, "some-disallowed-namespace")


# ---------------------------------------------------------------------------
# RECON-0 allowlist (2026-10-12): every listed repository is an exact-remote
# namespace address. Registration is not a grant.
# ---------------------------------------------------------------------------

RECON_0_NAMESPACES = {
    "Quantum-L9/.github": "quantum-l9-github",
    "Quantum-L9/Cognitive.Engine.Graphs": "cognitive-engine-graphs",
    "Quantum-L9/Constellation.Gate": "constellation-gate",
    "Quantum-L9/Cursor-Governance": "cursor-governance",
    "Quantum-L9/Enrichment.Inference.Engine": "enrichment-inference-engine",
    "Quantum-L9/Gate_SDK": "gate-sdk",
    "Quantum-L9/IdeaOS": "ideaos",
    "Quantum-L9/SEO-Bot": "seo-bot",
    "Quantum-L9/SplitWisely.ai": "splitwisely-ai",
    "Quantum-L9/Website-Bot": "website-bot",
    "Quantum-L9/l9-assurance": "l9-assurance",
    "Quantum-L9/l9-campaign-execution": "l9-campaign-execution",
    "Quantum-L9/l9-ci-core": "l9-ci-core",
    "Quantum-L9/l9-ci-debt-intelligence": "l9-ci-debt-intelligence",
    "Quantum-L9/l9-ci-debt-lsp": "l9-ci-debt-lsp",
    "Quantum-L9/l9-ci-debt-resolver": "l9-ci-debt-resolver",
    "Quantum-L9/l9-ci-sdk": "l9-ci-sdk",
    "Quantum-L9/l9-cognitive-runtime": "l9-cognitive-runtime",
    "Quantum-L9/l9-constellation-topology": "l9-constellation-topology",
    "Quantum-L9/l9-graphiti-memory": "l9-graphiti-memory",
    "Quantum-L9/l9-harness": "l9-harness",
    "Quantum-L9/l9-learning-foundry": "l9-learning-foundry",
    "Quantum-L9/l9-meta-injector": "l9-meta-injector",
    "Quantum-L9/l9-observability-core": "l9-observability-core",
    "Quantum-L9/l9-pr-repair": "pr-repair",
    "Quantum-L9/l9-repo-template": "l9-repo-template",
    "Quantum-L9/l9-revops": "l9-revops",
    "Quantum-L9/l9-semantic-compiler-engine": "l9-semantic-compiler-engine",
    "Quantum-L9/l9-state": "l9-state",
    "Quantum-L9/l9-wip": "l9-wip",
    "cryptoxdog/IB-Odoo_19": "ib-odoo-19",
}

# The four mappings that predate the RECON-0 allowlist; never renamed.
PRE_RECON_NAMESPACES = {
    "l9-graphiti-memory": "Quantum-L9/l9-graphiti-memory",
    "cursor-governance": "Quantum-L9/Cursor-Governance",
    "cognitive-engine-graphs": "Quantum-L9/Cognitive.Engine.Graphs",
    "l9-node-template": "Quantum-L9/L9-Node-Template",
}

REPO_ROOT = Path(__file__).resolve().parents[2]
RECON_ITEMS = sorted(RECON_0_NAMESPACES.items())


def _checkout(path: Path, remote: str | None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    if remote is not None:
        subprocess.run(["git", "-C", str(path), "remote", "add", "origin", remote], check=True)
    return path


def _remote_forms(owner_repo: str) -> list[str]:
    return [
        f"https://github.com/{owner_repo}",
        f"https://github.com/{owner_repo}.git",
        f"git@github.com:{owner_repo}.git",
        f"ssh://git@github.com/{owner_repo}.git",
        f"http://local_proxy@127.0.0.1:8080/git/{owner_repo}",
    ]


def test_registry_copies_have_equal_repos_maps() -> None:
    packaged = load_registry(MemorySettings())
    config = yaml.safe_load((REPO_ROOT / "config" / "group_registry.yaml").read_text("utf-8"))
    assert packaged["repos"] == config["repos"]


def test_recon_allowlist_is_registered_one_to_one() -> None:
    repos = load_registry(MemorySettings())["repos"]
    by_github: dict[str, list[str]] = {}
    for slug, entry in repos.items():
        by_github.setdefault(entry["github"], []).append(slug)
    for owner_repo, slug in RECON_0_NAMESPACES.items():
        assert by_github.get(owner_repo) == [slug], owner_repo


def test_pre_recon_mappings_are_preserved() -> None:
    repos = load_registry(MemorySettings())["repos"]
    for slug, owner_repo in PRE_RECON_NAMESPACES.items():
        assert repos[slug]["github"] == owner_repo


@pytest.mark.parametrize(
    ("owner_repo", "slug"), RECON_ITEMS, ids=[f"r{i:02d}" for i in range(len(RECON_ITEMS))]
)
def test_every_recon_remote_form_resolves_to_its_unique_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, owner_repo: str, slug: str
) -> None:
    monkeypatch.delenv("L9_MEMORY_NAMESPACE", raising=False)
    monkeypatch.delenv("GRAPHITI_GROUP_ID", raising=False)
    checkout_name = owner_repo.split("/", 1)[1]
    for index, remote in enumerate(_remote_forms(owner_repo)):
        # Both a neutral directory and the conventional clone directory name.
        for directory in (f"neutral{index}", f"clone{index}/{checkout_name}"):
            result = resolve_group(
                _checkout(tmp_path / directory, remote), settings=MemorySettings()
            )
            assert result.group_id == slug, (remote, directory, result)
            assert result.matches == (slug,)
            assert result.readonly is False


def test_nested_dot_github_directory_is_not_the_dot_github_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("L9_MEMORY_NAMESPACE", raising=False)
    monkeypatch.delenv("GRAPHITI_GROUP_ID", raising=False)
    settings = MemorySettings()

    seo = _checkout(tmp_path / "SEO-Bot", "https://github.com/Quantum-L9/SEO-Bot.git")
    nested = seo / ".github" / "workflows"
    nested.mkdir(parents=True)
    assert resolve_group(nested, settings=settings).group_id == "seo-bot"

    orphan = tmp_path / "unregistered" / ".github" / "workflows"
    orphan.mkdir(parents=True)
    _checkout(tmp_path / "unregistered", None)
    unresolved = resolve_group(orphan, settings=settings)
    assert unresolved.group_id != "quantum-l9-github"
    assert unresolved.readonly is True
    assert unresolved.method == "fallback_readonly"

    real = _checkout(tmp_path / ".github", "https://github.com/Quantum-L9/.github")
    assert resolve_group(real, settings=settings).group_id == "quantum-l9-github"


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/someone-else/.github",
        "https://github.com/Quantum-L9/.github-mirror",
        "https://github.com/Quantum-L9/l9-state-machine",
        "https://github.com/Quantum-L9/l9-ci-core-fork.git",
        "git@github.com:not-Quantum-L9/l9-ci-core.git",
        "https://github.com/evil/Quantum-L9-l9-wip",
        "https://github.com/Quantum-L9/l9-revops2",
        "https://github.com/Quantum-L9/IdeaOS/extra",
        "https://github.com/cryptoxdog/IB-Odoo_19-archive",
    ],
)
def test_lookalike_remote_does_not_borrow_a_recon_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: str
) -> None:
    monkeypatch.delenv("L9_MEMORY_NAMESPACE", raising=False)
    monkeypatch.delenv("GRAPHITI_GROUP_ID", raising=False)
    result = resolve_group(_checkout(tmp_path / "neutral", remote), settings=MemorySettings())
    assert result.group_id not in set(RECON_0_NAMESPACES.values())
    assert result.readonly is True


def test_ambiguous_path_without_remote_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("L9_MEMORY_NAMESPACE", raising=False)
    monkeypatch.delenv("GRAPHITI_GROUP_ID", raising=False)
    path = tmp_path / "Cursor-Governance" / "l9-graphiti-memory"
    _checkout(path, None)
    result = resolve_group(path, settings=MemorySettings())
    assert result.group_id is None
    assert result.readonly is True
    assert result.error is not None and "ambiguous" in result.error


def test_recon_directory_name_without_remote_does_not_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """New entries carry no path hint: a bare directory name is not evidence."""

    monkeypatch.delenv("L9_MEMORY_NAMESPACE", raising=False)
    monkeypatch.delenv("GRAPHITI_GROUP_ID", raising=False)
    pre_recon = set(PRE_RECON_NAMESPACES)
    for owner_repo, slug in RECON_ITEMS:
        if slug in pre_recon:
            continue
        path = _checkout(tmp_path / owner_repo.replace("/", "__") / owner_repo.split("/")[1], None)
        result = resolve_group(path, settings=MemorySettings())
        assert result.group_id != slug, owner_repo
        assert result.readonly is True
