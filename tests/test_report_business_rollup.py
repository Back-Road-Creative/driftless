"""The business-scoped Portfolio Rollup equals calc: its business totals and
on-track share are the ones ``driftless.calc.rollup`` produces from the seeded tree,
formatted — and it renders byte-identically from the same inputs. The document is
discovered with ``SCOPE == "business"`` and a two-argument ``render``."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from driftless import models as m
from driftless.calc.rollup import Kpis, on_track_share
from driftless.report import gather, iter_documents
from driftless.report.documents import business_rollup

AS_OF = date(2026, 3, 31)  # matches the seeded baseline finish
JAN = date(2026, 1, 31)

Risks = tuple[tuple[str, float, float], ...]


def _project(
    db: Session,
    portfolio: m.Portfolio,
    name: str,
    *,
    percent: int,
    planned: float,
    spend: float,
    milestone: str = "pending",
    risks: Risks = (),
) -> None:
    """One baselined project with its dated spend, a milestone and its risks."""
    project = m.Project(name=name, portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name=name, project=project)
    task = m.Task(name=name, workstream=stream, estimate_unit="hours", percent_complete=percent)
    baseline = m.Baseline(project=project, version=1, status="approved")
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=planned)
    line.planned_start, line.planned_finish = JAN, AS_OF
    db.add(line)
    db.add(m.Milestone(project=project, name=name, target_date=AS_OF, status=milestone))
    db.add(m.CostEntry(project=project, category="labour", incurred_on=JAN, amount=spend))
    for s, p, i in risks:
        db.add(m.Risk(project=project, description="r", status=s, probability=p, impact=i))


def _seed(db: Session) -> None:
    """Two portfolios, three projects — one red (missed milestone), so on-track < 100%."""
    brc = m.Business(name="BRC")
    brands = m.Portfolio(name="Content Brands", business=brc)
    ventures = m.Portfolio(name="Ventures", business=brc)
    _project(
        db, brands, "GMS", percent=25, planned=1000.0, spend=400.0, risks=(("open", 0.5, 4e4),)
    )
    _project(db, brands, "BTB", percent=75, planned=3000.0, spend=2000.0, milestone="missed")
    _project(db, ventures, "Zephyr", percent=50, planned=2000.0, spend=800.0)
    db.commit()


def _tree(db: Session) -> Kpis:
    """The rolled-up overview, mirroring ``driftless.web.home._render`` exactly."""
    return gather.overview(db, AS_OF)


def test_the_document_is_discovered_with_business_scope() -> None:
    docs = {mod.SLUG: mod for mod in iter_documents() if hasattr(mod, "SLUG")}
    assert "business-rollup" in docs
    assert getattr(docs["business-rollup"], "SCOPE", "project") == "business"


def test_the_same_inputs_render_byte_identically(db: Session) -> None:
    _seed(db)
    assert business_rollup.render(db, AS_OF) == business_rollup.render(db, AS_OF)


def test_business_totals_and_on_track_share_are_calcs(db: Session) -> None:
    _seed(db)
    total = _tree(db)
    projects = gather.leaves(total)
    # The business budget is the sum of the project BACs, computed once by roll_up.
    assert total.budget == sum((p.budget for p in projects), Decimal(0))
    share = on_track_share(projects)
    assert share is not None, "three projects, one red -> a real percentage"

    doc = business_rollup.render(db, AS_OF)
    assert f"{total.budget:,.0f}" in doc
    assert f"{share:.0f}%" in doc
    assert "Content Brands" in doc and "GMS" in doc
