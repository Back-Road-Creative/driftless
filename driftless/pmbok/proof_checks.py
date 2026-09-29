"""Pure checks behind ``driftless pmbok proof <claim>`` — one per wedge claim in
the 2026-09-22 competitive-gap plan §2, each a pure function over already-read
data so a passing and a failing fixture cost nothing to write. A thin runner
beside each opens the session/store the CLI has in hand and hands the pure
function what it needs; the CLI only prints ``ProofCheck.report()``.

``changelog-append-only`` and ``changelog-chain`` are not here: another unit
owns the hash chain. ``reproduce`` is here, and needs no database: it reads a
saved report or page straight off disk.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from driftless.api import rules
from driftless.calc import forecast as fc
from driftless.db import Base
from driftless.models import Baseline, Portfolio, Program, Project
from driftless.pmbok import flow_facts, mapping, state
from driftless.report import receipt as report_receipt
from driftless.report.documents import forecast as forecast_doc
from driftless.web import receipt as web_receipt


@dataclass(frozen=True)
class ProofCheck:
    """One claim's verdict: whether it held, and the offending rows if not."""

    claim: str
    passed: bool
    offending: tuple[str, ...] = ()

    def report(self) -> str:
        if self.passed:
            return f"OK: {self.claim}"
        lines = [f"FAIL: {self.claim}"]
        lines.extend(f"  - {row}" for row in self.offending)
        return "\n".join(lines)


# ---- no-typed-status ------------------------------------------------------

#: Models a rollup figure is computed for, never stored on — ``calc.rollup.roll_up``
#: is the only source of a portfolio/program/project's percent complete and RAG.
_ROLLUP_MODELS: tuple[type[Base], ...] = (Portfolio, Program, Project)
_TYPED_COLUMN_NAMES = frozenset({"percent_complete", "rag_status"})


def check_no_typed_status(model_columns: Mapping[str, frozenset[str]]) -> ProofCheck:
    """Fail if any rollup-level model carries a status/percent column of its own.

    A leaf ``Task.percent_complete`` is a legitimate typed *input* — someone has
    to report it, there is nothing under a leaf to roll up from — so this checks
    only the levels the plan actually claims are computed: portfolio, program
    and project. ``model_columns`` is the model name to its mapped column names,
    read once by the runner so the check itself never touches SQLAlchemy.
    """
    claim = "portfolio/program/project status and percent complete are computed, never typed"
    offending = tuple(
        f"{name}.{column}"
        for name, columns in model_columns.items()
        for column in sorted(columns & _TYPED_COLUMN_NAMES)
    )
    return ProofCheck(claim, not offending, offending)


def rollup_model_columns() -> dict[str, frozenset[str]]:
    """The live column names of every rollup-level model, for ``check_no_typed_status``."""
    columns: dict[str, frozenset[str]] = {
        model.__name__: frozenset(model.__table__.columns.keys()) for model in _ROLLUP_MODELS
    }
    return columns


# ---- baseline-immutable ----------------------------------------------------


def check_baseline_immutable(baseline_id: int, write_was_refused: bool) -> ProofCheck:
    """Fail if a write against an approved baseline was NOT refused."""
    claim = "an approved baseline refuses every write; a plan change is a new version"
    if write_was_refused:
        return ProofCheck(claim, True)
    return ProofCheck(claim, False, (f"baseline {baseline_id} accepted a patch while approved",))


def run_baseline_immutable_check(session: Session, baseline: Baseline) -> ProofCheck:
    """Attempt a patch on ``baseline`` through the real API guard and grade it."""
    claim = "an approved baseline refuses every write; a plan change is a new version"
    if baseline.status != "approved" and baseline.approved_at is None:
        return ProofCheck(
            claim, False, (f"baseline {baseline.id} is not approved; nothing to test",)
        )
    try:
        rules.baseline_patch_stays_valid(session, baseline, {"version": baseline.version + 1})
    except HTTPException:
        refused = True
    else:
        refused = False
    return check_baseline_immutable(baseline.id, write_was_refused=refused)


# ---- forecast ---------------------------------------------------------------


def check_forecast_reproducible(
    subject: str, first: fc.MonteCarloForecast, second: fc.MonteCarloForecast
) -> ProofCheck:
    """Fail if the same seed did not give byte-identical percentiles."""
    claim = "the seeded Monte Carlo forecast is byte-identical across runs"
    if first == second:
        return ProofCheck(claim, True)
    return ProofCheck(claim, False, (f"{subject}: {first!r} != {second!r}",))


def run_forecast_check(project: Project, as_of: date, seed: int) -> ProofCheck:
    """Run the Monte Carlo forecast for ``project`` twice with the same seed and grade it."""
    claim = "the seeded Monte Carlo forecast is byte-identical across runs"
    history = flow_facts.sprint_history(project, as_of)
    if not history:
        return ProofCheck(
            claim, False, (f"project {project.id} has no completed sprint to forecast from",)
        )
    remaining = flow_facts.remaining_points(project)
    first = forecast_doc.simulate_completion(history, remaining, as_of, seed=seed)
    second = forecast_doc.simulate_completion(history, remaining, as_of, seed=seed)
    return check_forecast_reproducible(f"project {project.id}", first, second)


# ---- process-state ----------------------------------------------------------


def check_process_state_has_evidence(
    entries: list[tuple[str, str, bool]],
) -> ProofCheck:
    """Fail if a process claims produced/in-progress with no supporting artifact.

    ``entries`` is ``(process_id, state_value, any_output_present)`` — the runner
    recomputes ``any_output_present`` with the *loosest* crosswalk gate, so it
    can only find MORE evidence than ``pmbok.state.process_state`` used, never
    less: a real drift (a state claimed with nothing behind it) still fails,
    but the per-control tailoring gate that legitimately narrows evidence for
    one Monitoring & Controlling process never produces a false failure here.
    """
    claim = "ITTO process state derives only from artifacts and sign-offs, never a stored status"
    offending = tuple(
        f"{process_id} is {state_value} with no output artifact resolving present"
        for process_id, state_value, has_evidence in entries
        if state_value in ("produced", "in_progress") and not has_evidence
    )
    return ProofCheck(claim, not offending, offending)


def run_process_state_check(project: Project, session: Session, as_of: date) -> ProofCheck:
    """Recompute every catalog process's state for ``project`` and grade the evidence."""
    entries: list[tuple[str, str, bool]] = []
    for process, proc_state in state.project_process_states(project, session, as_of):
        present = any(
            mapping.resolve(kind, project, session, as_of, allow_crosswalk=True).present
            for kind in process.outputs
            if mapping.is_tracked(kind)
        )
        entries.append((process.id, proc_state.value, present))
    return check_process_state_has_evidence(entries)


# ---- reproduce ---------------------------------------------------------------


def check_reproduce(saved: str) -> ProofCheck:
    """Fail if ``saved`` (a report or web page read back off disk) carries no
    reproducibility receipt, or one that does not match the content it names.

    Format is detected from content, never the file's extension: a markdown
    report's receipt is a trailing ``<!-- receipt: ... -->`` comment
    (``driftless.report.receipt``); a saved HTML page's is the ``breadcrumbs``
    footer (``driftless.web.receipt``). A file carrying neither marker fails
    with "no receipt found" rather than being mistaken for either format.
    """
    claim = "a saved report or page's reproducibility receipt verifies against its own content"
    if report_receipt._MARKER in saved:
        verified = report_receipt.verify_receipt(saved)
    elif web_receipt._MARKER in saved:
        verified = web_receipt.verify_receipt(saved)
    else:
        return ProofCheck(claim, False, ("no receipt found in the file",))
    if verified:
        return ProofCheck(claim, True)
    return ProofCheck(claim, False, ("the receipt does not match the file's content",))


def process_state_lines(project: Project, session: Session, as_of: date) -> list[str]:
    """Every process, its state and the output artifacts that satisfy it — the
    ``process-state`` command's informational body, printed before its verdict."""
    lines = []
    for process, proc_state in state.project_process_states(project, session, as_of):
        satisfying = [
            kind
            for kind in process.outputs
            if mapping.is_tracked(kind)
            and mapping.resolve(kind, project, session, as_of, allow_crosswalk=True).present
        ]
        lines.append(
            f"{process.id}  {process.name}  [{proc_state.value}]  {', '.join(satisfying) or '(none)'}"
        )
    return lines
