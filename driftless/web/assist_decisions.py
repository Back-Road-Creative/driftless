"""The decisions and meetings page: ``GET/POST /projects/{project_id}/assist/decisions``.

Five routed techniques share this one page (``assess.model.ASSISTANT_ROUTES``):
Collect Requirements' (5.2) ``voting``, ``multicriteria_decision_analysis``,
``autocratic_decision_making`` and ``focus_groups``, and Direct and Manage
Project Work's (4.3) ``meetings``. Voting, scoring and facilitation are
no-write what-ifs computed purely from GET params — the same "type it, see it,
nothing saved" contract ``assist_evm``'s what-if box makes. Meeting evidence is
the one write this page allows: a POST records a ``TechniqueRun`` for
``meetings`` through :func:`driftless.services.technique_runs.record_run`, the
project's only append-only ledger of a technique actually run, never a second
store for the same fact.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from driftless.api.deps import Db
from driftless.api.records import fetch
from driftless.calc.decisions import (
    FacilitationTechnique,
    MeetingAction,
    ScoreResult,
    VoteResult,
    VotingRule,
    autocratic_record,
    facilitation_plan,
    meeting_record,
    multicriteria_score,
    vote,
)
from driftless.models import Project
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.provenance import MethodContext
from driftless.services.technique_runs import MissingActorError, record_run, runs_for_project
from driftless.web import csrf
from driftless.web.as_of import as_of_dependency
from driftless.web.errors import PageRoute
from driftless.web.templating import TEMPLATES

#: The PMBOK-6 process each routed technique on this page belongs to. Voting,
#: multicriteria analysis, autocratic decisions and focus groups are all named
#: by Collect Requirements (5.2); meeting evidence is filed against Direct and
#: Manage Project Work (4.3), the process that actually names ``meetings``.
VOTING_PROCESS_ID = "5.2"
MEETINGS_PROCESS_ID = "4.3"

#: ``Project.delivery_mode`` (``driftless/models/hierarchy.py:DELIVERY_MODES``) and
#: ``MethodContext`` are two different, unaligned vocabularies — the latter also
#: distinguishes scrum from kanban, which the project record does not carry. This is
#: the one place that crosswalks them for a stored ``TechniqueRun``: predictive maps
#: straight across, agile reads as scrum (the closer of the two ceremony-bearing
#: methods), and hybrid — which ``MethodContext`` has no member for — falls back to
#: predictive, since a hybrid project still runs *some* things on a fixed plan.
_METHOD_BY_DELIVERY_MODE: dict[str, MethodContext] = {
    "predictive": MethodContext.PREDICTIVE,
    "agile": MethodContext.SCRUM,
    "hybrid": MethodContext.PREDICTIVE,
}


def _method_context(project: Project) -> MethodContext:
    return _METHOD_BY_DELIVERY_MODE.get(project.delivery_mode, MethodContext.PREDICTIVE)


def _parse_csv(value: str | None) -> tuple[str, ...]:
    """Comma-separated names, blanks and surrounding whitespace dropped."""
    if not value:
        return ()
    return tuple(v.strip() for v in value.split(",") if v.strip())


def _parse_lines(value: str | None) -> tuple[str, ...]:
    """One entry per non-blank line — how a textarea's free text becomes a list."""
    if not value:
        return ()
    return tuple(v.strip() for v in value.splitlines() if v.strip())


def _parse_weights(value: str | None) -> dict[str, float]:
    """``"cost:0.6,quality:0.4"`` -> ``{"cost": 0.6, "quality": 0.4}``."""
    weights: dict[str, float] = {}
    for pair in _parse_csv(value):
        key, sep, raw = pair.partition(":")
        if not sep or not key.strip():
            continue
        weights[key.strip()] = float(raw)
    return weights


def _parse_scores(value: str | None) -> dict[str, dict[str, float]]:
    """``"a:cost=8,quality=5;b:cost=5,quality=9"`` -> ``{"a": {...}, "b": {...}}``."""
    scores: dict[str, dict[str, float]] = {}
    if not value:
        return scores
    for block in value.split(";"):
        option, sep, raw = block.partition(":")
        option = option.strip()
        if not sep or not option:
            continue
        row: dict[str, float] = {}
        for pair in raw.split(","):
            criterion, csep, number = pair.partition("=")
            if csep and criterion.strip():
                row[criterion.strip()] = float(number)
        scores[option] = row
    return scores


def _parse_actions(value: str | None) -> tuple[MeetingAction, ...]:
    """One action per line, ``"description | owner | YYYY-MM-DD"``; the last two
    halves are optional, and an unparseable date is dropped rather than refused —
    a facilitator typing a description alone should never lose the whole line."""
    actions = []
    for line in _parse_lines(value):
        parts = [part.strip() for part in line.split("|")]
        owner = parts[1] if len(parts) > 1 else ""
        due: date | None = None
        if len(parts) > 2 and parts[2]:
            try:
                due = date.fromisoformat(parts[2])
            except ValueError:
                due = None
        actions.append(MeetingAction(parts[0], owner, due))
    return tuple(actions)


def _meeting_inputs(
    purpose: str,
    attendees: tuple[str, ...],
    decisions: tuple[str, ...],
    actions: tuple[MeetingAction, ...],
) -> dict[str, Any]:
    return {
        "purpose": purpose,
        "attendees": list(attendees),
        "decisions": list(decisions),
        "actions": [
            {
                "description": a.description,
                "owner": a.owner,
                "due": a.due.isoformat() if a.due else None,
            }
            for a in actions
        ],
    }


def _vote_context(vote_result: VoteResult | None) -> dict[str, Any] | None:
    if vote_result is None:
        return None
    return {
        "tally": vote_result.tally,
        "leader": vote_result.leader,
        "rule": vote_result.rule.value,
        "rule_met": vote_result.rule_met,
        "explanation": vote_result.explanation,
    }


def _score_context(score_result: ScoreResult | None) -> dict[str, Any] | None:
    if score_result is None:
        return None
    return {
        "ranking": score_result.ranking,
        "winner": score_result.winner,
        "deciding_criterion": score_result.deciding_criterion,
        "sensitivity_note": score_result.sensitivity_note,
    }


def create_assist_decisions_router(default_as_of: date | Callable[[], date]) -> APIRouter:
    """The decisions and meetings page, defaulting to ``default_as_of``."""
    router = APIRouter(route_class=PageRoute)
    resolve_as_of = as_of_dependency(default_as_of)

    @router.get("/projects/{project_id}/assist/decisions", response_class=HTMLResponse)
    def assist_decisions(
        request: Request,
        project_id: int,
        db: Db,
        at: date = Depends(resolve_as_of),
        vote_options: str | None = None,
        vote_ballots: str | None = None,
        vote_rule: str = VotingRule.MAJORITY.value,
        mc_options: str | None = None,
        mc_weights: str | None = None,
        mc_scores: str | None = None,
        facil_purpose: str | None = None,
        facil_participants: str | None = None,
        facil_technique: str = FacilitationTechnique.WORKSHOP.value,
        autocratic_decider: str | None = None,
        autocratic_rationale: str | None = None,
    ) -> HTMLResponse:
        project = fetch(db, Project, project_id)

        vote_result: VoteResult | None = None
        if vote_options and vote_ballots:
            try:
                rule = VotingRule(vote_rule)
            except ValueError as error:
                raise HTTPException(422, f"unknown voting rule {vote_rule!r}") from error
            try:
                vote_result = vote(_parse_csv(vote_options), _parse_csv(vote_ballots), rule)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error

        score_result: ScoreResult | None = None
        if mc_options and mc_weights:
            try:
                score_result = multicriteria_score(
                    _parse_csv(mc_options), _parse_weights(mc_weights), _parse_scores(mc_scores)
                )
            except ValueError as error:
                raise HTTPException(422, str(error)) from error

        facilitation = None
        if facil_purpose and facil_participants:
            try:
                technique = FacilitationTechnique(facil_technique)
            except ValueError as error:
                raise HTTPException(
                    422, f"unknown facilitation technique {facil_technique!r}"
                ) from error
            try:
                facilitation = facilitation_plan(
                    facil_purpose, _parse_csv(facil_participants), technique
                )
            except ValueError as error:
                raise HTTPException(422, str(error)) from error

        autocratic = None
        if autocratic_decider and autocratic_rationale:
            try:
                autocratic = autocratic_record(autocratic_decider, autocratic_rationale)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error

        meeting_runs = [
            run for run in runs_for_project(db, project.id, at) if run.technique_key == "meetings"
        ]

        context = {
            "project": project,
            "as_of": at.isoformat(),
            "vote_options": vote_options or "",
            "vote_ballots": vote_ballots or "",
            "vote_rule": vote_rule,
            "voting_rules": [r.value for r in VotingRule],
            "vote_result": _vote_context(vote_result),
            "mc_options": mc_options or "",
            "mc_weights": mc_weights or "",
            "mc_scores": mc_scores or "",
            "score_result": _score_context(score_result),
            "facil_purpose": facil_purpose or "",
            "facil_participants": facil_participants or "",
            "facil_technique": facil_technique,
            "facilitation_techniques": [t.value for t in FacilitationTechnique],
            "facilitation": facilitation,
            "autocratic_decider": autocratic_decider or "",
            "autocratic_rationale": autocratic_rationale or "",
            "autocratic": autocratic,
            "meeting_runs": meeting_runs,
            "provenance": {
                "voting_process": VOTING_PROCESS_ID,
                "meetings_process": MEETINGS_PROCESS_ID,
                "as_of": at.isoformat(),
            },
        }
        return TEMPLATES.TemplateResponse(request, "assist_decisions.html", context)

    @router.post("/projects/{project_id}/assist/decisions")
    def assist_decisions_submit(
        request: Request,
        project_id: int,
        db: Db,
        actor: Annotated[str, Form()] = "",
        purpose: Annotated[str, Form()] = "",
        attendees: Annotated[str, Form()] = "",
        decisions: Annotated[str, Form()] = "",
        actions: Annotated[str, Form()] = "",
        as_of: Annotated[date | None, Form()] = None,
        csrf_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """File one meeting as evidence: through ``record_run``, the one write path
        every ``TechniqueRun`` goes through — never a bespoke insert here."""
        csrf.require(request, csrf_token)  # before any read or write
        project = fetch(db, Project, project_id)
        at = resolve_as_of(as_of)
        try:
            record = meeting_record(
                purpose, _parse_lines(attendees), _parse_lines(decisions), _parse_actions(actions)
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        technique = TECHNIQUES["meetings"]
        try:
            record_run(
                db,
                project_id=project.id,
                technique_key="meetings",
                process_id=MEETINGS_PROCESS_ID,
                actor=actor or None,
                as_of=at,
                method=_method_context(project),
                source_version=technique.source_version or technique.source,
                inputs_snapshot=_meeting_inputs(
                    record.purpose, record.attendees, record.decisions, record.actions
                ),
            )
        except MissingActorError as error:
            raise HTTPException(422, str(error)) from error
        return RedirectResponse(
            f"/projects/{project_id}/assist/decisions?as_of={at.isoformat()}", status_code=303
        )

    return router
