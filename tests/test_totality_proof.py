"""The one-line proof: ``pmbok.proof.build_proof()`` reports zero of every gap
shape on this tree, and the wizard skips no process at all.

Each assertion below mirrors a totality test that already owns its own gap
shape — ``tests/test_method_graph.py::test_orphan_nodes_are_exactly_the_known_
exemptions`` for orphans, ``tests/test_launcher_totality.py`` for unlaunchable,
``tests/test_pmbok_crosswalk.py`` for the agile crosswalk, ``tests/test_pmbok_
tailoring.py`` for the M&C tailoring profiles, ``tests/test_process_totality.py``
/``test_technique_totality.py``/``test_artifact_totality.py`` for unexplained,
``tests/test_wizard_totality.py`` for the wizard's own skip claim — this module
does not re-derive any of those rules, it only proves ``proof.py`` reads them
faithfully and reports the SAME zero.

The last test below reuses ``test_wizard_totality.py``'s own lifecycle-order and
waive strategy by IMPORT rather than copying it, to check the live-session claim
``Proof.skipped_processes`` makes against a real store, not only the static
``state.is_assessable`` read the rest of this module runs store-free.
"""

from __future__ import annotations

from dataclasses import fields

from sqlalchemy.orm import Session

from driftless import models as m
from driftless.pmbok import catalog, state
from driftless.pmbok import plain_language as pl
from driftless.pmbok.proof import GAP_SHAPES, Proof, build_proof
from driftless.wizard import engine
from tests.conftest import AS_OF
from tests.test_wizard_totality import _LIFECYCLE_ORDER, _waive

#: An explanation is a sentence or two, held to the catalog's own summary rules.
_MAX_EXPLANATION_SENTENCES = 2
_MAX_EXPLANATION_WORDS = 45


def test_the_proof_is_total_on_this_tree() -> None:
    proof = build_proof()
    assert proof.orphan_techniques == ()
    assert proof.orphan_artifacts == ()
    assert proof.orphan_method_practices == ()
    assert proof.unexplained_processes == ()
    assert proof.unexplained_techniques == ()
    assert proof.unexplained_artifacts == ()
    assert proof.unlaunchable_techniques == ()
    assert proof.unlaunchable_artifacts == ()
    assert proof.uncrosswalked_method_practices == ()
    assert proof.uncrosswalked_agile_models == ()
    assert proof.uncrosswalked_tailoring_gaps == ()
    assert proof.skipped_processes == ()
    assert proof.total_gaps == 0
    assert proof.is_total is True


def test_orphan_and_uncrosswalked_method_practices_count_a_shared_member_once_each() -> None:
    """``orphan_method_practices`` and ``uncrosswalked_method_practices`` are two
    different checks now, not the same call assigned twice — a member that
    happens to land in both counts once per field, never twice for the same
    underlying gap."""
    proof = Proof(
        orphan_method_practices=("scrum:daily-scrum",),
        uncrosswalked_method_practices=("scrum:daily-scrum",),
    )
    assert proof.orphan_count == 1
    assert proof.uncrosswalked_count == 1
    assert proof.total_gaps == 2


def test_orphan_method_practices_is_empty_on_this_tree() -> None:
    """Today's registry carries no dangling crosswalk entry, so the new,
    distinct check the field now runs still reports nothing on this tree — the
    interesting proof is that it FIRES on a bogus entry, covered separately in
    ``tests/test_methods.py``-adjacent unit coverage of ``proof._orphan_method_
    practices``."""
    proof = build_proof()
    assert proof.orphan_method_practices == ()


def test_orphan_method_practices_fires_on_a_dangling_crosswalk_id() -> None:
    """A practice whose ``crosswalk`` names an id that is neither a real
    process nor a real technique is what ``orphan_method_practices`` now
    checks for — constructed here rather than relied on from live data, since
    live data carries none today."""
    from driftless.pmbok.methods import METHODS, MethodProfile, Practice, PracticeKind
    from driftless.pmbok.proof import _orphan_method_practices

    bogus_profile = MethodProfile(
        key="zz-fake",
        display_name="Fake",
        source="Fake Guide",
        source_version="1",
        plain_summary="A made-up method for this test.",
        practices=(
            Practice(
                key="bogus",
                display_name="Bogus",
                plain_summary="A made-up practice for this test.",
                kind=PracticeKind.POLICY,
                crosswalk=("no-such-process-id",),
            ),
        ),
    )
    original = dict(METHODS)
    METHODS["zz-fake"] = bogus_profile
    try:
        assert _orphan_method_practices() == ("zz-fake:bogus",)
    finally:
        METHODS.clear()
        METHODS.update(original)


def test_orphan_artifacts_reach_the_method_through_component_of_not_an_exemption() -> None:
    """``development_approach`` and ``performance_measurement_baseline`` are
    project management plan components with no process naming them directly —
    pinning the REASON ``orphan_artifacts`` is empty (each resolves through
    ``artifacts.COMPONENT_OF`` to a whole processes reference), not just the
    emptiness, so a reintroduced ``UNTRACKED_DISPOSITIONS`` exemption can't
    silently make the bare ``== ()`` assertion above pass again for the wrong
    reason."""
    from driftless.pmbok.artifacts import COMPONENT_OF

    referenced = {a for p in catalog.PROCESSES for a in (*p.inputs, *p.outputs)}
    for kind in ("development_approach", "performance_measurement_baseline"):
        assert kind in COMPONENT_OF, f"{kind} is not recorded as a component of anything"
        assert COMPONENT_OF[kind] in referenced, (
            f"{kind}'s recorded whole, {COMPONENT_OF[kind]!r}, is itself unreferenced"
        )


def test_every_count_is_the_length_of_its_own_member_tuple() -> None:
    """The counts are not typed twice: each is exactly ``len()`` of the tuple
    beside it, so a Proof built with members but no matching count is impossible."""
    proof = Proof(
        orphan_techniques=("a",),
        orphan_artifacts=("b", "c"),
        unexplained_processes=("d",),
        unlaunchable_techniques=("e", "f", "g"),
        uncrosswalked_agile_models=("h",),
        uncrosswalked_tailoring_gaps=("hybrid:5.5",),
        skipped_processes=("4.1", "4.2"),
    )
    assert proof.orphan_count == 3
    assert proof.unexplained_count == 1
    assert proof.unlaunchable_count == 3
    assert proof.uncrosswalked_count == 2
    assert proof.total_gaps == 11
    assert proof.is_total is False


def test_skipped_processes_is_exactly_the_not_assessable_set() -> None:
    """Store-free mirror of ``wizard.engine.next_step``'s one remaining skip
    clause — a process with no producible output is now a ``derived`` or
    ``reference`` step (``WizardStep.kind``), never skipped, so the only process
    ``next_step`` can still pass over entirely is one the store cannot judge at
    all: ``not state.is_assessable(process)``."""
    proof = build_proof()
    assert set(proof.skipped_processes) == {
        p.id for p in catalog.PROCESSES if not state.is_assessable(p)
    }


def test_next_step_reaches_every_process_the_proof_calls_unskipped(db: Session) -> None:
    """The live-session claim behind ``Proof.skipped_processes == ()``: walking a
    bare project through ``next_step``, waiving each earlier process in lifecycle
    order exactly the way ``tests/test_wizard_totality.py`` does, reaches every
    single catalog process in turn. That module's own strategy is imported, never
    copied, so the two suites cannot silently diverge on what "the lifecycle
    order" or "waived" mean."""
    proof = build_proof()
    assert proof.skipped_processes == ()

    project = m.Project(name="Bare", portfolio=m.Portfolio(name="P", business=m.Business(name="B")))
    db.add(project)
    db.commit()

    # One project, walked incrementally rather than test_wizard_totality's fresh-project-
    # per-id parametrization: waive the current process only once next_step has actually
    # returned it, so this proves the SAME lifecycle-order claim with one pass over the
    # catalog instead of one waive per (process, earlier-process) pair.
    for process in _LIFECYCLE_ORDER:
        step = engine.next_step(db, project, AS_OF)
        assert step is not None and step.process_id == process.id, (
            f"next_step skipped {process.id} — proof.build_proof() claims nothing is skipped"
        )
        _waive(db, project, process)
        db.commit()


def test_every_gap_shape_the_proof_can_report_carries_a_plain_explanation() -> None:
    """The explanation set is closed over the gap-shape set: ``GAP_SHAPES`` names
    exactly the members of ``Proof``, in declaration order, so a thirteenth count
    added to the dataclass cannot reach the page or the command as a bare label
    nobody worded. Each explanation is held to the same plain-language rules the
    catalog's own summaries pass -- one or two sentences, no raw identifier, no
    acronym -- and may not simply echo its own label back."""
    assert tuple(shape.field for shape in GAP_SHAPES) == tuple(f.name for f in fields(Proof))

    for shape in GAP_SHAPES:
        assert shape.label.strip(), f"{shape.field} has no label"
        text = shape.explanation.strip()
        assert text, f"{shape.label} is listed with no explanation of what it checks"
        assert 1 <= len(pl.sentences(text)) <= _MAX_EXPLANATION_SENTENCES, (
            f"{shape.label}'s explanation is not one or two sentences: {text!r}"
        )
        assert pl.word_count(text) <= _MAX_EXPLANATION_WORDS, (
            f"{shape.label}'s explanation runs {pl.word_count(text)} words: {text!r}"
        )
        assert not pl.snake_identifiers(text), f"{shape.label}'s explanation leaks an identifier"
        assert not pl.acronyms(text), f"{shape.label}'s explanation carries an acronym"
        assert text.rstrip(".").lower() != shape.label.lower(), (
            f"{shape.label}'s explanation only restates its label"
        )


def test_the_gaps_walk_pairs_every_shape_with_its_own_members() -> None:
    """``Proof.gaps()`` is the one list both the page and the command render, and
    each pair reads its members straight off the field its shape names."""
    proof = Proof(orphan_artifacts=("b", "c"), skipped_processes=("4.1",))
    walked = proof.gaps()
    assert tuple(shape for shape, _ in walked) == GAP_SHAPES
    assert dict((shape.field, members) for shape, members in walked) == {
        field.name: getattr(proof, field.name) for field in fields(Proof)
    }
