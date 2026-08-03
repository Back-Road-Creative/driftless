"""The Portfolio Rollup: every business as one document — overview totals, the
on-track share, and business → portfolio → program → project KPI rows.

Business-scoped, so it breaks the per-project ``render(session, project, as_of)``
convention: ``SCOPE = "business"`` tells the CLI to call ``render(session, as_of)``
with no project. It mirrors ``driftless.web.home._render`` exactly — the same
``gather.overview`` roll-up, the same ``gather.table_rows`` walk — so the
document and the dashboard cannot disagree. Every figure is calc's; the template
only formats. ``as_of`` is threaded, never the wall clock."""

from datetime import date

from sqlalchemy.orm import Session

from driftless.calc.rollup import on_track_share
from driftless.report import engine, gather

SLUG = "business-rollup"
TITLE = "Portfolio Rollup"
SCOPE = "business"


def render(session: Session, as_of: date) -> str:
    """Render the business-wide Portfolio Rollup as of ``as_of``."""
    total = gather.overview(session, as_of)
    # On track: the share of projects calc rated green. The count lives in calc;
    # this only flattens the tree to its project leaves — nothing is aggregated twice.
    share = on_track_share(gather.leaves(total))
    return engine.render(
        "business_rollup.md",
        {
            "title": TITLE,
            "as_of": as_of,
            "total": gather.cell(total),
            "on_track": f"{share:.0f}%" if share is not None else "n/a",
            "rows": gather.table_rows(total.children),
        },
    )
