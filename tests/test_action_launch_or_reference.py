"""Every recommended ``Action`` either launches its technique or links its written
explanation — never leaves a reader with a name and nowhere to go, and never
implies an operation is available when none is wired up.

``reference_href`` now addresses ``/techniques/{slug}``, the page that explains the
technique, rather than an anchor on the ITTO list of some process that names it —
which showed the reader the technique's *name*, one hop short. That makes it total:
``__post_init__`` refuses a ``pmbok_tt`` the registry does not hold, and the library
is keyed by a slug index over exactly those keys, so there is no "no linked process
yet either" case left on any surface. The three-way branch each surface carried is
now two-way, and the technique a process names and the technique none does get the
same treatment.

The exemplar techniques below are computed off the live catalog, never named,
because which technique has a linked process and which does not is exactly the
fact a concurrent PR is entitled to change (PR #273 attached the last few
orphans to their PMBOK-6 processes and added a new Driftless extension). Pinning
a specific key here would make this suite a second, competing catalog that goes
stale the moment the real one moves. That derivation is imported from
``tests/test_web_pages`` rather than repeated here — it used to be written out in
both files, identically down to the skip reason.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

import driftless
from driftless import cli
from driftless.assess import cli as assess_cli
from driftless.assess import engine as assess
from driftless.assess import model
from driftless.assess.model import Action, Assessment
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import (
    Baseline,
    BaselineLine,
    Business,
    CostEntry,
    Portfolio,
    Project,
    Task,
    Workstream,
)
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.tt import TT_CATALOG
from driftless.report import engine as report_engine
from driftless.report.documents import assessment as assessment_doc
from driftless.naming import technique_slug
from driftless.web.templating import TEMPLATES
import test_web_pages

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)

# Techniques named by at least one catalog process, the (possibly empty) remainder,
# and what to say when that remainder is empty — bound to the objects
# tests/test_web_pages derives, not derived a second time. Assigned rather than
# imported for the same reason the drill test assigns its fixtures: a from-import of a
# private name reads as this module's own definition of it.
_NAMED_BY_A_PROCESS = test_web_pages._NAMED_BY_A_PROCESS
_UNNAMED = test_web_pages._UNNAMED
_NO_PROCESS_REASON = test_web_pages._NO_PROCESS_REASON
# The narrower "no process AND no assistant" case ``_unlinked_action`` needs — see
# test_web_pages's own docstring on this pair for why it is not just ``_UNNAMED``.
_UNNAMED_UNROUTED = test_web_pages._UNNAMED_UNROUTED
_NO_UNROUTED_REASON = test_web_pages._NO_UNROUTED_REASON


def _seed_overspend(session: Session) -> Project:
    """BAC 1000, 20% done, AC 800 -> red cost (CPI 0.25), so the cost evaluator
    recommends real actions — including ``earned_value_analysis``, which Control
    Costs (7.4) has always named and is stable enough to stand for "a process
    names this technique" without being recomputed."""
    project = Project(
        name="GMS",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    stream = Workstream(name="Post", project=project)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = Baseline(project=project, version=1, status="approved")
    line = BaselineLine(
        baseline=baseline, task=task, planned_cost=1000.0, planned_start=JAN, planned_finish=AS_OF
    )
    session.add(line)
    session.add(CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
    session.commit()
    return project


@pytest.fixture
def db(tmp_path: Path) -> Session:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    return new_session_factory(engine)()


@pytest.fixture
def project(db: Session) -> Project:
    return _seed_overspend(db)


def _cost_actions(db: Session, project: Project) -> tuple[Action, ...]:
    cost = {a.kind: a for a in assess.assess_project(db, project, AS_OF)}["cost"]
    assert cost.actions, "the fixture must overspend, or this proves nothing"
    return cost.actions


def _unlinked_action() -> Action:
    """A real ``Action`` naming a technique no catalog process names AND no assistant
    routes — the input the reference-only, no-linked-process branch needs. No
    evaluator currently recommends such a technique on its own (that is the whole
    point of PR #273), so this builds one directly rather than threading it through
    a real assessment."""
    technique = _UNNAMED_UNROUTED[0]
    return Action("probe", "Apply an unmapped technique", technique, "why", "project:1")


# --- Action itself: closed vocabulary, derived facts ------------------------


def test_action_rejects_a_technique_the_registry_does_not_know() -> None:
    with pytest.raises(AssertionError):
        Action("id", "label", "not_a_real_technique", "rationale", "project:1")


def test_every_action_a_real_assessment_produces_resolves_to_the_registry(
    db: Session, project: Project
) -> None:
    for assessment in assess.assess_project(db, project, AS_OF):
        for action in assessment.actions:
            assert action.technique is TECHNIQUES[action.pmbok_tt]
            assert action.technique.display_name


def test_a_reference_link_addresses_the_explanation_not_the_process_that_names_it(
    db: Session, project: Project
) -> None:
    """The one literal address in this file, spelled out rather than derived, so a
    rewrite of the slug formula fails here instead of moving every link in silence."""
    actions = {a.pmbok_tt: a for a in _cost_actions(db, project)}
    eva = actions["earned_value_analysis"]
    assert eva.pmbok_tt in _NAMED_BY_A_PROCESS  # the linked-process side of the pair
    assert eva.reference_href == "/techniques/earned-value-analysis"


def test_a_technique_no_process_names_gets_the_same_link_as_any_other() -> None:
    """The case that was broken: a Driftless extension is tied to no PMBOK process by
    definition, so it used to get ``None`` and every surface told the reader nothing
    existed — while its page was already being served."""
    if not _UNNAMED_UNROUTED:
        pytest.skip(_NO_UNROUTED_REASON)
    action = _unlinked_action()
    assert action.reference_href == f"/techniques/{technique_slug(action.pmbok_tt)}"


def test_only_a_routed_action_is_launchable(db: Session, project: Project) -> None:
    """Reference-only unless ``ASSISTANT_ROUTES`` names the technique — derived from
    that registry, not a hand-maintained list. ``earned_value_analysis`` is the one
    cost action routed today (the earned-value calculator); its siblings still have
    no assistant."""
    for action in _cost_actions(db, project):
        if action.pmbok_tt in model.ASSISTANT_ROUTES:
            assert action.launch_href is not None
            assert action.is_reference_only is False
        else:
            assert action.launch_href is None
            assert action.is_reference_only is True


# --- The CLI surface ---------------------------------------------------------


def test_cli_shows_a_reference_link_when_a_process_names_the_technique(
    db: Session, project: Project, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as seed_session:
        _seed_overspend(seed_session)
    rc = cli.main(["assess", "GMS", "--as-of", AS_OF.isoformat(), "--db-url", url])
    assert rc == 0
    out = capsys.readouterr().out
    # The technique is named in humanized form — the raw key only ever appears
    # inside the anchor fragment of its reference link, never as display text.
    # change_control_tools is the exemplar (schedule_compression and its schedule
    # siblings are all routed now, to the schedule-network calculator): still
    # reference-only, and Perform Integrated Change Control (4.6) names it too.
    assert "[Change Control Tools" in out
    assert "[change_control_tools" not in out
    assert "reference only" in out
    assert "/techniques/change-control-tools" in out
    assert "no linked process yet either" not in out


def test_cli_links_the_explanation_for_a_technique_no_process_names() -> None:
    """Drives the CLI's own formatter directly with a technique the catalog names no
    process for, since no evaluator currently recommends one on its own. It reads the
    same as any other recommendation now — the third branch that used to say "no
    linked process yet either" is gone, because there is no such case."""
    if not _UNNAMED_UNROUTED:
        pytest.skip(_NO_UNROUTED_REASON)
    action = _unlinked_action()
    assessment = Assessment("cost", AS_OF, 1.0, "amber", (), (action,))
    out = assess_cli._format(assessment)
    display = action.technique.display_name
    assert f"[{display}" in out
    assert f"[{action.pmbok_tt}" not in out
    assert "reference only" in out
    assert action.reference_href in out
    assert "no linked process yet either" not in out


# --- The Assessment Report (markdown) surface --------------------------------


def test_assessment_report_shows_a_reference_link_when_a_process_names_the_technique(
    db: Session, project: Project
) -> None:
    text = assessment_doc.render(db, project, AS_OF)
    # change_control_tools is the exemplar (see the CLI test above): still reference-only.
    assert "[Change Control Tools](/techniques/change-control-tools)" in text
    assert "[change_control_tools]" not in text  # humanized, never the raw key
    assert "reference only" in text
    assert assessment_doc.render(db, project, AS_OF) == text  # byte-identical


def test_assessment_report_links_the_explanation_for_a_technique_no_process_names(
    project: Project,
) -> None:
    """Same reasoning as the CLI's counterpart: builds the row and renders the
    template directly around one unlinked technique, since no evaluator
    recommends one through the real pipeline today."""
    if not _UNNAMED_UNROUTED:
        pytest.skip(_NO_UNROUTED_REASON)
    action = _unlinked_action()
    assessment = Assessment("cost", AS_OF, 1.0, "amber", (), (action,))
    text = report_engine.render(
        "assessment.md",
        {
            "title": assessment_doc.TITLE,
            "project": project,
            "as_of": AS_OF,
            "assessments": assessment_doc._assessment_rows((assessment,)),
            "threats": [],
        },
    )
    display = action.technique.display_name
    assert f"[{display}]({action.reference_href})" in text
    assert action.pmbok_tt not in text
    assert "no linked process yet either" not in text


# --- The anchor and the reference address: one slug formula, walked ---------


def test_every_action_the_model_can_hold_has_a_reference_link_and_it_is_a_str() -> None:
    """Totality, walked over the whole closed ``TT_CATALOG`` rather than argued.

    ``reference_href`` is typed ``str`` rather than ``str | None`` because
    ``__post_init__`` admits only registry keys and the library answers at every
    one of their slugs. That is a claim about every catalog member, including the
    extension no process names, so it is checked over every one — and the address is
    built by
    calling :func:`driftless.naming.technique_slug`, the one function object the
    routers key on and the one the environment registers as the ``technique_slug``
    filter, so an ``Action`` that started deriving the word some other way fails
    here for every technique at once. The *spelling* that function produces is
    pinned by the one literal address in
    :func:`test_a_reference_link_addresses_the_explanation_not_the_process_that_names_it`.

    That the addresses actually resolve is
    ``tests/test_web_techniques.test_every_reference_href_an_action_produces_answers_with_the_explanation``,
    which walks the same catalog through the running app.
    """
    walked = set()
    for key in TT_CATALOG:
        action = Action(f"probe:{key}", "label", key, "rationale", "project:1")
        assert action.reference_href == f"/techniques/{technique_slug(key)}", key
        walked.add(key)
    assert walked == set(TT_CATALOG) and walked, "the walk must cover every catalog member"


# --- Where the slug formula lives --------------------------------------------


def test_the_model_and_the_web_layer_share_one_slug_function_at_module_scope() -> None:
    """``technique_slug`` sits in a leaf module both layers import at module scope.

    It used to live in ``driftless.web.templating``, which ``driftless.assess.model``
    cannot import at module scope: ``driftless.web``'s package init imports
    ``departments``, which imports ``assess.evaluators.resource``, which imports this
    very module — a circular ``ImportError`` on ``import driftless.assess.model``. The
    model reached it through an import inside the property body instead, which works
    and hides the cycle rather than removing it.

    This pins the fix rather than the workaround: the name is in the model's module
    namespace (a body-local import would not be), and it is the *same function object*
    the one Jinja environment registers as the ``technique_slug`` filter, so a template
    and the model cannot spell a slug two ways.
    """
    assert model.technique_slug is technique_slug
    assert TEMPLATES.env.filters["technique_slug"] is technique_slug


def test_the_slug_module_is_a_leaf_that_drags_in_no_driftless_package() -> None:
    """Importing it pulls in nothing else of ours — which is what makes it importable
    from both sides. Checked in a fresh interpreter, since this one has already
    imported half the tree; a module that merely happens to be imported late would
    pass an in-process check and still close the cycle."""
    code = (
        "import sys; import driftless.naming; "
        "ours = sorted(m for m in sys.modules if m.startswith('driftless.')); "
        "assert ours == ['driftless.naming'], ours"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# --- The branch that can no longer fire, on every surface --------------------

#: What each surface said when an action had no reference link at all. There is no
#: such action now — ``reference_href`` is total — so any surface still carrying this
#: is carrying a branch nothing can reach.
_DEAD_COPY = "no linked process yet either"


def test_no_surface_anywhere_still_carries_the_nowhere_to_send_you_branch() -> None:
    """Four surfaces (the CLI formatter, the Assessment Report template, the PMBOK
    detail page and the threat board) each had a third branch for an action with no
    reference link. Deleting the branches is not something a rendering test can force:
    once ``reference_href`` became total the branch stopped being *wrong* and started
    being merely unreachable, so every page still rendered correctly with the dead
    copy sitting in it.

    So this reads the shipped tree instead — every file under ``driftless/``, not a
    list of the four written here, since a fifth surface would grow the same branch by
    being copied from one of them.
    """
    root = pathlib.Path(driftless.__file__).parent
    carrying = sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".html", ".md"}
        and _DEAD_COPY in path.read_text(encoding="utf-8")
    )
    assert not carrying, f"a branch no action can reach still ships in: {carrying}"
