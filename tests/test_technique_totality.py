"""Coverage as a property of the tree: every ``TT_CATALOG`` member is explained
and cited, walked one by one rather than sampled.

``tests/test_technique_definitions.py`` pins the *shape* of a definition — a
populated summary implies steps and pitfalls — which stays true of a technique
nobody ever wrote a word about. These tests pin *totality*: add a technique to
a family in ``tt.py`` and ship it with an empty ``TechniqueContent`` and this
module names the key and the field that is missing.

Reachability (every member is used by a process or is a named extension) is
already asserted by ``tests/test_pmbok_tt_orphans.py`` and is deliberately not
repeated here.

The list of explanation fields is *derived* from ``TechniqueContent``'s own
dataclass fields rather than restated, so a field added to the content record
is required of every technique in the catalog the moment it exists — there is
no second list to keep in sync.
"""

from __future__ import annotations

import re
from dataclasses import fields

from driftless.pmbok import plain_language as pl
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.glossary import GLOSSARY
from driftless.pmbok.reasons import UNCITED_EXEMPTIONS
from driftless.pmbok.technique_content import TechniqueContent

#: The citation field, handled by its own tests below (a technique may be
#: uncited if it is exempt; it may never be unexplained).
CITATION_FIELD = "further_reading"

#: Every other ``TechniqueContent`` field, read off the dataclass itself.
EXPLANATION_FIELDS: tuple[str, ...] = tuple(
    field.name for field in fields(TechniqueContent) if field.name != CITATION_FIELD
)

# ``UNCITED_EXEMPTIONS`` — techniques allowed to carry no ``further_reading``,
# each with the reason it cannot honestly cite a clause — now lives in
# ``driftless.pmbok.reasons`` alongside the other two exemption dicts it
# shares a ``Reason`` shape with. This module still owns the checks below: it
# asserts the set *exactly equal* to the uncited set, so it fails both when a
# new technique ships uncited and when an entry there later gains a citation
# and should have been removed.

#: A PMBOK-6 clause reference: the edition, a section number in the edition's
#: real 1-13 range, and one to three dotted subdivisions (``§6.4.2.3``). It
#: pins the *shape* only — it cannot tell a real clause from a plausible one,
#: nor that the clause says what the technique claims. The checks below add what
#: the shape alone cannot: that the clause subdivides the tools-and-techniques
#: list, and that no two techniques claim one leaf.
CLAUSE_REFERENCE = re.compile(r"^PMBOK-6 §(?:[1-9]|1[0-3])(?:\.\d{1,2}){1,3}$")


#: Citations whose four-component leaf clause is shared by more than one
#: technique, each with the reason the sharing is not a contradiction. PMBOK-6
#: numbers some tools-and-techniques bullets as a *group* (data gathering, data
#: analysis, decision making, interpersonal and team skills), and two members of
#: one such group legitimately land on the same number.
#:
#: This mapping is asserted *exactly equal* to the observed clause-to-techniques
#: sharing below, in both directions, so an unrecorded pair and a pair that has
#: since stopped sharing fail equally loudly. It is not a table of correct clause
#: numbers and must never become one: it records only which observed collisions
#: were judged benign.
SHARED_LEAF_EXEMPTIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "PMBOK-6 §5.2.2.2": (
        ("benchmarking", "focus_groups"),
        "Both are data-gathering techniques of the same requirements-collection "
        "process, and neither is named as a family heading the other sits under; a "
        "clause numbering the group is expected to carry both.",
    ),
    "PMBOK-6 §5.2.2.4": (
        ("autocratic_decision_making", "multicriteria_decision_analysis", "voting"),
        "All three are decision-making techniques of the same requirements-"
        "collection process; multicriteria decision analysis, autocratic decision "
        "making and voting are the ways that group decides, rather than separate "
        "numbered families.",
    ),
    "PMBOK-6 §7.4.2.2": (
        ("earned_value_analysis", "to_complete_performance_index"),
        "Both are data-analysis techniques of the same cost-control process, and "
        "the to-complete performance index is computed from the earned-value "
        "figures rather than standing apart from them.",
    ),
    "PMBOK-6 §9.5.2.1": (
        ("conflict_management", "influencing"),
        "Both are interpersonal-and-team-skills techniques of the same team-"
        "management process; the clause numbers that skills group rather than "
        "either skill on its own.",
    ),
    "PMBOK-6 §11.4.2.5": (
        ("decision_tree_analysis", "influence_diagrams", "sensitivity_analysis", "simulation"),
        "All four are data-analysis techniques of the same quantitative-risk-"
        "analysis process; PMBOK-6 lists them together under one Data analysis "
        "bullet rather than as separate numbered families.",
    ),
}

#: The position, within a dotted clause number, of the subdivision that says
#: which ITTO list the clause belongs to: PMBOK-6 numbers a process's Inputs
#: ``X.Y.1``, its Tools & Techniques ``X.Y.2`` and its Outputs ``X.Y.3``.
ITTO_COMPONENT_INDEX = 2

#: The value that subdivision must take for a clause that defines a technique.
TOOLS_AND_TECHNIQUES_COMPONENT = "2"

#: The number of dotted components in a clause that names one numbered bullet of
#: a process's tools-and-techniques list, e.g. ``§6.4.2.3`` — as opposed to the
#: whole list (``§12.1.2``) or the whole process (``§8.2``).
LEAF_COMPONENTS = 4


def _clause_components(citation: str) -> tuple[str, ...]:
    """The dotted components of a citation's clause number, e.g.
    ``("6", "4", "2", "3")`` for ``"PMBOK-6 §6.4.2.3"``. Returns an empty tuple
    for anything that does not carry a recognisable clause, so a malformed
    citation is left to
    ``test_every_citation_looks_like_a_pmbok_6_clause_reference`` to report
    rather than crashing the checks below."""
    if not CLAUSE_REFERENCE.fullmatch(citation):
        return ()
    _, clause = citation.split("§", 1)
    return tuple(clause.split("."))


def _cited_leaf_clauses() -> dict[str, tuple[str, ...]]:
    """Every leaf clause cited anywhere, mapped to the techniques citing it."""
    citing: dict[str, list[str]] = {}
    for key, definition in sorted(TECHNIQUES.items()):
        for citation in definition.further_reading:
            if len(_clause_components(citation)) == LEAF_COMPONENTS:
                citing.setdefault(citation, []).append(key)
    return {clause: tuple(keys) for clause, keys in citing.items()}


def test_the_fields_being_walked_were_actually_derived() -> None:
    """Guards the derivation above: were it to yield nothing, every totality
    test below would pass vacuously over an empty field list."""
    assert EXPLANATION_FIELDS
    assert CITATION_FIELD in {field.name for field in fields(TechniqueContent)}
    assert TECHNIQUES


def test_every_technique_is_explained_in_every_content_field() -> None:
    gaps: list[str] = []
    for key, definition in sorted(TECHNIQUES.items()):
        for name in EXPLANATION_FIELDS:
            value = getattr(definition, name)
            if isinstance(value, tuple):
                if not value:
                    gaps.append(f"{key}.{name} is empty")
                gaps.extend(
                    f"{key}.{name}[{index}] is blank"
                    for index, element in enumerate(value)
                    if not element.strip()
                )
            elif not value.strip():
                gaps.append(f"{key}.{name} is blank")
    assert not gaps, (
        "every technique must be explained; write content for these in the "
        "matching driftless/pmbok/technique_content/<family>.py module:\n" + "\n".join(gaps)
    )


def test_every_technique_summary_is_one_short_jargon_free_sentence() -> None:
    """``summary`` is the one sentence a newcomer meets first, so it is held to
    the same plain-language rule as ``ARTIFACTS``' and ``PROCESS_DEFINITIONS``'
    ``plain_summary`` -- one rule, imported from ``plain_language``, never a
    restated copy. The other explanation fields (``when_to_use``, ``steps``,
    ``worked_example``, ...) stay deep-dive prose and may keep the technique's
    own terms of art and acronyms."""
    glossary_keys = frozenset(GLOSSARY)
    violations: list[str] = []
    for key, definition in sorted(TECHNIQUES.items()):
        violations.extend(
            f"{key}: {violation}"
            for violation in pl.violations(definition.summary, glossary_keys=glossary_keys)
        )
    assert not violations, (
        "summary must be one short sentence a newcomer can follow, with no "
        "acronyms and no raw identifiers:\n" + "\n".join(violations)
    )


def test_no_technique_field_leaks_a_raw_snake_case_identifier() -> None:
    gaps: list[str] = []
    for key, definition in sorted(TECHNIQUES.items()):
        for name in EXPLANATION_FIELDS:
            value = getattr(definition, name)
            for index, text in enumerate(value if isinstance(value, tuple) else (value,)):
                gaps += [f"{key}.{name}[{index}]: {tok!r}" for tok in pl.snake_identifiers(text)]
    assert not gaps, "no technique field may leak a raw identifier:\n" + "\n".join(gaps)


def test_no_technique_ships_uncited_without_an_exemption() -> None:
    uncited = {key for key, definition in TECHNIQUES.items() if not definition.further_reading}
    unexplained = sorted(uncited - set(UNCITED_EXEMPTIONS))
    assert not unexplained, (
        f"{unexplained} carry no further_reading — cite the PMBOK-6 clause that "
        "defines each, or add it to UNCITED_EXEMPTIONS with the reason it cannot "
        "be cited"
    )


def test_no_exemption_outlives_the_gap_it_covers() -> None:
    """An exemption list that only ever grows stops meaning anything."""
    uncited = {key for key, definition in TECHNIQUES.items() if not definition.further_reading}
    stale = sorted(set(UNCITED_EXEMPTIONS) - uncited)
    assert not stale, (
        f"{stale} are listed in UNCITED_EXEMPTIONS but are not uncited techniques — "
        "each has since gained a further_reading citation, or its key no longer "
        "exists; delete the entry"
    )


def test_every_exemption_names_a_real_technique_and_a_reason() -> None:
    for key, reason in sorted(UNCITED_EXEMPTIONS.items()):
        assert key in TECHNIQUES, f"{key} is exempt from citation but is not a technique"
        assert reason.why.strip(), f"{key} is exempt from citation with no reason given"


def test_every_citation_looks_like_a_pmbok_6_clause_reference() -> None:
    malformed: list[str] = []
    for key, definition in sorted(TECHNIQUES.items()):
        malformed.extend(
            f"{key}: {entry!r}"
            for entry in definition.further_reading
            if not CLAUSE_REFERENCE.fullmatch(entry)
        )
    assert not malformed, (
        "further_reading carries edition-plus-clause references only, e.g. "
        f"'PMBOK-6 §6.4.2.3' — these do not match {CLAUSE_REFERENCE.pattern}:\n"
        + "\n".join(malformed)
    )


def test_the_citation_checks_below_are_walking_real_citations() -> None:
    """Guards the two derivations above: were the parser to stop recognising a
    clause, every citation check below would pass over an empty collection."""
    assert _clause_components("PMBOK-6 §6.4.2.3") == ("6", "4", "2", "3")
    assert _clause_components("PMBOK-6 §8.2") == ("8", "2")
    assert _clause_components("not a citation") == ()
    assert _cited_leaf_clauses()


def test_no_citation_places_a_technique_outside_a_tools_and_techniques_clause() -> None:
    """PMBOK-6 numbers a process's Inputs ``X.Y.1``, its Tools & Techniques
    ``X.Y.2`` and its Outputs ``X.Y.3``. A technique is therefore defined under
    ``.2.`` and nowhere else, so a citation subdividing ``.1.`` or ``.3.`` is
    provably pointing at the wrong list — decidable from the number itself,
    without any table of which clause is correct."""
    misplaced: list[str] = []
    for key, definition in sorted(TECHNIQUES.items()):
        for citation in definition.further_reading:
            components = _clause_components(citation)
            if len(components) <= ITTO_COMPONENT_INDEX:
                continue
            if components[ITTO_COMPONENT_INDEX] != TOOLS_AND_TECHNIQUES_COMPONENT:
                misplaced.append(f"{key}: {citation}")
    assert not misplaced, (
        "a technique can only be defined under a process's tools-and-techniques "
        f"subsection (component {ITTO_COMPONENT_INDEX + 1} of the clause number is "
        f"{TOOLS_AND_TECHNIQUES_COMPONENT!r}) — these cite an inputs or outputs "
        "subsection, so the clause number is wrong. Establish the right one from "
        "the edition, or blank the citation and add the key to "
        "UNCITED_EXEMPTIONS:\n" + "\n".join(misplaced)
    )


def test_no_two_techniques_share_a_leaf_clause_without_a_recorded_reason() -> None:
    """Two separately numbered bullets of one tools-and-techniques list cannot
    carry the same number, so a shared leaf clause means at least one of the two
    citations is wrong — unless the sharing is a known-benign group clause, in
    which case SHARED_LEAF_EXEMPTIONS records the pair and why."""
    shared = {clause: keys for clause, keys in _cited_leaf_clauses().items() if len(keys) > 1}
    unrecorded = sorted(set(shared) - set(SHARED_LEAF_EXEMPTIONS))
    assert not unrecorded, (
        f"{unrecorded} are each cited by more than one technique "
        f"({ {clause: shared[clause] for clause in unrecorded} }) — at least one "
        "citation in each collision is wrong. Blank the ones that cannot be "
        "established (adding their keys to UNCITED_EXEMPTIONS), or record the "
        "collision in SHARED_LEAF_EXEMPTIONS with the reason it is benign."
    )


def test_no_shared_leaf_exemption_outlives_the_collision_it_covers() -> None:
    """The mirror of the check above: an exemption list that only ever grows
    stops meaning anything."""
    shared = {clause: keys for clause, keys in _cited_leaf_clauses().items() if len(keys) > 1}
    stale = sorted(set(SHARED_LEAF_EXEMPTIONS) - set(shared))
    assert not stale, (
        f"{stale} are recorded in SHARED_LEAF_EXEMPTIONS but no longer cited by "
        "more than one technique — delete the entry"
    )
    drifted = sorted(
        clause
        for clause, keys in shared.items()
        if clause in SHARED_LEAF_EXEMPTIONS and SHARED_LEAF_EXEMPTIONS[clause][0] != keys
    )
    assert not drifted, (
        f"{drifted} are recorded in SHARED_LEAF_EXEMPTIONS for one set of "
        "techniques and are now cited by another "
        f"({ {clause: shared[clause] for clause in drifted} }) — the reason was "
        "written about the old pair, so re-judge the collision and rewrite it"
    )


def test_every_shared_leaf_exemption_names_real_techniques_and_a_reason() -> None:
    for clause, (keys, reason) in sorted(SHARED_LEAF_EXEMPTIONS.items()):
        assert CLAUSE_REFERENCE.fullmatch(clause), f"{clause!r} is not a clause reference"
        assert len(_clause_components(clause)) == LEAF_COMPONENTS, (
            f"{clause} is not a leaf clause, so it cannot be a leaf collision"
        )
        assert len(keys) > 1, f"{clause} is exempt from a collision involving one technique"
        assert tuple(sorted(keys)) == keys, f"{clause}'s techniques are not sorted"
        for key in keys:
            assert key in TECHNIQUES, f"{clause} is exempt for {key}, which is not a technique"
        assert reason.strip(), f"{clause} is exempt with no reason given"
