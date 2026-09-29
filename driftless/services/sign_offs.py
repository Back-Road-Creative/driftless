"""Appending to the sign-off ledger, for whichever surface asked."""

from __future__ import annotations

import os

from fastapi import HTTPException
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.records import fetch
from driftless.assess import engine as assess
from driftless.db.changelog import set_actor
from driftless.models import Baseline, Gate, Project, SignOff
from driftless.pmbok import state as pmbok_state

#: A baseline sign-off is only meaningful once the version it names has been through
#: approval — a ``draft`` is still being edited, so there is no approved plan yet to
#: record a decision about. ``superseded`` stays eligible: a later re-baseline does
#: not erase the historical fact that an earlier version was signed off.
_SIGNABLE_BASELINE_STATUSES = ("approved", "superseded")

#: Refused by default — an agent's decision does not append to the ledger unless an
#: operator opts in explicitly. See ``create_sign_off``.
ALLOW_AGENT_SIGNOFF_ENV = "DRIFTLESS_ALLOW_AGENT_SIGNOFF"


def stamped_signal(db: Session, payload: s.SignOffIn) -> float | None:
    """The score a sign-off records, computed from the store and never accepted from it.

    ``signal`` is the whole re-arm mechanism — :func:`driftless.assess.engine.is_suppressed`
    keeps a signed-off threat hidden only while its live score stays no worse than this
    number — so a request-supplied one muted a threat permanently on an append-only row.
    The assessment engine is re-run here for the named project at the sign-off's own
    as-of and the score of the threat ``subject_ref`` names is taken from it (never
    rescored locally). The ref carries its own project, so a mismatched ``project_id``
    matches nothing rather than some other threat's score.

    ``None`` — which never suppresses — whenever there is no such score to record: a
    process decision, a threat that is not live at that as-of, or a sign-off naming no
    project or no as-of date, there being no clock to fall back on by design.
    """
    if payload.subject_kind != "threat" or payload.project_id is None or payload.as_of is None:
        return None
    scores = {
        threat.id: threat.score
        for assessment in assess.assess_project(
            db, fetch(db, Project, payload.project_id), payload.as_of
        )
        for threat in assessment.threats
    }
    return scores.get(payload.subject_ref)


def _validate_baseline_subject(db: Session, payload: s.SignOffIn) -> None:
    """A baseline sign-off names a real, project-scoped, approved-or-superseded row.

    Unlike a threat or a process ref — text conventions built by code, never looked
    up — ``subject_ref`` here is a ``Baseline.id`` in the store, so a stray or
    cross-project value would otherwise write a ledger entry about nothing. Checked
    here, at the one write path, rather than left to a foreign-key 500 or a silent
    orphan row.
    """
    if payload.project_id is None:
        raise HTTPException(422, "a baseline sign-off must name project_id")
    try:
        baseline_id = int(payload.subject_ref)
    except ValueError as error:
        raise HTTPException(
            422, f"subject_ref must be a baseline id, got {payload.subject_ref!r}"
        ) from error
    baseline = db.get(Baseline, baseline_id)
    if baseline is None or baseline.project_id != payload.project_id:
        raise HTTPException(404, f"no baseline {baseline_id} on project {payload.project_id}")
    if baseline.status not in _SIGNABLE_BASELINE_STATUSES:
        raise HTTPException(
            422,
            f"baseline {baseline_id} is {baseline.status!r}, not "
            f"{' or '.join(_SIGNABLE_BASELINE_STATUSES)}",
        )


def _validate_gate_subject(db: Session, payload: s.SignOffIn) -> None:
    """A gate sign-off names a real, project-scoped gate, and refuses a decision
    other than ``"waived"`` while the gate is not yet ready.

    Same shape as :func:`_validate_baseline_subject` — ``subject_ref`` is a
    ``Gate.id`` in the store, checked at the one write path rather than left to
    a foreign-key 500 or an orphan row. Readiness itself is never stored
    (:func:`driftless.pmbok.state.gate_readiness`): a gate that is not ready can
    still be waived — the sanctioned way to tailor a gate out — but recording
    it "accepted" or "resolved" before its required processes are complete
    would be a ledger entry about something that never happened.
    """
    if payload.project_id is None:
        raise HTTPException(422, "a gate sign-off must name project_id")
    try:
        gate_id = int(payload.subject_ref)
    except ValueError as error:
        raise HTTPException(
            422, f"subject_ref must be a gate id, got {payload.subject_ref!r}"
        ) from error
    gate = db.get(Gate, gate_id)
    if gate is None or gate.project_id != payload.project_id:
        raise HTTPException(404, f"no gate {gate_id} on project {payload.project_id}")
    if payload.decision == "waived":
        return
    project = fetch(db, Project, payload.project_id)
    # SignOffIn._process_records_its_as_of already refused a dateless gate decision.
    assert payload.as_of is not None
    ready, missing = pmbok_state.gate_readiness(gate, project, db, payload.as_of)
    if not ready:
        raise HTTPException(
            422,
            f"gate {gate_id} is not ready: required processes not yet complete: "
            f"{', '.join(missing)}",
        )


def create_sign_off(
    db: Session, payload: s.SignOffIn, signed_by: str, *, is_agent: bool = False
) -> SignOff:
    """Append a decision to the sign-off ledger, signed by the name already resolved.

    Append-only: there is deliberately no PATCH or DELETE for sign-offs — a reversal is
    a new row with the opposite decision, so the ledger is the whole history and the
    current position is its latest entry for a subject. Which is exactly why the
    suppression signal is :func:`stamped_signal`'s to decide and not the request's: a
    forged threshold here could never be taken back.

    ``signed_by`` arrives already decided, because deciding it needs the request and a
    service does not take one — each caller resolves it through
    :func:`driftless.api.deps.signer`, the one place that rule lives. Passing it in
    rather than re-resolving it is what keeps the name stamped exactly once per write.
    ``is_agent`` is the same shape of decision, resolved by
    :func:`driftless.api.deps.is_agent_actor`: whether the request's own credential is
    an agent Person's bound token.

    An agent actor is refused here, by default: ``DRIFTLESS_ALLOW_AGENT_SIGNOFF`` must
    be set to ``"1"`` for the row to land at all. A human sign-off is never affected —
    the check only runs for ``is_agent``. Refusing this in the store rather than only
    at the route means the one write path (this function, shared by the JSON and the
    web routes) is where the rule lives, not duplicated at each caller.

    Also credited on the ChangeLog (:func:`driftless.db.changelog.set_actor`): the
    same identity that signs the ledger row is who the audit trail blames for it,
    rather than leaving that to whatever the caller's session happened to be
    stamped with already.
    """
    if is_agent and os.environ.get(ALLOW_AGENT_SIGNOFF_ENV) != "1":
        raise HTTPException(
            403,
            f"an agent actor cannot sign off unless an operator sets {ALLOW_AGENT_SIGNOFF_ENV}=1",
        )
    set_actor(db, signed_by)
    if payload.project_id is not None:
        fetch(db, Project, payload.project_id)
    if payload.subject_kind == "baseline":
        _validate_baseline_subject(db, payload)
    if payload.subject_kind == "gate":
        _validate_gate_subject(db, payload)
    row = SignOff(
        **{
            **payload.model_dump(),
            "signed_by": signed_by,
            "signed_by_kind": "agent" if is_agent else "human",
            "signal": stamped_signal(db, payload),
        }
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
