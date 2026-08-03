"""Cross-entity search: one term over the things a person names out loud.

SEARCHED, AND ON WHICH COLUMN — the text someone would say to name the thing, and only where
a hit has a page to send them to: portfolio, program, project, workstream and task ``name``,
plus the two RAID records people describe rather than name, risk and issue ``description``.
NOT searched: money and measurement rows (``BudgetLine``, ``CostEntry``, ``QualityMeasurement``),
whose only text is a closed vocabulary — an amount is not a name; ``Business``, which has no
page of its own, so a hit could only link to ``/``; and the auth tables, run from the CLI.

BOUNDED — a search box becomes the slowest page in the product by scanning table by table, row by
row. This runs exactly ONE statement per searched kind (seven, flat in the store size), each
``LIMIT``ed to :data:`PER_KIND`: at most 70 hits whatever the store holds, and no caller-supplied
limit — a cap a request can raise is not a cap. Matching lowers both sides, so it means the same on
SQLite and on Postgres (case-sensitive there), and escapes the term's own ``%``/``_`` rather than
honouring them. Order is (kind in :data:`SEARCHED` order, then id), read off no clock at all.

TWO SURFACES, TWO PATHS — ``GET /search`` is the page (``driftless.web.search``) and ``GET
/search/results`` the JSON, registered on ``app`` directly and never through an included router:
the page walks read an included router's routes as *pages*, so a JSON route mounted that way
would be walked as HTML and would sit outside the check keeping it off the page's own path."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from driftless.models import Issue, Portfolio, Program, Project, Risk, Task, Workstream

PER_KIND = 10  # the most hits any one kind may return — see BOUNDED above


class Hit(BaseModel):  # one match: what it is, which row, what to call it, where to go
    kind: str
    id: int
    label: str
    path: str


@dataclass(frozen=True)
class Searched:
    """One searchable kind: the column matched, and the page a hit links to. ``anchor`` is the
    id that path is built from — not always the row's own (a workstream and a task are read on
    their project's hub), and one mapped elsewhere is joined in by :func:`search`."""

    kind: str
    row_id: InstrumentedAttribute[int]
    column: InstrumentedAttribute[str]
    anchor: InstrumentedAttribute[int]
    path: str


HUB = "/projects/{}/hub"
SEARCHED: tuple[Searched, ...] = (
    Searched("portfolio", Portfolio.id, Portfolio.name, Portfolio.id, "/portfolios/{}/rollup"),
    Searched("program", Program.id, Program.name, Program.id, "/programs/{}/rollup"),
    Searched("project", Project.id, Project.name, Project.id, HUB),
    Searched("workstream", Workstream.id, Workstream.name, Workstream.project_id, HUB),
    Searched("task", Task.id, Task.name, Workstream.project_id, HUB),
    Searched("risk", Risk.id, Risk.description, Risk.project_id, HUB),
    Searched("issue", Issue.id, Issue.description, Issue.project_id, HUB),
)


def search(db: Session, term: str) -> list[Hit]:
    """Every hit for ``term``, at most :data:`PER_KIND` per kind. Empty term, no hits."""
    cleaned = term.strip()
    if not cleaned:  # the empty query is a product state: it asks for nothing
        return []
    escaped = cleaned.lower().translate({ord(c): f"\\{c}" for c in "\\%_"})
    hits: list[Hit] = []
    for spec in SEARCHED:
        statement = (
            select(spec.row_id, spec.column, spec.anchor)
            .where(func.lower(spec.column).like(f"%{escaped}%", escape="\\"))
            .order_by(spec.row_id)
            .limit(PER_KIND)
        )
        if spec.anchor.class_ is not spec.column.class_:  # a task's anchor is its parent's
            statement = statement.join(spec.anchor.class_)
        hits += [
            Hit(kind=spec.kind, id=row_id, label=label, path=spec.path.format(anchor))
            for row_id, label, anchor in db.execute(statement)
        ]
    return hits
