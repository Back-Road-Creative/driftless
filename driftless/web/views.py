"""Presentation helpers for the ITTO web surface: the shapes a template renders.

Split out of ``web.pages`` because none of it touches a router. Every function here
takes rows (or already-resolved engine output) and returns plain dicts, lists and
strings — no request, no session dependency, no ``APIRouter``. That is what makes
them reusable: ``web.project_hub``, ``web.business_map``, ``report.gather`` and
``assess.adapters`` all call into this module, and none of them wants a router
imported as a side effect of asking for a percentage.

The router half is the per-controller modules, which import from here. The
dependency runs one way on purpose — a helper that needed the router back would be
a route, and belongs there instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.assess import engine as assess
from driftless.assess.feed import trend_delta as _trend_delta
from driftless.models import CostEntry, Project, StatusSnapshot
from driftless.pmbok import catalog, mapping, state
from driftless.pmbok.model import KnowledgeArea, Process, ProcessGroup
from driftless.report import gather

# Each of the five process states maps to one ``.st-*`` wash defined in base.html;
# the process-map legend renders from these SAME classes (via ``LEGEND`` below), so
# a swatch can never drift from the cell it explains (findings #12 / #18):
#   produced → ok (green)     signed_off → signed (teal, distinct from produced)
#   in_progress → warn        waived → muted        not_started → muted (neutral,
# not alarming red — a not-yet-started process is no-data, not a failure).
STATE_RANK = {
    "produced": "ok",
    "signed_off": "signed",
    "waived": "muted",
    "in_progress": "warn",
    "not_started": "muted",
}
# The wash cannot be the state's only carrier, and on this grid it never could: two of
# the five states share the neutral ``muted`` wash on purpose, and the five washes sit
# under 1.2:1 from each other, so in greyscale, in print, or to a colour-blind reader the
# whole grid was one colour and a WAIVED process — tailored out of every completeness
# figure — read exactly like an untouched one that counts against it. ``sr-only`` text
# does not answer that (visually hidden) and ``title=`` does not either (hover only), so
# each state also carries a MARK: a visible glyph printed in the cell and in the legend
# chip that names it. The marks are SHAPES, never hues — an empty circle (nothing yet), a
# half-filled one (under way), a filled one (produced), a check (signed off) and an em
# dash (waived: the table convention for "not applicable", and deliberately not a cross —
# tailoring a process out is a decision, not a failure). Colour now only reinforces them.
STATE_MARK = {
    "produced": "\N{BLACK CIRCLE}",
    "signed_off": "\N{CHECK MARK}",
    "in_progress": "\N{CIRCLE WITH LEFT HALF BLACK}",
    "waived": "\N{EM DASH}",
    "not_started": "\N{WHITE CIRCLE}",
}
# The legend's fixed reading order, each state paired with its live ``.st-*`` class and
# the mark its cells print, so neither can drift from the grid it explains.
LEGEND = [
    (st, STATE_RANK[st], STATE_MARK[st])
    for st in ("produced", "signed_off", "in_progress", "waived", "not_started")
]
# The sixth word the map needs — and the one ``ProcessState`` must never grow. A catalog
# process can name no output the store holds a resolver for, and once many did:
# ``process_state`` answers NOT_STARTED about the STORE (there was nothing to look for) and
# the cell printed it as a verdict on the PROJECT — work it owes and has not begun. Nothing
# is owed on such a process; the catalog not tracking it is a settled boundary, not a gap.
# How far the resolvers reach today is a measured figure, stated once under a machine check
# in ``docs/pmbok-mapping.md`` and deliberately not restated here. ``is_assessable``
# is that distinction, so the map asks it and prints the same "not tracked" an artifact
# cell prints (:func:`_artifact_cell`): one vocabulary for one fact. It stays OUT of
# ``ProcessState``, whose five members reach the rollup counts, the wizard, the report and
# the API — none of which asks this question. It stays out of the legend too, and that is
# why it is a WORD and not a sixth mark: a word carries its own meaning into greyscale and
# print with no chip to decode it, so the five-chip legend still explains every mark drawn.
UNTRACKED = "not_tracked"
CELL_RANK = {**STATE_RANK, UNTRACKED: "muted"}
CELL_MARK: dict[str, str | None] = {**STATE_MARK, UNTRACKED: None}


def state_word(process: Process, proc_state: state.ProcessState) -> str:
    """The word the map prints for one process — never a state the process is not in.

    A recorded decision outranks the coverage fact: a waived or signed-off process shows
    what someone signed, tracked or not. Only the computed NOT_STARTED — the one answer an
    untracked process reaches with nobody having decided anything — is re-read as silence.
    """
    if proc_state is state.ProcessState.NOT_STARTED and not state.is_assessable(process):
        return UNTRACKED
    return proc_state.value


def threat_cards(db: Session, as_of: date, project_id: int | None = None) -> list[dict[str, Any]]:
    """Ranked live-threat cards, each naming its project and carrying its actions.

    ``top_threats`` supplies the cross-store suppression and ranking. A per-project
    ``assess_project`` pass supplies, for each threat, the project it belongs to and
    the recommended actions its assessment attached — actions live on the
    ``Assessment``, not the ``Threat`` — keyed by the globally unique threat id.
    Both reads are pure functions of the store and ``as_of``, and the card list
    follows the engine's ranking, so the board regenerates byte-identically.

    ``project_id`` scopes every read to one project — the project hub's own use —
    so a single hub page never pays the whole-store cost: only that project's
    assessment runs, and ranking comes from ``live_threats`` (the same per-project
    engine call ``top_threats`` fans out to) instead of the store-wide feed. Both
    paths share the same ``eager_project`` options as ``engine.top_threats``, so the
    walk down to ``line.task`` never fires a lazy query per baseline line here
    either. Filtering the unscoped board by project id and calling this scoped
    would produce the same cards in the same order — both sort by the engine's one
    ranking key — so the scoped path is a cost cut, not a behavior change.

    Each card also carries a ``delta`` describing its week-over-week trend: the
    same ranked feed one week earlier (``as_of - 7d``) is loaded and threats are
    matched by their stable, severity-independent id, so ``dir`` is ``up`` when the
    score worsened, ``down`` when it improved, ``flat`` when unchanged, or ``new``
    for a threat with no counterpart a week ago. The window is measured from
    ``as_of``, never the wall clock, so the trend regenerates deterministically.
    The second load (of the prior week) is the accepted cost of that comparison —
    eager-loaded like the current week, so it is not an N+1 either.
    """
    query = select(Project).order_by(Project.name, Project.id).options(*adapters.eager_project())
    if project_id is not None:
        query = query.where(Project.id == project_id)
    projects = list(db.scalars(query))

    by_id: dict[str, dict[str, Any]] = {}
    # The one pass that is this function's own (the two ``top_threats`` calls
    # below batch inside the engine): scoped so its per-project reads are
    # batched across the whole board too, not re-queried project by project.
    with adapters.prefetched(db, projects):
        for project in projects:
            for assessment in assess.assess_project(db, project, as_of):
                actions = [
                    {
                        "label": a.label,
                        "rationale": a.rationale,
                        "technique": a.technique.display_name,
                        "launch_href": a.launch_href,
                        "reference_href": a.reference_href,
                    }
                    for a in assessment.actions
                ]
                for threat in assessment.threats:
                    by_id[threat.id] = {
                        "project_id": project.id,
                        "project_name": project.name,
                        "actions": actions,
                    }

    if project_id is not None:
        scoped_project = projects[0] if projects else None
        current = assess.live_threats(db, scoped_project, as_of) if scoped_project else ()
        prior_threats = (
            assess.live_threats(db, scoped_project, as_of - timedelta(days=7))
            if scoped_project
            else ()
        )
    else:
        current = assess.top_threats(db, as_of)
        prior_threats = assess.top_threats(db, as_of - timedelta(days=7))
    prior = {t.id: t.score for t in prior_threats}

    cards: list[dict[str, Any]] = []
    for t in current:
        meta = by_id[t.id]
        cards.append(
            {
                "id": t.id,
                "kind": t.kind,
                "severity": t.severity,
                "score": t.score,
                "description": t.description,
                "project_id": meta["project_id"],
                "project_name": meta["project_name"],
                "actions": meta["actions"],
                "delta": _trend_delta(t.score, prior.get(t.id)),
            }
        )
    return cards


def _artifact_cell(status: mapping.ArtifactStatus) -> dict[str, str]:
    """One ITTO artifact as the drill page reads it: a word for what the store knows,
    the ``.st-*`` wash the map already uses for that reading, and the resolver's own
    detail. ``not tracked`` — a kind with no resolver at all — is deliberately
    distinct from ``absent``: the first is a fact about this product, the second a
    claim about the project. The word is inside the badge, so no wash stands alone.
    """
    if status.present:
        label, rank = ("healthy", "ok") if status.healthy else ("at risk", "warn")
    elif mapping.is_tracked(status.kind):
        label, rank = "absent", "muted"
    else:
        label, rank = "not tracked", "muted"
    return {"label": label, "rank": rank, "detail": status.detail}


def process_in_project(
    process: Process, project: Project, db: Session, as_of: date
) -> dict[str, Any]:
    """The hops a theory page cannot make: one process, read against one project.

    Carries this project's live artifact status for every kind the process's ITTO
    names, its computed process state, and its knowledge area's assessment with the
    threats and actions that assessment attached. The join to the assessment is by
    name and needs no second table: ``Assessment.kind`` IS the ``KnowledgeArea``
    value for the nine evaluators, and ``integration`` for the worst-of roll-up, so
    every one of the ten areas has exactly one — pinned by a test, and answered with
    ``None`` rather than a 500 if that ever stops holding. Threats run through
    ``assess.is_suppressed``, so one signed off on the board stays hidden here too.

    Nothing is recomputed: ``mapping.resolve``, ``state.process_state`` and
    ``assess.assess_project`` are the same pure, as-of-parameterised engines the map,
    the wizard and the threat board already read, so a pinned as-of regenerates
    byte-identically and no figure here can drift from the one beside it.
    """
    with state.prefetched(db, [project]):
        artifacts = {
            kind: _artifact_cell(mapping.resolve(kind, project, db, as_of))
            for kind in dict.fromkeys((*process.inputs, *process.outputs))
        }
        cell_state = state.process_state(process, project, db, as_of).value
        area = {a.kind: a for a in assess.assess_project(db, project, as_of)}.get(
            process.area.value
        )
    return {
        "project": project,
        "as_of": as_of.isoformat(),
        "artifacts": artifacts,
        "state": cell_state,
        "rank": STATE_RANK[cell_state],
        # The distinguishing predicate the map cell cannot say in five words: a
        # process with no tracked output reads not_started about the STORE.
        "assessable": state.is_assessable(process),
        "assessment": area
        and {
            "status": area.status,
            "score": area.risk_score,
            "threats": [
                {"severity": t.severity, "description": t.description}
                for t in area.threats
                if not assess.is_suppressed(db, t, as_of)
            ],
            "actions": [
                {
                    "label": a.label,
                    "rationale": a.rationale,
                    "technique": a.technique.display_name,
                    "launch_href": a.launch_href,
                    "reference_href": a.reference_href,
                }
                for a in area.actions
            ],
        },
    }


def pct(value: float | None) -> str:
    """A 0..1 fraction as a whole-percent label, or ``no data yet`` — never a fake 0%."""
    return f"{value * 100:.0f}%" if value is not None else "no data yet"


def trend_series(snapshots: Sequence[StatusSnapshot]) -> list[dict[str, Any]]:
    """The weekly-status trend's plotted points — each carrying ``at``, its position
    along the ELAPSED span as a 0..1 fraction, not its row number.

    Snapshots are not weekly, and the form writes at whatever ``as_of`` it is posted,
    so plotting by row index drew three readings a day apart and a fourth three months
    later as four evenly spaced points — a slope reporting a rate of progress the dates
    never supported. The fraction is computed here rather than left to the template,
    which has only the loop index and ISO strings: with the arithmetic on this side the
    template cannot re-derive an ordinal axis by accident.

    A same-date correction (``models.records.StatusSnapshot``) can now leave two rows
    sharing one ``taken_on``. Plotting both would put the chart back exactly where the
    old unique constraint kept it from ever being: two disagreeing points at one x. So
    the series is deduped to one point per date -- ``snapshots`` MUST already be in
    recording order (``id`` ascending, which ``status_form`` supplies), so the dict
    below keeps the LAST row it sees per date: the highest-``id``, most-recently-
    recorded one, matching every other "latest reading" read in this codebase. Sorting
    the input by ``taken_on`` instead would make the pick depend on query return order
    among tied dates -- the nondeterminism this function exists to avoid.

    Unlike the S-curves, this series is stored rows at operator-chosen dates, which is
    why ``gather.sample_dates`` — evenly spaced by construction, and the reason the
    dashboard, burn and EVM curves index-plot honestly — cannot serve it. A lone
    snapshot spans zero days and sits at 0.0; the axis has no length to divide by.
    """
    if not snapshots:
        return []
    latest_by_date: dict[date, StatusSnapshot] = {}
    for row in snapshots:
        latest_by_date[row.taken_on] = row  # last write per date wins: recording order in
    ordered = sorted(latest_by_date.values(), key=lambda row: row.taken_on)
    first = ordered[0].taken_on
    span = (ordered[-1].taken_on - first).days
    return [
        {
            "taken_on": row.taken_on.isoformat(),
            "percent": row.percent_complete,
            "rag": row.rag_status,
            "at": ((row.taken_on - first).days / span) if span else 0.0,
        }
        for row in ordered
    ]


_EVM_SAMPLES = 12


def evm_curve(project: Project, costs: Sequence[CostEntry], as_of: date) -> dict[str, Any]:
    """Planned-vs-actual cost S-curve data for one project — pure and drift-free.

    Sweeps the two genuinely time-phased lines — PV(t) (planned value) and AC(t)
    (actual cost) — over a fixed ``_EVM_SAMPLES`` :func:`gather.sample_dates`
    from the ``adapters.plan_baseline`` window's earliest ``planned_start`` to
    ``as_of``, plus the flat BAC and the CURRENT EV/CPI/SPI/EAC as text figures.
    One selector, so the curve's x-axis is the plan its BAC came from. EV is deliberately
    a single as-of *position*, never a swept line: the model retains only each
    task's current ``percent_complete`` (no progress history), so an EV curve
    swept over past dates would be a flat, misleading fiction. ``snapshot_from``
    is pure once the baselines are loaded, so no query fires per sample date;
    with no APPROVED baseline the ``points`` list is empty and the template shows
    an empty state.
    """
    baseline = adapters.plan_baseline(project, as_of)
    lines = baseline.lines if baseline else []
    if not lines:
        return {"points": [], "bac": 0.0, "current": None}
    starts = [line.planned_start for line in lines]
    points: list[dict[str, float]] = []
    for sample in gather.sample_dates(starts, as_of, _EVM_SAMPLES):
        snap = adapters.snapshot_from(project, costs, sample)
        points.append({"pv": round(snap.pv, 2), "ac": round(snap.ac, 2)})
    current = adapters.snapshot_from(project, costs, as_of)
    return {
        "points": points,
        "bac": round(current.bac, 2),
        "current": {
            "ev": round(current.ev, 2),
            "cpi": round(current.cpi, 3) if current.cpi is not None else None,
            "spi": round(current.spi, 3) if current.spi is not None else None,
            "eac": round(current.eac, 2) if current.eac is not None else None,
        },
    }


def reference_grid() -> dict[str, dict[str, list[dict[str, str]]]]:
    """A stateless knowledge-area × process-group grid of the frozen catalog.

    The same area×group shape as :func:`process_grid`, but each cell carries only
    the process id and name — no state or rank — straight from ``catalog.PROCESSES``.
    """
    grid: dict[str, dict[str, list[dict[str, str]]]] = {
        area.value: {group.value: [] for group in ProcessGroup} for area in KnowledgeArea
    }
    for process in catalog.PROCESSES:
        grid[process.area.value][process.group.value].append(
            {"id": process.id, "name": process.name}
        )
    return grid


def process_grid(
    states: Sequence[tuple[Process, state.ProcessState]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """A knowledge-area × process-group grid of process cells, each with its state.

    Takes the project's ``project_process_states`` result directly — the caller
    computes it once (inside a ``pmbok.state.prefetched`` scope) and threads it
    here rather than this re-walking the store itself.
    """
    by_id = {p.id: s for p, s in states}
    grid: dict[str, dict[str, list[dict[str, Any]]]] = {
        area.value: {group.value: [] for group in ProcessGroup} for area in KnowledgeArea
    }
    for process in catalog.PROCESSES:
        cell_state = state_word(process, by_id[process.id])
        grid[process.area.value][process.group.value].append(
            {
                "id": process.id,
                "name": process.name,
                "state": cell_state,
                "rank": CELL_RANK[cell_state],
                "mark": CELL_MARK[cell_state],
            }
        )
    return grid


def area_completeness(
    states: Sequence[tuple[Process, state.ProcessState]],
) -> dict[str, float | None]:
    """Per-knowledge-area completion, the SAME rule as ``state.completeness`` grouped by area.

    For each area: the share of its assessable, non-waived processes that are
    PRODUCED or SIGNED_OFF — waived and untrackable processes are excluded exactly
    as :func:`state.completeness` excludes them, so the ring's percentage can never
    drift from the states the grid renders. Takes the SAME ``project_process_states``
    result the grid renders from — the caller computes it once (inside a
    ``pmbok.state.prefetched`` scope) and threads it here, so a page with both a
    grid and rings never walks the store for the same states twice. ``None`` for
    an area with nothing to assess (rendered as a ``no data yet`` ring, never a fake 0%).
    Pure and deterministic.
    """
    counted: dict[str, int] = {area.value: 0 for area in KnowledgeArea}
    done: dict[str, int] = {area.value: 0 for area in KnowledgeArea}
    for process, process_state in states:
        if state.excluded_from_completeness(process, process_state):
            continue
        counted[process.area.value] += 1
        if process_state in (state.ProcessState.PRODUCED, state.ProcessState.SIGNED_OFF):
            done[process.area.value] += 1
    return {area: (done[area] / counted[area] if counted[area] else None) for area in counted}
