"""The propagation manifest: every reader an applied change must reach.

Five families read the store into something a person or another system sees,
and each is named here against a callable that reads ONE project: process
state (:mod:`driftless.pmbok.state`), the rollups (:mod:`driftless.pmbok.rollup`
and :mod:`driftless.calc.rollup`, the second reached the way the dashboard
reaches it — through :mod:`driftless.report.gather`, since ``calc.rollup``
itself takes a tree, not a project), the report documents
(:mod:`driftless.report.documents`), the assessment engine
(:mod:`driftless.assess`) and the export/import surface
(:mod:`driftless.api.export`, read here the way a caller of the generic list
routes reads it — the two models a change kind can write, scoped to one
project).

``CONSUMERS`` is the guard ``tests/test_propagation_manifest.py`` drives: for
each change kind in :mod:`driftless.services.changes`, every family's reading
of the affected project must differ before/after ``apply`` — a family that
genuinely cannot see a change kind is named in ``UNAFFECTED_BY_CHANGE`` with
the reason, so a family missing from BOTH is a silent gap the test catches
rather than a family nobody thought to check. No new models: everything here
reads what already exists.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.assess import assess_project
from driftless.models import Project, SignOff, StatusSnapshot
from driftless.pmbok import state
from driftless.pmbok.rollup import business_process_cells
from driftless.report import gather
from driftless.report.engine import iter_documents

#: A family's reader: one project, one as-of, in — anything comparable out.
Reader = Callable[[Session, Project, date], object]


def _process_state_view(session: Session, project: Project, as_of: date) -> object:
    """Every catalog process's state for ``project`` — the process-map's own read."""
    return tuple(
        (process.id, proc_state.value)
        for process, proc_state in state.project_process_states(project, session, as_of)
    )


def _pmbok_rollup_view(session: Session, project: Project, as_of: date) -> object:
    """``project``'s own cell out of the store-wide, per-process rollup."""
    cells = business_process_cells(session, as_of)
    return tuple(
        (
            cell.process_id,
            next((pc.state.value for pc in cell.projects if pc.project_id == project.id), None),
        )
        for cell in cells
    )


def _calc_rollup_view(session: Session, project: Project, as_of: date) -> object:
    """``project``'s own KPI leaf out of the dashboard's whole-store rollup —
    ``gather.overview`` built over ``calc.rollup.roll_up``, the same walk the
    home page and the drill pages render through."""
    kpis = gather.overview(session, as_of)
    ids = gather.id_tree(session)
    found = gather.find_node(kpis.children, ids, "project", project.id)
    return found[0] if found is not None else None


def _report_view(session: Session, project: Project, as_of: date) -> object:
    """Every PROJECT-scoped report document rendered for ``project``, concatenated.

    Two documents (``department``, ``business_rollup``) are store-wide, not
    project-scoped — their ``render`` takes no ``project`` at all, so they are
    skipped here rather than called with a signature they do not have."""
    return tuple(
        module.render(session, project, as_of)
        for module in iter_documents()
        if "project" in inspect.signature(module.render).parameters
    )


def _assess_view(session: Session, project: Project, as_of: date) -> object:
    """Every knowledge-area assessment for ``project`` — status, score and threats."""
    return tuple(
        (
            assessment.kind,
            assessment.status,
            assessment.risk_score,
            assessment.coverage,
            tuple(threat.id for threat in assessment.threats),
        )
        for assessment in assess_project(session, project, as_of)
    )


def _export_view(session: Session, project: Project, as_of: date) -> object:
    """``project``'s own rows of the two export/import-symmetric models a
    change kind can write — the CSV a ``?format=csv`` list read would answer,
    minus the response envelope."""
    snapshots = session.scalars(
        select(StatusSnapshot)
        .where(StatusSnapshot.project_id == project.id)
        .order_by(StatusSnapshot.id)
    )
    sign_offs = session.scalars(
        select(SignOff).where(SignOff.project_id == project.id).order_by(SignOff.id)
    )
    return (
        tuple(
            tuple(s.StatusSnapshotOut.model_validate(row).model_dump(mode="json").items())
            for row in snapshots
        ),
        tuple(
            tuple(s.SignOffOut.model_validate(row).model_dump(mode="json").items())
            for row in sign_offs
        ),
    )


#: The five families, each a tuple of readers — a family's whole reading is
#: every reader's output, so a family with two readers (rollup) differs the
#: moment either one does.
CONSUMERS: dict[str, tuple[Reader, ...]] = {
    "process_state": (_process_state_view,),
    "rollup": (_pmbok_rollup_view, _calc_rollup_view),
    "reports": (_report_view,),
    "assessments": (_assess_view,),
    "exports": (_export_view,),
}

#: Per change kind, the families that change kind is declared NOT to reach,
#: with the reason — checked against ``CONSUMERS`` (not restated) by
#: ``tests/test_propagation_manifest.py``, so an entry naming a retired
#: family fails loudly rather than going stale.
UNAFFECTED_BY_CHANGE: dict[str, dict[str, str]] = {
    # status_snapshot reaches every family today: pmbok.mapping resolves three
    # tracked outputs (status_report, work_performance_reports,
    # project_communications) straight off StatusSnapshot
    # (driftless/pmbok/mapping.py:_reported_status), which pulls process_state,
    # rollup AND driftless/assess/evaluators/communications.py's assessment
    # in behind it — so there is no family left to declare unaffected.
    "sign_off": {
        "assessments": (
            "the engine's suppression scope only reads subject_kind == "
            '"threat" (driftless/assess/engine.py:assess_project); a '
            '"process" sign-off, the kind this change writes, is invisible '
            "to it by construction."
        ),
    },
}
