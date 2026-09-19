# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_class_vocabulary.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-09-19

"""One memory-class vocabulary, asserted where it can no longer drift.

Two alias tables used to disagree. ``lesson`` resolved to ``procedural``
through the operator CLI and to ``insight`` through ``memory.write_agent``, and
because ``memory.search`` filters on ``memory_classes``, a caller filtering
``["insight"]`` silently missed every lesson the other lane had written.
Nothing errored, which is what made it expensive to find.

These are structural assertions: they hold for whatever the table contains, so
adding a spelling cannot reintroduce the divergence without failing here.
"""

from __future__ import annotations

import pytest

from l9_graphite_memory.cli import _LEGACY_KIND_MAP, _memory_class
from l9_graphite_memory.contracts import MemoryClass
from l9_graphite_memory.contracts.class_vocabulary import (
    AGENT_WRITABLE_CLASSES,
    CLASS_ALIASES,
    agent_writable_class,
    agent_writable_summary,
    alias_summary,
    known_class_spellings,
    resolve_memory_class,
)
from l9_graphite_memory.mcp_tools import CANONICAL_TOOLS

# ---------------------------------------------------------------------------
# the table is single-source and resolves in one pass
# ---------------------------------------------------------------------------


def test_every_alias_targets_a_canonical_class() -> None:
    for spelling, target in CLASS_ALIASES.items():
        assert isinstance(target, MemoryClass), f"{spelling!r} does not target a MemoryClass"


def test_no_alias_points_at_another_alias() -> None:
    """Resolution is a single pass, so a chain would silently resolve wrong.

    ``error -> lesson -> procedural`` is the shape that hid here: the first hop
    landed on a key that was itself an alias, and only a second table made it
    reach a class at all.
    """

    for spelling, target in CLASS_ALIASES.items():
        assert target.value not in CLASS_ALIASES or CLASS_ALIASES[target.value] is target, (
            f"alias {spelling!r} targets {target.value!r}, which is itself an alias"
        )


def test_no_alias_shadows_a_canonical_spelling() -> None:
    """A canonical value must never be re-pointed by the alias table."""

    canonical = {member.value for member in MemoryClass}
    for spelling in CLASS_ALIASES:
        assert spelling not in canonical, f"{spelling!r} is a class and must not be aliased"


def test_canonical_values_resolve_to_themselves() -> None:
    for member in MemoryClass:
        assert resolve_memory_class(member.value) is member


def test_unknown_spelling_names_what_is_accepted() -> None:
    with pytest.raises(ValueError) as caught:
        resolve_memory_class("not-a-class")
    message = str(caught.value)
    assert "not-a-class" in message
    assert "lesson" in message


def test_known_spellings_are_exactly_classes_plus_aliases() -> None:
    expected = {member.value for member in MemoryClass} | set(CLASS_ALIASES)
    assert set(known_class_spellings()) == expected


# ---------------------------------------------------------------------------
# both lanes agree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spelling", sorted(CLASS_ALIASES) + [m.value for m in MemoryClass])
def test_cli_and_agent_lane_resolve_every_spelling_identically(spelling: str) -> None:
    """The assertion the two tables could not satisfy.

    Skipped only where the agent lane refuses the class outright, which is an
    authority decision rather than a vocabulary one.
    """

    resolved = resolve_memory_class(spelling)
    if resolved not in AGENT_WRITABLE_CLASSES:
        pytest.skip(f"{resolved.value} is not writable on the agent lane")
    assert agent_writable_class(spelling) is resolved
    assert _memory_class(spelling) is resolved


def test_lesson_is_procedural_on_every_lane() -> None:
    """The specific divergence, named.

    ``procedural`` is the established meaning: the CLI has resolved it that way
    since the legacy kind map was introduced, and the corpus written through
    that lane already carries it.
    """

    assert resolve_memory_class("lesson") is MemoryClass.PROCEDURAL
    assert agent_writable_class("lesson") is MemoryClass.PROCEDURAL
    assert _memory_class("lesson") is MemoryClass.PROCEDURAL


def test_cli_legacy_map_is_the_shared_table() -> None:
    """The CLI keeps its public name but no longer owns a second table."""

    assert _LEGACY_KIND_MAP is CLASS_ALIASES


@pytest.mark.parametrize("spelling", ["pickup", "pickup_context"])
def test_both_pickup_spellings_are_episodic_everywhere(spelling: str) -> None:
    """One lane spelled it ``pickup`` and the other rejected it outright.

    ``episodic`` rather than ``meta``: a continuation record is what a session
    resumes from, and the consumer has resolved ``pickup_context`` that way
    throughout. Taking the agent door's ``meta`` instead would have replaced
    one cross-lane divergence with another.
    """

    assert resolve_memory_class(spelling) is MemoryClass.EPISODIC
    assert _memory_class(spelling) is MemoryClass.EPISODIC
    assert agent_writable_class(spelling) is MemoryClass.EPISODIC


# ---------------------------------------------------------------------------
# the agent-lane allowlist is closed under the alias table
# ---------------------------------------------------------------------------


def test_every_alias_target_is_writable_on_the_agent_lane() -> None:
    """Closure. Half the bug was an alias resolving to a refused class.

    ``lesson`` resolved to ``procedural`` on the CLI while ``procedural`` was
    absent from the agent allowlist, so the agent lane could not emit the class
    the operator lane routed every lesson into, and the two could not produce a
    comparable corpus.
    """

    for spelling, target in CLASS_ALIASES.items():
        assert target in AGENT_WRITABLE_CLASSES, (
            f"alias {spelling!r} resolves to {target.value!r}, which the agent lane refuses"
        )


def test_identity_is_the_only_class_the_agent_lane_refuses() -> None:
    refused = set(MemoryClass) - AGENT_WRITABLE_CLASSES
    assert refused == {MemoryClass.IDENTITY}


def test_refused_class_is_reported_as_authority_not_as_a_typo() -> None:
    with pytest.raises(ValueError) as caught:
        agent_writable_class("identity")
    message = str(caught.value)
    assert "identity" in message
    assert "does not accept" in message


# ---------------------------------------------------------------------------
# the description an agent reads is generated, not hand-kept
# ---------------------------------------------------------------------------


def test_write_agent_description_is_generated_from_the_table() -> None:
    """A fourth hand-maintained copy is how the first three drifted apart."""

    description = next(
        item["description"] for item in CANONICAL_TOOLS if item["name"] == "memory.write_agent"
    )
    assert agent_writable_summary() in description
    assert alias_summary() in description


def test_description_never_advertises_a_refused_class() -> None:
    description = next(
        item["description"] for item in CANONICAL_TOOLS if item["name"] == "memory.write_agent"
    )
    assert "identity" not in description


def test_alias_summary_covers_the_whole_table() -> None:
    summary = alias_summary()
    for spelling, target in CLASS_ALIASES.items():
        assert f"{spelling}→{target.value}" in summary
