"""``driftless.pmbok.proof_checks`` — the pure predicate behind each ``proof``
subcommand. Each check gets a passing and a failing fixture; the runners that
wire a check to a real store are exercised end to end in ``tests/test_proof_cli.py``
against the seeded demo store.
"""

from datetime import date

import pytest

from driftless.calc import forecast as fc
from driftless.pmbok import proof_checks as pc


def test_no_typed_status_passes_when_no_rollup_model_carries_the_columns() -> None:
    check = pc.check_no_typed_status(
        {"Portfolio": frozenset({"id", "name"}), "Project": frozenset({"id", "name"})}
    )
    assert check.passed
    assert check.offending == ()


def test_no_typed_status_fails_and_names_the_offending_column() -> None:
    check = pc.check_no_typed_status(
        {"Portfolio": frozenset({"id"}), "Project": frozenset({"id", "percent_complete"})}
    )
    assert not check.passed
    assert check.offending == ("Project.percent_complete",)


def test_baseline_immutable_passes_when_the_write_was_refused() -> None:
    check = pc.check_baseline_immutable(baseline_id=7, write_was_refused=True)
    assert check.passed


def test_baseline_immutable_fails_when_the_write_went_through() -> None:
    check = pc.check_baseline_immutable(baseline_id=7, write_was_refused=False)
    assert not check.passed
    assert "baseline 7" in check.offending[0]


def _forecast(seed: int) -> fc.MonteCarloForecast:
    history = [fc.Sprint("S1", ended_on=date(2026, 1, 14), completed_points=8.0)]
    return fc.monte_carlo_completion(
        history, remaining_points=16.0, as_of=date(2026, 1, 15), seed=seed
    )


def test_forecast_reproducible_passes_for_identical_runs() -> None:
    first, second = _forecast(seed=7), _forecast(seed=7)
    check = pc.check_forecast_reproducible("project 1", first, second)
    assert check.passed


def test_forecast_reproducible_fails_when_the_runs_diverge() -> None:
    first, second = _forecast(seed=7), _forecast(seed=8)
    check = pc.check_forecast_reproducible("project 1", first, second)
    assert not check.passed
    assert "project 1" in check.offending[0]


def test_process_state_evidence_passes_when_every_claim_is_backed() -> None:
    entries = [("4.1", "produced", True), ("5.1", "not_started", False)]
    check = pc.check_process_state_has_evidence(entries)
    assert check.passed


def test_process_state_evidence_fails_for_an_unbacked_claim() -> None:
    entries = [("4.1", "produced", False)]
    check = pc.check_process_state_has_evidence(entries)
    assert not check.passed
    assert "4.1" in check.offending[0]


class _FakeBaseline:
    """Just enough of ``Baseline`` for ``run_baseline_immutable_check`` — it only
    reads ``status``/``approved_at``/``version``/``id``, never the ORM machinery."""

    def __init__(self, status: str, approved_at: date | None, version: int = 1, id: int = 7):
        self.status = status
        self.approved_at = approved_at
        self.version = version
        self.id = id


def test_run_baseline_immutable_check_skips_an_unapproved_baseline() -> None:
    baseline = _FakeBaseline(status="draft", approved_at=None)
    check = pc.run_baseline_immutable_check(session=None, baseline=baseline)  # type: ignore[arg-type]
    assert not check.passed
    assert "nothing to test" in check.offending[0]


def test_run_baseline_immutable_check_passes_when_the_guard_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _refuse(*_args: object, **_kwargs: object) -> None:
        raise pc.HTTPException(status_code=409, detail="baseline is approved")

    monkeypatch.setattr(pc.rules, "baseline_patch_stays_valid", _refuse)
    baseline = _FakeBaseline(status="approved", approved_at=date(2026, 1, 1))
    check = pc.run_baseline_immutable_check(session=None, baseline=baseline)  # type: ignore[arg-type]
    assert check.passed


def test_run_baseline_immutable_check_fails_when_the_guard_lets_the_write_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pc.rules, "baseline_patch_stays_valid", lambda *a, **k: None)
    baseline = _FakeBaseline(status="approved", approved_at=date(2026, 1, 1))
    check = pc.run_baseline_immutable_check(session=None, baseline=baseline)  # type: ignore[arg-type]
    assert not check.passed
    assert "baseline 7" in check.offending[0]
