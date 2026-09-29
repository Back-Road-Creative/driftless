"""Pins that ``TECHNIQUES`` is built *from* ``tt.FAMILIES``, so a technique can
never exist in one without the other by construction, not by developer
diligence — these tests guard the mechanism, not a human keeping two lists
in sync.

Fails on import before ``driftless.pmbok.definitions`` exists.
"""

from collections import Counter

import pytest

from driftless.assess.model import ASSISTANT_ROUTES
from driftless.naming import humanize
from driftless.pmbok import definitions
from driftless.pmbok.definitions import (
    EXTENSION_SOURCE,
    PMBOK_SOURCE,
    PMBOK_SOURCE_VERSION,
    TECHNIQUES,
    AssistanceMode,
    TechniqueDefinition,
)
from driftless.pmbok.tt import EXTENSIONS, FAMILIES, TT_CATALOG

_OVERRIDES = definitions._DISPLAY_NAME_OVERRIDES


def test_tt_catalog_and_techniques_match_in_both_directions() -> None:
    assert set(TECHNIQUES) == TT_CATALOG


def test_every_definition_has_a_usable_display_name_and_source() -> None:
    for key, definition in TECHNIQUES.items():
        assert isinstance(definition, TechniqueDefinition)
        assert definition.display_name and definition.display_name != key
        assert definition.source


def test_family_values_partition_the_catalog_exactly_like_families() -> None:
    sizes = Counter(definition.family.value for definition in TECHNIQUES.values())
    assert dict(sizes) == {family: len(keys) for family, keys in FAMILIES.items()}
    assert sum(sizes.values()) == len(TT_CATALOG)


def test_each_definitions_family_membership_matches_its_tt_family_set() -> None:
    for key, definition in TECHNIQUES.items():
        assert key in FAMILIES[definition.family.value]


def test_a_populated_summary_always_carries_steps_and_pitfalls() -> None:
    """The shape rule, stated as an invariant rather than a count of how many are
    still empty — it needed no edit as the families were filled in, and it needs
    none if a newly added technique ships with its explanation still empty."""
    for key, definition in TECHNIQUES.items():
        if definition.summary:
            assert definition.steps, f"{key} has a summary but no steps"
            assert definition.pitfalls, f"{key} has a summary but no pitfalls"


def test_display_name_overrides_fix_the_terms_of_art_title_case_gets_wrong() -> None:
    assert (
        TECHNIQUES["to_complete_performance_index"].display_name == "To-Complete Performance Index"
    )
    assert TECHNIQUES["design_for_x"].display_name == "Design for X"


def test_every_unoverridden_display_name_is_what_the_one_humanize_rule_spells() -> None:
    """Walked over every catalog key against ``naming.humanize`` itself, rather than
    against a restatement of what that function does.

    ``_DISPLAY_NAME_OVERRIDES`` exists precisely because a couple of PMBOK terms of art
    are NOT the humanized key, so this checks the *fallback* path: a key with no
    override reads exactly as the one word-shaping rule spells it, and a key with one
    reads differently — an override that already agrees with ``humanize`` corrects
    nothing and is dead weight.
    """
    assert set(_OVERRIDES) <= set(TECHNIQUES), (
        f"an override names no technique: {sorted(_OVERRIDES)}"
    )
    for key, definition in TECHNIQUES.items():
        if key in _OVERRIDES:
            assert definition.display_name == _OVERRIDES[key], key
            assert definition.display_name != humanize(key), (
                f"{key}'s override is what humanize already produces"
            )
        else:
            assert definition.display_name == humanize(key), key


def test_the_fallback_display_name_calls_humanize_rather_than_restating_its_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The walk above would pass just as happily against a second inline copy of the
    formula, because a fresh copy agrees on the day it is written; it only catches the
    copy once the two have already drifted, which is a shipped defect by then. This is
    the part a copy cannot survive: replace the rule and every unoverridden name must
    move with it — while an override, whose whole job is to say "not the humanized
    key", must not.

    ``technique_slug`` is built from the same ``humanize``, so a definitions-local copy
    means rewriting the rule moves every technique URL while every display name stays
    put, with nothing failing.
    """
    monkeypatch.setattr(definitions, "humanize", lambda text: f"<{text}>")
    plain = sorted(set(TECHNIQUES) - set(_OVERRIDES))
    assert plain, "vacuous walk: every technique carries an override"
    for key in plain:
        assert definitions._display_name(key) == f"<{key}>", key
    for key in _OVERRIDES:
        assert definitions._display_name(key) == _OVERRIDES[key], key


def test_only_a_non_extension_technique_claims_a_pmbok_source() -> None:
    """Provenance is driven off ``tt.EXTENSIONS`` itself, walked over every
    catalog member, so adding an extension to ``tt.py`` cannot silently
    inherit a PMBOK citation it has not earned."""
    assert EXTENSIONS, "the guard below is only meaningful while some extension exists"
    assert EXTENSIONS <= TT_CATALOG
    for key, definition in TECHNIQUES.items():
        expected = EXTENSION_SOURCE if key in EXTENSIONS else PMBOK_SOURCE
        assert definition.source == expected, key


def test_source_version_is_present_exactly_where_a_pmbok_edition_is_claimed() -> None:
    """The edition string lives in one place and every PMBOK-sourced definition
    carries that same string; an extension cites no edition, so it carries none."""
    for key, definition in TECHNIQUES.items():
        claims_pmbok = definition.source == PMBOK_SOURCE
        assert bool(definition.source_version) is claims_pmbok, key
        if claims_pmbok:
            assert definition.source_version == PMBOK_SOURCE_VERSION, key


def test_assistance_mode_never_promises_more_than_the_assistant_routes_offer() -> None:
    """``assess.model.ASSISTANT_ROUTES`` is the only place that knows whether a
    technique can actually be RUN rather than only read about. It is empty
    today, so ``GUIDE`` — explain it, nothing more — is the honest answer for
    every technique, and this walks all of them to say so. The moment a route
    ships, the routed technique must stop calling itself a guide, and this
    fails until its mode is raised."""
    for key, definition in TECHNIQUES.items():
        if key in ASSISTANT_ROUTES:
            assert definition.assistance_mode is not AssistanceMode.GUIDE, key
        else:
            assert definition.assistance_mode is AssistanceMode.GUIDE, key
