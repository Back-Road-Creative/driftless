"""Quality knowledge-area evaluator: latest metric readings against target and freshness.

Signal: the latest ``QualityMeasurement`` per metric, its actual value against
its target, and how fresh the newest reading is. Red when any metric's latest
reading is out of tolerance (actual past target); amber when every metric is
in tolerance but the evidence is more than 30 days old, and also when there
are no measurements at all — an unmeasured project is a gap, not a clean bill
of health, so it never reads green by default. Green only when there is
fresh, in-tolerance evidence for every metric. The recommended actions are
the PMBOK quality tools & techniques for verifying and root-causing the
result. Pure and as-of-parameterised — reads no wall clock.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.assess.model import Action, Assessment, RagStatus, Threat
from driftless.models import Project, QualityMeasurement
from driftless.pmbok import mapping
from driftless.pmbok.state import threat_subject_ref

KIND = "quality"

#: Days after which a metric's latest reading counts as stale evidence — the SAME
#: constant ``mapping.QUALITY_RECENCY_DAYS`` holds quality_report to (not a copy):
#: loosening the recency policy can't desync this evaluator's staleness read from
#: the artifact mapping's.
_STALE_AFTER = timedelta(days=mapping.QUALITY_RECENCY_DAYS)


def evaluate(session: Session, project: Project, as_of: date) -> Assessment:
    """Assess the project's quality health as of ``as_of``."""
    ref = f"project:{project.id}"
    tid = threat_subject_ref(KIND, project.id)

    rows = sorted(
        (
            row
            for row in adapters.project_rows(session, QualityMeasurement, project.id)
            if row.measured_on <= as_of
        ),
        key=lambda row: (row.measured_on, row.id),
        reverse=True,
    )
    if not rows:
        score = round(1.0, 4)
        threat = Threat(
            tid,
            KIND,
            "amber",
            score,
            "Quality is unmeasured: no quality measurements are recorded for this project.",
            ref,
        )
        return Assessment(KIND, as_of, score, "amber", (threat,), _actions(project.id, ref))

    # Rows are ordered measured_on desc, id desc, so the first occurrence of
    # each metric is deterministically its latest reading.
    latest_by_metric: dict[str, QualityMeasurement] = {}
    for row in rows:
        latest_by_metric.setdefault(row.metric, row)

    out_of_tolerance = [m for m in latest_by_metric.values() if m.actual_value > m.target_value]
    # Freshness is per metric: a metric whose *own* latest reading is old is stale
    # evidence, even if another metric was measured recently. Green needs fresh,
    # in-tolerance evidence for every metric.
    stale_metrics = [m for m in latest_by_metric.values() if as_of - m.measured_on > _STALE_AFTER]

    red = bool(out_of_tolerance)
    amber = not red and bool(stale_metrics)
    if not (red or amber):
        return Assessment(KIND, as_of, 0.0, "green")

    severity: RagStatus = "red" if red else "amber"
    score = round(float(len(out_of_tolerance)) if red else 1.0, 4)

    if red:
        count = len(out_of_tolerance)
        plural = "metric" if count == 1 else "metrics"
        description = f"{count} quality {plural} out of tolerance (latest actual exceeds target)."
    else:
        oldest = min(stale_metrics, key=lambda m: m.measured_on)
        description = (
            f"Quality evidence is stale: '{oldest.metric}' last measured "
            f"{oldest.measured_on.isoformat()}."
        )

    threat = Threat(tid, KIND, severity, score, description, ref)
    return Assessment(KIND, as_of, score, severity, (threat,), _actions(project.id, ref))


def _actions(project_id: int, ref: str) -> tuple[Action, ...]:
    """The standard quality-verification action set, addressed at ``ref``."""
    return (
        Action(
            f"quality:audit:{project_id}",
            "Run a quality audit",
            "audits",
            "Independently review whether quality processes and standards are being followed.",
            ref,
        ),
        Action(
            f"quality:inspection:{project_id}",
            "Inspect deliverables against target metrics",
            "inspection",
            "Re-measure the metrics closest to, or already past, tolerance to confirm state.",
            ref,
        ),
        Action(
            f"quality:root_cause:{project_id}",
            "Run a root-cause analysis",
            "root_cause_analysis",
            "Trace out-of-tolerance or stale metrics back to the process defect driving them.",
            ref,
        ),
    )
