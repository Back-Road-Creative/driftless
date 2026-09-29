"""The per-line delta between two approved baseline versions:
``GET /projects/{project_id}/baselines/diff``, optionally ``?versions=v1...v2``.

Read-only and computed, never a model or a migration: every figure here is
derived at request time from the two named ``Baseline`` rows' own
``BaselineLine``s, through :func:`driftless.calc.baseline_diff.diff_baseline_lines`.

``versions`` (``"{v1}...{v2}"``, split by hand below) is a QUERY parameter, not
a second path segment: every other per-project page in this app is
``/projects/{project_id}/<static-suffix>`` — exactly one path parameter — and
the shared web test harness (``tests/test_web_csrf.py``'s ``SAMPLE``) can only
supply one substitution value per page shape. A second independent path
parameter would need a second, different value the harness has no mechanism
for. With no ``versions`` given, the page defaults to the two most recent
approved baselines, so the plain path alone is still a complete, populated
page — the closest existing convention (``?as_of=``, ``?crash=`` elsewhere)
applied to this new case.

A baseline that does not exist, or exists only as a draft, is not diffable:
``versions`` failing to parse as ``"<int>...<int>"``, or either named side missing
or not ``status == "approved"``, 404s — the page's "unknown/unapproved baseline"
rule, never a 422 a browser address cannot act on. With no ``versions`` given and
fewer than two approved baselines to default to, there is nothing named to be
wrong, so the page renders 200 with its own empty state instead — the same rule
``gantt.html`` and every other data-backed page here already follows: an empty
store is a page state, not an error.

Each baseline's own approval record (``status``, ``approved_at``) stands beside
the ``ChangeRequest`` whose ``resulting_baseline_id`` names the later version,
when one exists, and the sign-off ledger for the ``after`` version —
``SignOff`` rows with ``subject_kind == "baseline"`` and ``subject_ref`` the
baseline's own id — is listed and offered a decision form.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.calc.baseline_diff import diff_baseline_lines
from driftless.calc.evm import BaselineTask
from driftless.models import Baseline, BaselineLine, ChangeRequest, Project, SignOff
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES


def _approved_version(db: Session, project_id: int, version: int) -> Baseline:
    """The one approved baseline at ``version`` on ``project_id``, or a 404 —
    "unknown" (no such version) and "unapproved" (a draft or superseded row)
    both read the same to a reader who cannot diff against either."""
    baseline = db.scalar(
        select(Baseline).where(Baseline.project_id == project_id, Baseline.version == version)
    )
    if baseline is None or baseline.status != "approved":
        raise HTTPException(404, f"no approved baseline v{version} on project {project_id}")
    return baseline


def _lines(db: Session, baseline_id: int) -> Sequence[BaselineLine]:
    """A baseline's lines with each line's task batched into the same round trip —
    never a query per line, the same rule ``web.gantt`` already follows."""
    return db.scalars(
        select(BaselineLine)
        .where(BaselineLine.baseline_id == baseline_id)
        .options(selectinload(BaselineLine.task))
        .order_by(BaselineLine.task_id)
    ).all()


def _as_tasks(lines: Sequence[BaselineLine]) -> tuple[BaselineTask, ...]:
    return tuple(
        BaselineTask(str(line.task_id), line.planned_start, line.planned_finish, line.planned_cost)
        for line in lines
    )


def _default_versions(db: Session, project_id: int) -> tuple[int, int] | None:
    """The two most recent approved baselines, newest last — or ``None`` when fewer
    than two exist, since there is then nothing to default a diff to; the caller
    renders the page's own empty state rather than treating that as an error."""
    versions = db.scalars(
        select(Baseline.version)
        .where(Baseline.project_id == project_id, Baseline.status == "approved")
        .order_by(Baseline.version.desc())
        .limit(2)
    ).all()
    if len(versions) < 2:
        return None
    return versions[1], versions[0]


def _signoffs(db: Session, baseline_id: int) -> Sequence[SignOff]:
    """The baseline sign-off ledger for one version, newest first."""
    return db.scalars(
        select(SignOff)
        .where(SignOff.subject_kind == "baseline", SignOff.subject_ref == str(baseline_id))
        .order_by(SignOff.signed_at.desc())
    ).all()


def create_baseline_diff_router() -> APIRouter:
    """The baseline diff page — no as-of dependency: it names two already-approved
    versions explicitly, so there is nothing left for an as-of to resolve."""
    router = APIRouter(route_class=PageRoute)

    @router.get("/projects/{project_id}/baselines/diff", response_class=HTMLResponse)
    def baseline_diff(
        request: Request, project_id: int, db: Db, versions: str | None = None
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)
        before = after = change_request = None
        rows: list[dict[str, object]] | None = None
        signoffs: Sequence[SignOff] = ()
        if versions is None:
            pair = _default_versions(db, project.id)
        else:
            parts = versions.split("...")
            if len(parts) != 2 or not all(part.isdigit() for part in parts):
                raise HTTPException(404, f"not a version pair: {versions!r}")
            pair = (int(parts[0]), int(parts[1]))
        if pair is not None:
            v1, v2 = pair
            before = _approved_version(db, project.id, v1)
            after = _approved_version(db, project.id, v2)
            before_lines, after_lines = _lines(db, before.id), _lines(db, after.id)
            names = {str(line.task_id): line.task.name for line in (*before_lines, *after_lines)}
            diffs = diff_baseline_lines(_as_tasks(before_lines), _as_tasks(after_lines))
            rows = [{"name": names.get(diff.task_id, diff.task_id), "diff": diff} for diff in diffs]
            change_request = db.scalar(
                select(ChangeRequest).where(ChangeRequest.resulting_baseline_id == after.id)
            )
            signoffs = _signoffs(db, after.id)
        context = {
            "project": project,
            "before": before,
            "after": after,
            "rows": rows,
            "change_request": change_request,
            "signoffs": signoffs,
        }
        return TEMPLATES.TemplateResponse(request, "baseline_diff.html", context)

    return router
