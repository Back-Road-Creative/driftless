"""``driftless.calc.control_state``: an ``OperatingControl``'s RAG state, computed
from its linked incidents and their evidence age — never stored, same RAG
philosophy ``assess.scorecard.evaluate_metric`` applies to a scorecard metric."""

from datetime import date

from driftless.calc.control_state import STALE_AFTER_DAYS, IncidentEvidence, control_state


def test_no_incidents_and_no_evidence_reads_amber() -> None:
    """No open incidents but nothing to show for it either — not a clean green."""
    result = control_state([], date(2026, 9, 22))
    assert result.status == "amber"
    assert result.evidence is None
    assert result.reasons


def test_open_high_severity_incident_is_red() -> None:
    incidents = [
        IncidentEvidence(status="open", severity="high", raised_on=date(2026, 9, 20)),
    ]
    result = control_state(incidents, date(2026, 9, 22))
    assert result.status == "red"
    assert any("high" in reason or "critical" in reason for reason in result.reasons)


def test_open_critical_severity_incident_is_red() -> None:
    incidents = [
        IncidentEvidence(status="investigating", severity="critical", raised_on=date(2026, 9, 20)),
    ]
    result = control_state(incidents, date(2026, 9, 22))
    assert result.status == "red"


def test_open_low_severity_incident_is_amber() -> None:
    incidents = [
        IncidentEvidence(status="open", severity="low", raised_on=date(2026, 9, 20)),
    ]
    result = control_state(incidents, date(2026, 9, 22))
    assert result.status == "amber"


def test_resolved_incident_with_recent_evidence_is_green() -> None:
    incidents = [
        IncidentEvidence(
            status="resolved",
            severity="high",
            raised_on=date(2026, 8, 1),
            resolved_on=date(2026, 9, 20),
        ),
    ]
    result = control_state(incidents, date(2026, 9, 22))
    assert result.status == "green"
    assert result.evidence is not None
    assert result.evidence.age_days == 2


def test_stale_evidence_with_no_open_incident_is_amber() -> None:
    incidents = [
        IncidentEvidence(
            status="resolved",
            severity="low",
            raised_on=date(2026, 1, 1),
            resolved_on=date(2026, 1, 5),
        ),
    ]
    as_of = date(2026, 9, 22)
    assert (as_of - date(2026, 1, 5)).days > STALE_AFTER_DAYS
    result = control_state(incidents, as_of)
    assert result.status == "amber"
    assert result.evidence is not None
    assert result.evidence.age_days > STALE_AFTER_DAYS


def test_evidence_from_the_future_is_ignored() -> None:
    """As-of never sees evidence dated after itself — same rule ``evidence_age`` holds."""
    incidents = [
        IncidentEvidence(status="closed", severity="low", raised_on=date(2026, 9, 25)),
    ]
    result = control_state(incidents, date(2026, 9, 22))
    assert result.evidence is None
    assert result.status == "amber"


def test_high_severity_beats_amber_staleness() -> None:
    """Red for an open high incident even when the evidence is also fresh."""
    incidents = [
        IncidentEvidence(status="open", severity="critical", raised_on=date(2026, 9, 22)),
    ]
    result = control_state(incidents, date(2026, 9, 22))
    assert result.status == "red"
    assert result.evidence is not None
    assert result.evidence.age_days == 0
