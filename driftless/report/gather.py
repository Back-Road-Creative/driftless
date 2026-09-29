"""Canonical adapters: stored rows -> the value objects ``driftless.calc`` consumes.

``driftless.web.home`` renders through these adapters directly, so a document figure
and the dashboard figure are built by the same code and cannot disagree. Every
collection is explicitly sorted — dict order reorders across processes and float
addition is not associative, so an unsorted spend list could change AC's last
digit run to run.

A project leaf's RAG folds two signals worst-of-wins: the milestone status
(missed -> red, at_risk -> amber) and the assessment engine's Integration
rollup, which is the worst of the nine knowledge areas (cost, schedule, quality,
risk, ...). A milestone-only verdict would show green for a project the
assessment rates red — e.g. a met milestone while cost runs red (CPI < 0.9) —
so the two are folded here. The remaining figures (budget, actual, percent,
risks) stay calc's numbers untouched.

A project with *nothing to assess* — no baseline (BAC 0), no milestones and no
status snapshots — is a special case: the assessment engine still flags its
unmeasured areas amber, but "we assessed it and it is mildly concerning" is a
false reading of an empty placeholder. Such a leaf is stamped ``unknown`` (a
distinct no-data state, rendered grey) so it reads as "there is nothing here to
assess", not as a health verdict."""

from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, NamedTuple

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from driftless.assess import adapters
from driftless.assess.engine import assess_project
from driftless.assess.model import SEVERITY_WEIGHT
from driftless.calc import evm
from driftless.calc.rollup import Kpis, LeafMetrics, Node, RagStatus, roll_up
from driftless.models import (
    Business,
    CostEntry,
    Milestone,
    Portfolio,
    Program,
    Project,
    Risk,
    StatusSnapshot,
)
from driftless.models.records import OPEN_RISK_STATUSES
from driftless.pmbok import flow_facts

HIGH_EXPOSURE = 10_000.0  # the exposure a risk must clear to count against a project
OPEN_RISKS = OPEN_RISK_STATUSES  # re-exported: driftless.web.project_hub reads gather.OPEN_RISKS
MILESTONE_RAG: dict[str, RagStatus] = {"missed": "red", "at_risk": "amber"}  # precedence order


def milestone_slip_days(milestone: Milestone) -> int | None:
    """Days between ``target_date`` and ``baseline_date`` — ``None`` when the
    milestone carries no baseline date. The one subtraction the Schedule and
    Forecast documents both read, so their slip figures cannot independently
    drift."""
    if milestone.baseline_date is None:
        return None
    return (milestone.target_date - milestone.baseline_date).days


def cell(kpis: Kpis) -> dict[str, Any]:
    """One pre-formatted KPI row for a template — the single Kpis→display formatter.

    The dashboard and the Portfolio Rollup both render these, so a figure on the
    screen and the same figure in the document are formatted by identical code
    and cannot disagree. Formatting (thousands, percent) is a view concern and
    lives here, above calc, never inside it."""
    return {
        "name": kpis.name,
        "rag": kpis.rag,
        "budget": f"{kpis.budget:,.0f}",
        "actual": f"{kpis.actual_cost:,.0f}",
        "complete": f"{kpis.percent_complete * 100:.0f}%",
        "risks": kpis.open_high_risks,
    }


def flow_cell(kpis: Kpis) -> dict[str, str | int]:
    """The three flow tiles' formatted values off ONE ``Kpis`` — home and the
    drill pages both read this, so a flow figure on the dashboard can never
    disagree with the same node's own drill page. ``no data yet`` (never 0) when no
    child rolled up any agile evidence — ``calc.rollup`` already returns
    ``None`` for exactly that case, the same "nothing measured" reading
    :func:`cell` gives every other figure here."""
    return {
        "wip": kpis.wip if kpis.wip is not None else "no data yet",
        "throughput_per_week": (
            kpis.throughput_per_week if kpis.throughput_per_week is not None else "no data yet"
        ),
        "median_cycle_days": (
            f"{kpis.median_cycle_days:.1f}" if kpis.median_cycle_days is not None else "no data yet"
        ),
    }


def _by_project(session: Session, statement: Select[Any]) -> dict[int, list[Any]]:
    """Rows of one ordered query grouped by ``project_id`` — home's ``_by_project``."""
    grouped: dict[int, list[Any]] = defaultdict(list)
    for row in session.scalars(statement):
        grouped[row.project_id].append(row)
    return grouped


_PROJECT_COSTS_CACHE_KEY = "driftless.report.gather.project_costs"


def project_costs(session: Session) -> dict[int, list[CostEntry]]:
    """Every cost entry grouped by project, ordered so AC's float sum is stable.

    Memoized on ``session.info`` — one full-table scan per session no matter how
    many callers ask, mirroring ``pmbok.state.prefetched``'s cache idiom (there,
    an explicit scope; here, transparent, since every caller already just wants
    "the current costs" with no signature to thread a scope through). ``report
    all`` renders several documents (cost-evm, forecast, weekly-status,
    department) per project per run through one read-only, single-use session
    that writes nothing — so the memo cannot go stale within that run. Callers
    that open a fresh session per request (the web app) get a fresh scan too;
    a session that both wrote a ``CostEntry`` and then called this in the same
    session would see the pre-write snapshot, but no write path in this service
    does that today."""
    cached: dict[int, list[CostEntry]] | None = session.info.get(_PROJECT_COSTS_CACHE_KEY)
    if cached is not None:
        return cached
    costs = _by_project(session, select(CostEntry).order_by(CostEntry.incurred_on, CostEntry.id))
    session.info[_PROJECT_COSTS_CACHE_KEY] = costs
    return costs


def project_evm(project: Project, costs: list[CostEntry], as_of: date) -> evm.EarnedValueSnapshot:
    """Newest baseline's lines, task progress and dated spend -> one snapshot.

    Delegates to ``driftless.assess.adapters`` — the single canonical EVM adapter —
    so the dashboard, the reports and the assessment engine all read earned value
    from the same code and cannot disagree."""
    return adapters.snapshot_from(project, costs, as_of)


def _project_node(
    session: Session,
    project: Project,
    costs: list[CostEntry],
    risks: list[Risk],
    snaps: list[StatusSnapshot],
    as_of: date,
) -> Node:
    """A rollup leaf for one project — every figure is calc's, mirroring ``home``.

    The leaf RAG is the worse (red > amber > green) of the milestone status and
    the assessment engine's Integration rollup (worst of the nine knowledge
    areas), so a met milestone cannot mask a red cost or schedule assessment.

    A project with nothing to assess — no baseline (BAC 0), no milestones and no
    status snapshots — overrides that fold with ``unknown``: an empty placeholder
    is no-data, not a mildly-concerning amber. ``snaps`` are the project's status
    snapshots up to ``as_of``, mirroring the batch ``costs``/``risks`` inputs.

    WIP, throughput and median cycle time are read only for an agile or hybrid
    project (``flow_facts.sprint_history``'s own gate) — a predictive project
    has no backlog items by construction, so calling the flow adapter for one
    would spend a query proving nothing. They stay ``None`` (the rollup's
    ``no data yet``) rather than a false zero, and the read is batched inside this
    walk's own ``adapters.prefetched`` scope like every other per-project read
    here, so a store-wide rollup pays one query set for the lot.
    """
    snap = project_evm(project, costs, as_of)
    statuses = {milestone.status for milestone in project.milestones}
    milestone_rag: RagStatus = next(
        (rag for status, rag in MILESTONE_RAG.items() if status in statuses), "green"
    )
    assessment_rag = assess_project(session, project, as_of)[0].status
    leaf_rag = max((milestone_rag, assessment_rag), key=lambda rag: SEVERITY_WEIGHT[rag])
    if snap.bac == 0 and not project.milestones and not snaps:
        leaf_rag = "unknown"
    flow = (
        flow_facts.flow_leaf_metrics(session, project, as_of)
        if project.delivery_mode in ("agile", "hybrid")
        else None
    )
    return Node(
        "project",
        project.name,
        LeafMetrics(
            Decimal(str(snap.bac)),
            Decimal(str(snap.ac)),
            Decimal(str(snap.ev / snap.bac)) if snap.bac else Decimal(0),
            sum(1 for r in risks if r.status in OPEN_RISKS and r.exposure >= HIGH_EXPOSURE),
            leaf_rag,
            wip=flow.wip if flow else None,
            throughput_per_week=flow.throughput if flow else None,
            median_cycle_days=flow.median_cycle_days if flow else None,
        ),
    )


def _businesses(session: Session) -> tuple[Business, ...]:
    """Businesses (name, id order), portfolios → programs → projects eager-loaded."""
    return tuple(
        session.scalars(
            select(Business)
            .order_by(Business.name, Business.id)
            .options(
                selectinload(Business.portfolios).options(
                    selectinload(Portfolio.programs),
                    selectinload(Portfolio.projects).options(*adapters.eager_project()),
                )
            )
        )
    )


def _grouped(portfolio: Portfolio) -> Iterator[tuple[Program | None, list[Project]]]:
    """Programs (name, id order) with their projects, then ``None`` + program-less.

    A project pointing at a program in ANOTHER portfolio has no bucket this
    walk ever yields. The API refuses to create such a row; a pre-existing one
    fails loudly here rather than silently vanishing from every rollup surface
    while the direct Project queries still show it.
    """
    by_program: dict[int | None, list[Project]] = defaultdict(list)
    for project in sorted(portfolio.projects, key=lambda p: (p.name, p.id)):
        by_program[project.program_id].append(project)
    for program in sorted(portfolio.programs, key=lambda g: (g.name, g.id)):
        yield program, by_program.pop(program.id, [])
    yield None, by_program.pop(None, [])
    if by_program:
        strays = ", ".join(
            f"project {project.id} -> program {project.program_id}"
            for projects in by_program.values()
            for project in projects
        )
        raise RuntimeError(
            f"portfolio {portfolio.id} has projects under programs it does not own: {strays}"
        )


def business_nodes(session: Session, as_of: date) -> tuple[Node, ...]:
    """One rollup branch per Business row: business → portfolio → program → project,
    every level ordered (name, id), program-less projects direct portfolio children
    (no invented bucket), businesses never merged. Batching stays ``_by_project``
    plus one ``adapters.prefetched`` scope, so the per-leaf ``assess_project``
    call reads batched rows, not a fresh query set per leaf."""
    businesses = _businesses(session)
    costs = project_costs(session)
    risks = _by_project(session, select(Risk).order_by(Risk.id))
    snaps = _by_project(
        session,
        select(StatusSnapshot).where(StatusSnapshot.taken_on <= as_of).order_by(StatusSnapshot.id),
    )

    def leaf(p: Project) -> Node:
        return _project_node(session, p, costs[p.id], risks[p.id], snaps[p.id], as_of)

    def branch(portfolio: Portfolio) -> Node:
        children: list[Node] = []
        for program, projects in _grouped(portfolio):
            nodes = tuple(leaf(p) for p in projects)
            if program is None:
                children.extend(nodes)
            else:
                children.append(Node("program", program.name, children=nodes))
        return Node("portfolio", portfolio.name, children=tuple(children))

    def tree(business: Business) -> Node:
        portfolios = sorted(business.portfolios, key=lambda p: (p.name, p.id))
        return Node("business", business.name, children=tuple(branch(p) for p in portfolios))

    every = [p for b in businesses for portfolio in b.portfolios for p in portfolio.projects]
    with adapters.prefetched(session, every):
        return tuple(tree(business) for business in businesses)


def leaf_projects(session: Session) -> tuple[Project, ...]:
    """Projects in ``business_nodes``'s exact leaf order — the dashboard's id thread."""
    return tuple(
        project
        for business in _businesses(session)
        for portfolio in sorted(business.portfolios, key=lambda p: (p.name, p.id))
        for _, projects in _grouped(portfolio)
        for project in projects
    )


@dataclass(frozen=True, slots=True)
class IdTree:
    """Real DB ids in ``business_nodes``'s exact shape (calc carries no ids)."""

    id: int
    children: tuple["IdTree", ...] = ()


def id_tree(session: Session) -> tuple[IdTree, ...]:
    """Real ids mirroring ``business_nodes`` node-for-node — same rows, sorts and
    shape — so zipping the two trees pairs every node with its stored id."""

    def branch(portfolio: Portfolio) -> IdTree:
        kids: list[IdTree] = []
        for program, projects in _grouped(portfolio):
            leaves = tuple(IdTree(p.id) for p in projects)
            kids += leaves if program is None else (IdTree(program.id, leaves),)
        return IdTree(portfolio.id, tuple(kids))

    return tuple(
        IdTree(b.id, tuple(branch(p) for p in sorted(b.portfolios, key=lambda p: (p.name, p.id))))
        for b in _businesses(session)
    )


def portfolio_nodes(session: Session, as_of: date) -> tuple[Node, ...]:
    """``business_nodes`` flattened one level — the statement guard reads this shape."""
    return tuple(pf for business in business_nodes(session, as_of) for pf in business.children)


def overview(session: Session, as_of: date) -> Kpis:
    """The whole store rolled up under one root — dashboard tiles and rollup totals."""
    return roll_up(Node("overview", "Overview", children=business_nodes(session, as_of)), as_of)


def leaves(kpis: Kpis) -> tuple[Kpis, ...]:
    """Every project leaf under ``kpis``, any depth — flat walks drop the program tier."""
    if kpis.level == "project":
        return (kpis,)
    return tuple(leaf for child in kpis.children for leaf in leaves(child))


def table_rows(
    nodes: tuple[Kpis, ...],
    ids: tuple[IdTree, ...] | None = None,
    nested: bool = False,
) -> list[dict[str, Any]]:
    """Depth-first display rows — each ``cell`` tagged with its level, projects
    under a program marked ``nested``; dashboard, drills and Portfolio Rollup
    share this walk. With ``ids`` (:func:`id_tree`'s parallel shape) every row
    carries its REAL DB ``id``; the document renderer passes none."""
    rows: list[dict[str, Any]] = []
    for position, node in enumerate(nodes):
        extra: dict[str, Any] = {"kind": node.level, "nested": nested}
        branch = ids[position] if ids is not None else None
        if branch is not None:
            extra["id"] = branch.id
        rows.append(cell(node) | extra)
        kids = branch.children if branch is not None else None
        rows.extend(table_rows(node.children, kids, node.level == "program"))
    return rows


def find_node(
    nodes: tuple[Kpis, ...], ids: tuple[IdTree, ...], kind: str, target_id: int
) -> tuple[Kpis, IdTree] | None:
    """The ``kind`` node with REAL DB id ``target_id``, paired with its id
    subtree; ``None`` only on a genuinely absent id — the drill page's 404."""
    for node, branch in zip(nodes, ids, strict=True):
        if node.level == kind and branch.id == target_id:
            return node, branch
        found = find_node(node.children, branch.children, kind, target_id)
        if found is not None:
            return found
    return None


_BUSINESS_CURVE_SAMPLES = 12  # matches views.evm_curve's per-project sample count


def sample_dates(start_candidates: Sequence[date], as_of: date, samples: int) -> tuple[date, ...]:
    """At most ``samples`` evenly-spaced DISTINCT dates from the earliest of
    ``start_candidates`` through ``as_of`` — the one clamp-and-sample window
    ``business_curve``, ``home._burn_series`` and ``views.evm_curve`` all read
    through, so the three can no longer drift apart the way they did in #1532.

    Distinct because every consumer treats each date as one reading: a span
    shorter than the sample count used to repeat dates (12 samples over a 3-day
    plan window landed on 4 calendar days), and ``home.html`` repeats the
    S-curve as one dated table row per point, so its accessible twin read the
    same date and figures three times over. Duplicates are collapsed here, once,
    rather than by each caller; a short window sweeps one sample per day.

    Clamped to ``as_of``: a start still in the future must not push sample
    dates past ``as_of``, which would count spend dated after ``as_of`` as
    already incurred. The window degenerates to a single ``as_of`` sample
    instead. ``start_candidates`` must be non-empty."""
    start = min(min(start_candidates), as_of)
    span = max(0, (as_of - start).days)
    return tuple(
        dict.fromkeys(
            start + timedelta(days=round(span * i / (samples - 1)) if span else 0)
            for i in range(samples)
        )
    )


def snapshot_sweep(
    project: Project, costs: Sequence[CostEntry]
) -> Callable[[date], evm.EarnedValueSnapshot]:
    """``as_of -> adapters.snapshot_from(project, costs, as_of)`` with each
    baseline's adaptation hoisted: the line sort and the two plan-shaped value-
    object lists vary only with WHICH baseline is in force, yet the swept
    S-curves rebuilt them at EVERY sample date — 165 adapter calls per dashboard
    GET at 5 projects, and the request cost scaled with tasks x samples instead
    of tasks + samples (99ms -> 1177ms for 5 -> 300 tasks/project). Adapted
    once per DISTINCT baseline id, memoized here as the sweep first meets it and
    reused at every later sample that resolves to the same one. Approvals are
    sparse, so a baseline approved mid-sweep costs one EXTRA adaptation, not one
    per sample: the hoist survives at the cost that actually scales (tasks),
    and :func:`adapters.plan_baseline` -- pure, no query, over the already-
    loaded ``project.baselines`` -- is cheap enough to call at every date.

    The one as-of-dependent branch — ``snapshot_from`` refuses an ``as_of``
    before the resolved plan's earliest ``planned_start`` by dropping the
    lines — is reproduced per baseline by swapping in the empty plan/progress
    lists those dropped lines would have built. Everything else is the same
    code order over the same sorts, so the floats sum identically and the
    rendered series stay byte-identical; ``tests/test_gather_sampling.py`` pins
    the sweep equal to the canonical adapter at every regime, INCLUDING a
    second baseline approved partway through the sampled window, so a caller
    that flattened the curve onto one plan cannot pass quietly."""
    spend = [
        evm.CostEntry(c.incurred_on, c.amount)
        for c in sorted(costs, key=lambda c: (c.incurred_on, c.id))
    ]
    adapted: dict[int, tuple[date | None, list[evm.BaselineTask], list[evm.ProgressReport]]] = {}

    def at(as_of: date) -> evm.EarnedValueSnapshot:
        baseline = adapters.plan_baseline(project, as_of)
        if baseline is None:
            return evm.earned_value_snapshot([], [], spend, as_of)
        if baseline.id not in adapted:
            ordered = sorted(baseline.lines, key=lambda line: line.task_id)
            begun = min((line.planned_start for line in ordered), default=None)
            plan = [
                evm.BaselineTask(str(x.task_id), x.planned_start, x.planned_finish, x.planned_cost)
                for x in ordered
            ]
            done = [
                evm.ProgressReport(str(x.task_id), date.min, x.task.percent_complete / 100)
                for x in ordered
            ]
            adapted[baseline.id] = (begun, plan, done)
        begun, plan, done = adapted[baseline.id]
        if begun is not None and as_of < begun:
            return evm.earned_value_snapshot([], [], spend, as_of)
        return evm.earned_value_snapshot(plan, done, spend, as_of)

    return at


def business_curve(
    projects: Sequence[Project], costs: dict[int, list[CostEntry]], as_of: date
) -> dict[str, Any]:
    """Whole-business planned-vs-actual cost S-curve — sums PV(t)/AC(t) across
    every project at up to ``_BUSINESS_CURVE_SAMPLES`` :func:`sample_dates` from
    the earliest baselined project's start to ``as_of``, mirroring ``views.evm_curve``
    at business scope. Each project is adapted ONCE through :func:`snapshot_sweep`,
    never re-adapted per sample. Pure and query-free (no ``Session`` at all):
    ``projects`` must carry eager-loaded baselines (as ``leaf_projects`` returns)
    and ``costs`` is the batched ``project_costs`` map. No baseline anywhere ->
    empty ``points``.

    Each point carries the ISO ``date`` it was sampled at. That date is already
    computed here to take the sample; keeping it rather than discarding it is
    what lets ``home.html`` repeat the curve as a table without re-deriving the
    sample window in the template, which would be a second implementation of
    :func:`sample_dates` free to drift from this one.

    The window is set by the same baselines the points are: this took the newest
    baseline of ANY status while every figure plotted comes from ``snapshot_from``,
    which is approved-only. So a drafted re-baseline starting earlier than the
    approved plan stretched the axis back over dates the plan had not begun, where
    nothing is earned — filling the curve with zero samples that read as reported
    figures. :func:`adapters.plan_baseline` is the one approval rule; ``None`` from
    it means no approved plan, contributing no start, exactly as a project that was
    never baselined."""
    plans = [b for b in (adapters.plan_baseline(p, as_of) for p in projects) if b is not None]
    starts = [min(line.planned_start for line in b.lines) for b in plans if b.lines]
    if not starts:
        return {"points": []}
    sweeps = [snapshot_sweep(p, costs.get(p.id, [])) for p in projects]
    points: list[dict[str, Any]] = []
    for sample in sample_dates(starts, as_of, _BUSINESS_CURVE_SAMPLES):
        snaps = [sweep(sample) for sweep in sweeps]
        points.append(
            {
                "date": sample.isoformat(),
                "pv": round(sum(s.pv for s in snaps), 2),
                "ac": round(sum(s.ac for s in snaps), 2),
            }
        )
    return {"points": points}


class TreemapRect(NamedTuple):
    """One laid-out portfolio rectangle: ``table_rows``'s own figures plus geometry.

    ``lines`` is every label line that FITS, already placed as ``(text, x, y)``, so
    ``home.html`` renders what it is given and cannot draw a label its rectangle has
    no room for -- the fit is measured here, against the real geometry, once."""

    name: str
    bac: Decimal
    rag: RagStatus
    id: int
    x: float
    y: float
    w: float
    h: float
    lines: tuple[tuple[str, float, float], ...]


_SLIVER_SHARE = 0.04  # a zero-BAC portfolio's floor, as a share of the real (nonzero) total
# home.html's ``text.tm-label`` metrics, in template units: .65rem at the 16px root is
# 10.4px, whose mean system-ui advance is ~0.55em. INSET/TOP place the first baseline.
_GLYPH, _INSET, _TOP, _LEADING, _DESCENT = 5.72, 5.0, 14.0, 12.0, 3.0


def _label_lines(
    name: str, bac: Decimal, x: float, y: float, w: float, h: float
) -> tuple[tuple[str, float, float], ...]:
    """The label lines that fit inside this rectangle, placed. Degrades by what the
    AREA affords rather than by orientation: name and budget, then the name alone,
    then a truncated name, then nothing -- the old ``w > 70 and h > 26`` gate was a
    landscape test, so it dropped the name from a tall rectangle of ample area and
    printed a 23-character one in a 71-unit box that could not hold it."""
    chars = int((w - 2 * _INSET) // _GLYPH)
    rows = 1 + int((h - _TOP - _DESCENT) // _LEADING) if h >= _TOP + _DESCENT else 0
    budget = f"{bac:,.0f}"
    if rows < 1 or chars < 1:
        return ()
    if len(name) > chars:
        name = name[: chars - 1] + "…" if chars >= 4 else ""
    elif rows >= 2 and len(budget) <= chars:
        return ((name, x + _INSET, y + _TOP), (budget, x + _INSET, y + _TOP + _LEADING))
    return ((name, x + _INSET, y + _TOP),) if name else ()


def _cut(weights: Sequence[float]) -> int:
    """The split point balancing weight across two CONTIGUOUS halves -- the given order
    is never disturbed, so the rectangles still read in the rollup table's order."""
    total, seen, best, gap = sum(weights), 0.0, 1, None
    for i in range(1, len(weights)):
        seen += weights[i - 1]
        if gap is None or abs(2 * seen - total) < gap:
            best, gap = i, abs(2 * seen - total)
    return best


def _carve(
    items: Sequence[tuple[tuple[str, Decimal, RagStatus, int], float]],
    x: float,
    y: float,
    w: float,
    h: float,
    out: list[TreemapRect],
) -> None:
    """Halve ``items`` by weight and cut the rectangle across its LONGER side, until one
    item is left -- which is what keeps every rectangle near-square at any count."""
    if len(items) == 1:
        (name, bac, rag, pid), _ = items[0]
        label = _label_lines(name, bac, x, y, w, h)
        out.append(TreemapRect(name, bac, rag, pid, x, y, w, h, label))
        return
    weights = [weight for _, weight in items]
    cut = _cut(weights)
    share = sum(weights[:cut]) / sum(weights)
    if w >= h:
        _carve(items[:cut], x, y, w * share, h, out)
        _carve(items[cut:], x + w * share, y, w * (1 - share), h, out)
    else:
        _carve(items[:cut], x, y, w, h * share, out)
        _carve(items[cut:], x, y + h * share, w, h * (1 - share), out)


def treemap_layout(
    rows: Sequence[tuple[str, Decimal, RagStatus, int]], width: float, height: float
) -> list[TreemapRect]:
    """One-level treemap: ``rows`` stay in the given order (never resorted — no
    squarify), each rectangle's area proportional to its BAC, split by :func:`_carve`.
    Every area is still exactly ``weight_i / total_weight * width * height`` —
    proportional halving preserves that at every level — so it stays hand-checkable
    without walking the layout. Claiming a share of the REMAINING rect along an
    alternating axis kept those areas but degenerated: 20 equal portfolios on the
    dashboard's 340x200 canvas ran to 30.7:1 with a 10.5-unit edge, unreadable and
    barely clickable. A zero-BAC portfolio is floored to ``_SLIVER_SHARE`` of the real
    total so it stays visible/clickable; a store where NOTHING is baselined yields no
    rectangles at all -- flooring every row evenly there would draw equal shares of a
    total that does not exist, so the caller renders its empty state rather than an
    area no figure supports."""
    real_total = sum(float(bac) for _, bac, _, _ in rows if bac > 0)
    if real_total == 0:
        return []
    floor = real_total * _SLIVER_SHARE
    weights = [float(bac) if bac > 0 else floor for _, bac, _, _ in rows]
    rects: list[TreemapRect] = []
    _carve(list(zip(rows, weights, strict=True)), 0.0, 0.0, width, height, rects)
    return rects
