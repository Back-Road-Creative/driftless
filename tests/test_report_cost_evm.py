"""The Cost/EVM document equals calc: every figure in the Markdown is the one
``driftless.calc.evm`` computes from the seeded rows, formatted — not recomputed.

The seed here makes all nine figures pairwise distinct (the shared conftest seed
has BAC == PV and AC == ETC, so a swapped pair of table rows still passed), and
each assertion pins the whole row — label and value together — so a figure
printed beside the wrong label cannot pass either."""

from datetime import date

from sqlalchemy.orm import Session

from driftless import models as m
from driftless.report import gather, render_document

AS_OF = date(2026, 3, 31)

_ROW_LABELS = (
    "Budget at completion (BAC)",
    "Planned value (PV)",
    "Earned value (EV)",
    "Actual cost (AC)",
    "Cost performance index (CPI)",
    "Schedule performance index (SPI)",
    "Estimate at completion (EAC)",
    "Estimate to complete (ETC)",
    "Variance at completion (VAC)",
    "Cost variance (CV)",
    "Schedule variance (SV)",
)


def _distinct_project(db: Session) -> m.Project:
    """A project whose nine EVM figures all format differently: the plan window
    runs past ``AS_OF`` (so PV < BAC) and progress is 45% (so ETC != AC)."""
    portfolio = m.Portfolio(name="Content Brands", business=m.Business(name="BRC"))
    proj = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="GMS", project=proj)
    task = m.Task(name="GMS", workstream=stream, estimate_unit="hours", percent_complete=45)
    baseline = m.Baseline(project=proj, version=1, status="approved")
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=2000.0)
    line.planned_start, line.planned_finish = date(2026, 1, 1), date(2026, 4, 10)
    db.add(line)
    db.add(
        m.CostEntry(project=proj, category="labour", incurred_on=date(2026, 1, 31), amount=640.0)
    )
    db.commit()
    return proj


def test_every_rendered_figure_sits_in_its_own_labelled_row(db: Session) -> None:
    project = _distinct_project(db)
    costs = gather.project_costs(db).get(project.id, [])
    snap = gather.project_evm(project, costs, AS_OF)
    doc = render_document("cost-evm", db, project, AS_OF)

    values: list[float] = [snap.bac, snap.pv, snap.ev, snap.ac]
    for ratio in (snap.cpi, snap.spi, snap.eac, snap.etc, snap.vac):
        assert ratio is not None  # this seed defines every ratio
        values.append(ratio)
    values.extend([snap.cv, snap.sv])
    figures = [f"{value:.2f}" for value in values]
    assert len(set(figures)) == len(figures), (
        "the seed must keep all eleven figures pairwise distinct — equal figures let "
        "swapped table rows pass"
    )
    assert "GMS" in doc
    assert AS_OF.isoformat() in doc
    for label, figure in zip(_ROW_LABELS, figures, strict=True):
        assert f"| {label} | {figure} |" in doc, f"the {label} row must carry its own figure"
    assert "EAC method: cost-performance-index" in doc
