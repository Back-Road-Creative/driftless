"""The Scope & Baseline document: a project's baseline versions and the change
requests that drove re-baselining. It compares the original plan (v1) with the
current one (highest version) — per-task planned window and cost, plus each
version's planned-cost total — so scope and cost growth are visible. The one
subtraction (the cost delta) is done here; the template only formats. Every
collection is ordered for byte-identical output.

A project with no approved baseline has nothing to compare, so ``render`` returns
a short placeholder document (the template's empty-``versions`` branch) instead of
indexing an empty list — this keeps ``report all`` completing for every project."""

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from driftless.models import Baseline, BaselineLine, ChangeRequest, Project
from driftless.report import engine

SLUG = "scope-baseline"
TITLE = "Scope & Baseline"


def _baseline_view(session: Session, baseline: Baseline) -> dict[str, Any]:
    """One baseline's per-task planned window and cost, with the planned-cost total.

    ``lines`` is a throwaway local — the session's weak identity map evicts it
    (and any ``line.task`` it lazily loaded) the moment this returns, so a second
    call for the same baseline (``render`` builds both ``original`` and ``current``
    this way) would re-run one query per line. ``selectinload`` batches every
    line's task into the SAME round trip that fetches the lines, so a call costs
    a fixed two statements regardless of how many lines the baseline has."""
    lines = session.scalars(
        select(BaselineLine)
        .where(BaselineLine.baseline_id == baseline.id)
        .order_by(BaselineLine.task_id, BaselineLine.id)
        .options(selectinload(BaselineLine.task))
    ).all()
    rows = [
        {
            "task": ln.task.name,
            "start": ln.planned_start,
            "finish": ln.planned_finish,
            "cost": ln.planned_cost,
        }
        for ln in lines
    ]
    return {
        "version": baseline.version,
        "total": sum((ln.planned_cost for ln in lines), 0.0),
        "rows": rows,
    }


def render(session: Session, project: Project, as_of: date) -> str:
    """Render the Scope & Baseline document for ``project`` as of ``as_of``."""
    baselines = session.scalars(
        select(Baseline)
        .where(Baseline.project_id == project.id, Baseline.status == "approved")
        .order_by(Baseline.version)
    ).all()
    versions = [
        {"version": b.version, "status": b.status, "approved_at": b.approved_at} for b in baselines
    ]
    if not baselines:
        return engine.render(
            "scope_baseline.md",
            {"title": TITLE, "project": project.name, "as_of": as_of, "versions": versions},
        )
    original = _baseline_view(session, baselines[0])
    current = _baseline_view(session, baselines[-1])
    changes = [
        {
            "raised_on": cr.raised_on,
            "description": cr.description,
            "status": cr.status,
            "version": cr.resulting_baseline.version if cr.resulting_baseline is not None else None,
        }
        for cr in session.scalars(
            select(ChangeRequest)
            .where(ChangeRequest.project_id == project.id)
            .order_by(ChangeRequest.raised_on, ChangeRequest.id)
        )
    ]
    context: dict[str, Any] = {
        "title": TITLE,
        "project": project.name,
        "as_of": as_of,
        "versions": versions,
        "original": original,
        "current": current,
        "changed": len(baselines) > 1,
        "cost_delta": current["total"] - original["total"],
        "changes": changes,
    }
    return engine.render("scope_baseline.md", context)
