"""Import a Viva Goals (retired 2025-12-31) OKR CSV export into the existing
balanced scorecard: objectives and key results, landed through the same
validated write path (``api.schemas`` + ``api.records.insert``) every other
scorecard write already uses — never a second write path.

``VIVA_COLUMNS`` is the ONE place the export's column layout is named. It is
based on the Viva Goals OKR export columns as documented publicly; unverified
against a live export — adjust ``VIVA_COLUMNS`` if yours differ. A column this
module does not name is ignored; a required column missing from the file
refuses with a message naming it, rather than guessing at a layout nobody on
this project has confirmed.

Viva Goals has no equivalent of a scorecard perspective, direction, cadence,
or amber/red tolerance band, so every imported row gets the same documented
default (below) rather than a per-row guess. Re-running the same file is
idempotent: an objective, metric definition, or observation already present
(by its natural identity) is left alone, never duplicated.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api import schemas as s
from driftless.api.records import insert
from driftless.api.schemas import ScorecardDirection, ScorecardPerspective
from driftless.models import Project
from driftless.models.scorecard import (
    METRIC_ALWAYS,
    ScorecardMetricDefinition,
    ScorecardMetricObservation,
    StrategicObjective,
)

# Based on the Viva Goals OKR export columns as documented publicly;
# unverified against a live export — adjust VIVA_COLUMNS if yours differ.
VIVA_COLUMNS = {
    "title": "Title",
    "type": "Type",
    "owner": "Owner",
    "parent": "Aligned To",
    "target": "Target Value",
    "current": "Current Value",
    "due_date": "Due Date",
}
_REQUIRED_FIELDS = ("title", "type", "parent", "target", "current", "due_date")
_OBJECTIVE_TYPE = "Objective"
_KEY_RESULT_TYPE = "Key Result"

# Documented defaults for scorecard fields Viva Goals has no source column
# for — never guessed per row.
DEFAULT_PERSPECTIVE: ScorecardPerspective = "internal_operations"
DEFAULT_DIRECTION: ScorecardDirection = "higher_is_better"
DEFAULT_UNIT = "units"
DEFAULT_CADENCE_DAYS = 30
DEFAULT_AMBER_FRACTION = 0.9
DEFAULT_RED_FRACTION = 0.75


class MissingColumn(ValueError):
    """A required Viva Goals export column was not present in the file."""


@dataclass(frozen=True)
class ImportedObjective:
    """One Viva Goals "Objective" row."""

    title: str
    owner: str | None


@dataclass(frozen=True)
class ImportedKeyResult:
    """One Viva Goals "Key Result" row, named to the objective it aligns to."""

    title: str
    objective_title: str
    owner: str | None
    target: float
    current: float | None
    due_date: date


@dataclass(frozen=True)
class ImportedScorecard:
    """Everything one Viva Goals export file described, sorted for a
    deterministic write order regardless of the source file's row order."""

    objectives: tuple[ImportedObjective, ...]
    key_results: tuple[ImportedKeyResult, ...]


@dataclass(frozen=True)
class ImportResult:
    """How many NEW rows an import created (or, under ``dry_run``, would create)."""

    objectives_created: int
    metrics_created: int
    observations_created: int


def parse_viva_goals_csv(path: str | Path) -> ImportedScorecard:
    """Parse a Viva Goals OKR CSV export, per ``VIVA_COLUMNS``.

    A row missing its title is skipped. A "Key Result" row missing its parent
    objective, due date, or target is skipped rather than guessed at; its
    current value is optional (a not-yet-started key result carries none).
    """
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        for field in _REQUIRED_FIELDS:
            column = VIVA_COLUMNS[field]
            if column not in fieldnames:
                raise MissingColumn(f"missing required column {column!r}")

        objectives: dict[str, ImportedObjective] = {}
        key_results: list[ImportedKeyResult] = []
        for row in reader:
            title = (row.get(VIVA_COLUMNS["title"]) or "").strip()
            if not title:
                continue
            row_type = (row.get(VIVA_COLUMNS["type"]) or "").strip()
            owner = (row.get(VIVA_COLUMNS["owner"]) or "").strip() or None

            if row_type == _OBJECTIVE_TYPE:
                objectives[title] = ImportedObjective(title=title, owner=owner)
            elif row_type == _KEY_RESULT_TYPE:
                parent = (row.get(VIVA_COLUMNS["parent"]) or "").strip()
                due_text = (row.get(VIVA_COLUMNS["due_date"]) or "").strip()
                target_text = (row.get(VIVA_COLUMNS["target"]) or "").strip()
                if not parent or not due_text or not target_text:
                    continue
                current_text = (row.get(VIVA_COLUMNS["current"]) or "").strip()
                key_results.append(
                    ImportedKeyResult(
                        title=title,
                        objective_title=parent,
                        owner=owner,
                        target=float(target_text),
                        current=float(current_text) if current_text else None,
                        due_date=date.fromisoformat(due_text),
                    )
                )

    return ImportedScorecard(
        objectives=tuple(sorted(objectives.values(), key=lambda o: o.title)),
        key_results=tuple(sorted(key_results, key=lambda k: (k.objective_title, k.title))),
    )


def import_viva_goals(
    db: Session, project: Project, scorecard: ImportedScorecard, *, dry_run: bool = False
) -> ImportResult:
    """Write ``scorecard`` onto ``project``'s business, through the validated
    scorecard write path. Idempotent: re-importing the same file creates no
    duplicate objective, metric definition, or observation.

    Under ``dry_run`` nothing is written — the counts reflect what WOULD be
    created without touching the database.
    """
    business_id = project.portfolio.business_id

    objective_ids: dict[str, int] = {}
    objectives_created = 0
    for objective in scorecard.objectives:
        existing = db.scalar(
            select(StrategicObjective).where(
                StrategicObjective.business_id == business_id,
                StrategicObjective.name == objective.title,
            )
        )
        if existing is not None:
            objective_ids[objective.title] = existing.id
            continue
        objectives_created += 1
        if dry_run:
            # No real id exists yet; a sentinel that matches no row lets the
            # key-result loop below still count what it would create, rather
            # than silently under-reporting every metric under a new objective.
            objective_ids[objective.title] = -1
            continue
        row = insert(
            db,
            StrategicObjective,
            s.StrategicObjectiveIn(
                business_id=business_id,
                perspective=DEFAULT_PERSPECTIVE,
                name=objective.title,
                owner=objective.owner,
            ),
        )
        objective_ids[objective.title] = row.id

    metrics_created = 0
    observations_created = 0
    for kr in scorecard.key_results:
        objective_id = objective_ids.get(kr.objective_title)
        if objective_id is None:
            continue

        existing_metric = db.scalar(
            select(ScorecardMetricDefinition).where(
                ScorecardMetricDefinition.objective_id == objective_id,
                ScorecardMetricDefinition.name == kr.title,
                ScorecardMetricDefinition.effective_from == METRIC_ALWAYS,
            )
        )
        metric_is_new = existing_metric is None
        metric_id: int | None
        if metric_is_new:
            metrics_created += 1
            if dry_run:
                metric_id = None
            else:
                metric_row = insert(
                    db,
                    ScorecardMetricDefinition,
                    s.ScorecardMetricDefinitionIn(
                        objective_id=objective_id,
                        name=kr.title,
                        direction=DEFAULT_DIRECTION,
                        unit=DEFAULT_UNIT,
                        target_value=kr.target,
                        amber_threshold=kr.target * DEFAULT_AMBER_FRACTION,
                        red_threshold=kr.target * DEFAULT_RED_FRACTION,
                        cadence_days=DEFAULT_CADENCE_DAYS,
                        owner=kr.owner,
                    ),
                )
                metric_id = metric_row.id
        else:
            assert existing_metric is not None
            metric_id = existing_metric.id

        if kr.current is None:
            continue

        if metric_is_new:
            observations_created += 1
            if dry_run or metric_id is None:
                continue
        else:
            existing_observation = db.scalar(
                select(ScorecardMetricObservation).where(
                    ScorecardMetricObservation.metric_definition_id == metric_id,
                    ScorecardMetricObservation.observed_on == kr.due_date,
                    ScorecardMetricObservation.value == kr.current,
                )
            )
            if existing_observation is not None:
                continue
            observations_created += 1
            if dry_run:
                continue

        assert metric_id is not None  # dry_run/metric_id-None both `continue` above
        insert(
            db,
            ScorecardMetricObservation,
            s.ScorecardMetricObservationIn(
                metric_definition_id=metric_id,
                observed_on=kr.due_date,
                value=kr.current,
            ),
        )

    return ImportResult(objectives_created, metrics_created, observations_created)
