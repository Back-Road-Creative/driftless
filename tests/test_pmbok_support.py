"""Support coverage: a technique with an explanation counts as explained, one without
does not; a process with no producible output is a hole; and every total reconciles
with the completeness/producibility rule it reuses rather than re-deriving one."""

from __future__ import annotations

from dataclasses import replace

import pytest

from driftless.pmbok import catalog, state
from driftless.pmbok.definitions import AssistanceMode, TechniqueDefinition, TechniqueFamily
from driftless.pmbok.model import KnowledgeArea, Process, ProcessGroup
from driftless.pmbok.support import (
    HelpFact,
    build_coverage,
    driftless_help,
    process_coverage,
    technique_coverage,
)
from driftless.wizard.cli import producible_kinds

_UNEXPLAINED = TechniqueDefinition(
    key="fake_technique",
    display_name="Fake Technique",
    family=TechniqueFamily.GENERAL,
    source="pmbok_6",
)
_EXPLAINED = replace(
    _UNEXPLAINED,
    key="fake_explained",
    display_name="Fake Explained",
    summary="what it is for",
    assistance_mode=AssistanceMode.CALCULATOR,
)

_PROCESS = Process(
    id="99.9",
    name="Fake Process",
    group=ProcessGroup.PLANNING,
    area=KnowledgeArea.SCOPE,
    inputs=(),
    tools_techniques=("fake_technique", "fake_explained"),
    outputs=("scope_statement",),
)

_REGISTRY = {"fake_technique": _UNEXPLAINED, "fake_explained": _EXPLAINED}


def test_a_technique_with_a_summary_is_explained() -> None:
    assert technique_coverage(_UNEXPLAINED).explained is False
    assert technique_coverage(_EXPLAINED).explained is True


def test_technique_coverage_carries_the_assistance_mode_untouched() -> None:
    assert technique_coverage(_EXPLAINED).assistance_mode is AssistanceMode.CALCULATOR
    assert technique_coverage(_UNEXPLAINED).assistance_mode is AssistanceMode.GUIDE


def test_a_process_with_nothing_producible_is_reported_as_a_hole() -> None:
    row = process_coverage(_PROCESS, registry=_REGISTRY, producible=tuple)
    assert row.producible_outputs == ()
    assert row.has_producible_output is False


def test_a_process_with_a_producible_output_is_not_a_hole() -> None:
    row = process_coverage(_PROCESS, registry=_REGISTRY, producible=lambda: ("scope_statement",))
    assert row.producible_outputs == ("scope_statement",)
    assert row.has_producible_output is True


def test_process_coverage_carries_each_technique_through_by_key() -> None:
    row = process_coverage(_PROCESS, registry=_REGISTRY, producible=tuple)
    assert [t.key for t in row.techniques] == ["fake_technique", "fake_explained"]
    assert [t.explained for t in row.techniques] == [False, True]


def test_process_coverage_reuses_is_assessable_rather_than_re_deriving_it() -> None:
    """The assessability the coverage view reports for every catalog process is exactly
    ``state.is_assessable``'s answer — not a parallel judgment that could disagree with it."""
    for process in catalog.PROCESSES:
        row = process_coverage(process)
        assert row.assessable is state.is_assessable(process)


def test_build_coverage_totals_reconcile_with_a_fresh_recount() -> None:
    """The explained total is a literal here rather than ``build_coverage``'s own
    expression restated: the fixture holds one explained technique of two, so an
    expected value the implementation does not recompute is the honest one."""
    summary = build_coverage(processes=(_PROCESS,), registry=_REGISTRY, producible=tuple)
    assert summary.technique_count == len(_REGISTRY)
    assert summary.explained_technique_count == 1
    assert summary.process_count == 1
    assert summary.assessable_process_count == sum(1 for p in (_PROCESS,) if state.is_assessable(p))
    assert summary.producible_process_count == 0


def test_build_coverage_over_the_real_catalog_matches_the_live_registries() -> None:
    """No hardcoded counts: every total is recomputed here from the same live sources
    ``build_coverage`` reads, so it moves with the catalog/registry instead of rotting.
    The explained total is reconciled against ``technique_coverage``'s own per-technique
    rule rather than against ``build_coverage``'s expression restated, which would pass
    whatever that expression did."""
    from driftless.pmbok.definitions import TECHNIQUES

    summary = build_coverage()
    assert summary.process_count == len(catalog.PROCESSES)
    assert summary.technique_count == len(TECHNIQUES)
    assert summary.explained_technique_count == sum(
        1 for d in TECHNIQUES.values() if technique_coverage(d).explained
    )
    assert summary.assessable_process_count == sum(
        1 for p in catalog.PROCESSES if state.is_assessable(p)
    )
    offered = frozenset(producible_kinds())
    assert summary.producible_process_count == sum(
        1 for p in catalog.PROCESSES if any(k in offered for k in p.outputs)
    )


def test_every_process_technique_key_resolves_in_the_default_registry() -> None:
    """Guards against a typo in ``tools_techniques`` silently dropping a row instead of
    raising — every key ``build_coverage`` walks over the real catalog must be one
    ``TECHNIQUES`` actually defines."""
    from driftless.pmbok.definitions import TECHNIQUES

    for process in catalog.PROCESSES:
        for key in process.tools_techniques:
            assert key in TECHNIQUES, f"{process.id} names undefined technique {key!r}"


def test_process_coverage_raises_on_an_unknown_technique_key() -> None:
    bad = replace(_PROCESS, tools_techniques=("not_a_real_technique",))
    with pytest.raises(KeyError):
        process_coverage(bad, registry=_REGISTRY, producible=tuple)


def test_driftless_help_joins_routed_techniques_and_producible_outputs() -> None:
    routes = {"fake_technique": "/x/{project_id}"}
    assert driftless_help(_PROCESS, routes=routes, producible=tuple) == (
        HelpFact("technique", "fake_technique"),
    )
    assert driftless_help(_PROCESS, routes={}, producible=lambda: ("scope_statement",)) == (
        HelpFact("output", "scope_statement"),
    )
    assert driftless_help(_PROCESS, routes={}, producible=tuple) == ()

    duped = replace(_PROCESS, tools_techniques=("fake_technique", "fake_technique"))
    assert driftless_help(duped, routes=routes, producible=tuple) == (
        HelpFact("technique", "fake_technique"),
    )


def test_producible_outputs_agrees_with_the_wizards_own_rule() -> None:
    """``support._producible_outputs`` is a copy of ``wizard.engine._producible`` — the
    private original cannot be imported here (``tests/test_package.py`` forbids it across
    a module boundary), so this test is the guard against the copy going stale. If this
    ever fails, ``support.py`` is wrong and must be brought back into line with
    ``wizard.engine._producible`` — never the other way round."""
    from driftless.pmbok import support
    from driftless.wizard import engine

    offered = frozenset(producible_kinds())
    for process in catalog.PROCESSES:
        assert support._producible_outputs(process, offered) == engine._producible(process), (
            f"{process.id}: support.py and wizard.engine disagree on what is producible"
        )
