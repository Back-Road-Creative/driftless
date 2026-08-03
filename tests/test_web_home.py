"""Contract tests for the home dashboard: it is mounted on the app the server
actually serves, its figures are the ones ``driftless.calc`` produces from the same
rows, the as-of date is an input rather than the wall clock, RAG rolls up
worst-child-wins, and an empty store renders a page."""

import re
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.assess.feed import attention_feed
from driftless.db import Base, new_engine, new_session_factory
from driftless.pmbok.rollup import business_completeness, business_process_cells
from driftless.report import gather
from driftless.report.documents import business_rollup
from driftless.web import create_router, csrf
from driftless.web.home import _burn_series
from test_web_a11y import _TEMPLATES, _ratio, _token_sets

AS_OF = date(2026, 3, 31)
JAN = date(2026, 1, 31)
JUN = date(2026, 6, 30)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    """A session on a throwaway SQLite *file*: an in-memory URL would give each
    connection its own empty database."""
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(create_router(AS_OF))
    app.dependency_overrides[get_session] = lambda: db
    # https, as production serves: an http jar drops the ``Secure`` CSRF cookie, so a
    # re-render would remint the token and the byte-identity checks could not hold.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


def _portfolio(name: str) -> m.Portfolio:
    return m.Portfolio(name=name, business=m.Business(name=f"BRC {name}"))


def _project(
    db: Session,
    portfolio: m.Portfolio,
    name: str,
    *,
    percent: int = 0,
    milestone: str = "pending",
    planned: float = 1000.0,
    spends: tuple[tuple[date, float], ...] = (),
    risks: tuple[tuple[str, float, float], ...] = (),
    program: m.Program | None = None,
) -> None:
    """One project with a single baselined task, plus its dated records."""
    project = m.Project(name=name, portfolio=portfolio, delivery_mode="predictive", program=program)
    stream = m.Workstream(name=name, project=project)
    task = m.Task(name=name, workstream=stream, estimate_unit="hours", percent_complete=percent)
    baseline = m.Baseline(project=project, version=1, status="approved")
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=planned)
    line.planned_start, line.planned_finish = JAN, AS_OF
    db.add(line)
    db.add(m.Milestone(project=project, name=name, target_date=AS_OF, status=milestone))
    for on, amount in spends:
        db.add(m.CostEntry(project=project, category="labour", incurred_on=on, amount=amount))
    for s, p, i in risks:
        db.add(m.Risk(project=project, description="r", status=s, probability=p, impact=i))
    db.commit()


def _tile(html: str, name: str) -> str:
    found = re.search(rf'id="kpi-{name}" class="value"[^>]*>([^<]*)<', html)
    assert found is not None, f"no {name} KPI tile in the page"
    return found.group(1)


def _rags(html: str) -> list[str]:
    return re.findall(r'<tr class="portfolio" data-rag="(\w+)"', html)


def _projects(html: str) -> list[str]:
    # The name cell now links to the project detail page, so skip the anchor open.
    return re.findall(r'<tr class="project" data-rag="\w+">\s*<td[^>]*>(?:<a[^>]*>)?([^<]*)<', html)


def test_the_dashboard_is_mounted_on_the_app_the_server_serves(db: Session) -> None:
    """Reached through ``driftless.api.app.app``, not a bare router assembled here.

    The page was fully tested before anything mounted it, so ``GET /`` answered
    404 on the running app; only a request through the real app object catches
    that, and the default as-of it stamps proves the wall clock is read per
    request rather than frozen at import.
    """
    real_app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(real_app) as client:
            page = client.get("/")
    finally:
        real_app.dependency_overrides.clear()

    assert page.status_code == 200, page.text
    assert date.today().isoformat() in page.text


def test_the_default_as_of_is_resolved_once_per_request(db: Session) -> None:
    """A callable default is called per request, so a process that stays up for
    weeks never keeps serving the date it booted on."""
    dates = iter((JAN, JUN))
    app = FastAPI()
    app.include_router(create_router(lambda: next(dates)))
    app.dependency_overrides[get_session] = lambda: db

    with TestClient(app) as client:
        assert JAN.isoformat() in client.get("/").text
        assert JUN.isoformat() in client.get("/").text


def test_an_empty_store_renders_the_onboarding_call_to_action(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200, page.text
    assert "no portfolios" in page.text.lower()
    assert (_tile(page.text, "budget"), _tile(page.text, "on-track")) == ("0", "n/a")
    assert 'id="onboarding"' in page.text and "wizard" in page.text and "<table" not in page.text
    assert (_tile(page.text, "threats"), _tile(page.text, "process")) == ("0", "n/a")
    assert "Nothing needs attention" in page.text, "the empty rail states it plainly"
    assert 'class="scurve"' not in page.text and 'class="treemap"' not in page.text, (
        "an empty store has nothing to chart -- just the CTA"
    )


def test_the_home_renders_the_business_curve_and_the_treemap(
    client: TestClient, db: Session
) -> None:
    """Two server-rendered inline-SVG charts under the KPI strip: the business-
    wide cost S-curve (planned vs actual, both series legended by a colour chip
    plus a word, only the final value on each line labeled) and the portfolio
    treemap (one rectangle per portfolio, RAG-coloured, linking its real drill
    id, a title tooltip on every rectangle). Both are pure functions of the
    engine's own figures, so a pinned as-of renders byte-identically twice."""
    portfolio = _portfolio("Content Brands")
    _project(db, portfolio, "GMS", percent=25, spends=((JAN, 400.0),))
    pf = db.query(m.Portfolio).one()

    page = client.get("/").text
    assert page == client.get("/").text, "a pinned as-of renders byte-identically"
    assert 'class="scurve"' in page and page.count("<polyline") >= 2, "two swept series render"
    assert "Planned" in page and "Actual" in page, (
        "the legend names both series, never colour-alone"
    )
    assert 'class="treemap"' in page
    # F-T11: base.html emits <title>driftless</title> on every page, so the old
    # '"<title>" in page' passed with ZERO rectangles drawn. Demand the real thing:
    # each treemap link keyboard-reachable (tabindex — engines do not all focus an
    # SVG <a>) and opening with a <title> naming the portfolio, its BAC and its RAG
    # as a word, so the fill hue is never the verdict's only carrier (F-G6, F-G9).
    found = re.findall(
        r'<a href="/portfolios/(\d+)/rollup" tabindex="0"><title>([^<]+)</title>', page
    )
    rect = re.search(r'<rect class="tm (\w+)"', page)
    assert rect is not None, "the treemap draws a rectangle"
    word = "no data" if rect.group(1) == "unknown" else rect.group(1)
    assert found == [(str(pf.id), f"Content Brands — 1,000 — {word}")], (
        "each treemap link opens with its portfolio, BAC and RAG spelled out"
    )


def test_the_two_scurve_series_are_told_apart_by_stroke_never_colour_alone(
    client: TestClient, db: Session
) -> None:
    """Both series were ``.s-line`` with ``stroke: currentColor`` and no dash —
    indistinguishable in greyscale or print; the weekly-status EVM chart already
    dashes AC for exactly this reason (F-G7). The actual polyline dashes, the
    planned one stays solid, and the legend says which is which in words."""
    _project(db, _portfolio("Content Brands"), "GMS", percent=25, spends=((JAN, 400.0),))

    page = client.get("/").text
    classes = re.findall(r'<polyline class="(s-line[^"]*)"', page)
    assert classes == ["s-line", "s-line ac"], "the two series carry distinct classes"
    assert _declared(".s-line.ac", "stroke-dasharray"), "the actual series is dashed"
    assert "Planned (solid)" in page and "Actual (dashed)" in page, (
        "the legend states the carrier in words a greyscale reader keeps"
    )


# The S-curve's own geometry, measured off the rendered SVG rather than eyeballed: two
# end labels in the same horizontal band print on top of each other, and a chart that
# silently disappears is a chart the reader cannot ask for.
def _curve_labels(html: str) -> list[tuple[float, str]]:
    """Every S-curve end label as (baseline y, printed figure), read out of the SVG."""
    return [
        (float(y), text)
        for y, text in re.findall(
            r'<text class="curve-label"[^>]*\by="([\d.-]+)"[^>]*>([^<]*)</text>', html
        )
    ]


def _px(selector: str, prop: str) -> float:
    """``selector``'s ``prop`` in px — the shipped rem value at the 16px root."""
    value = _declared(selector, prop)
    assert value is not None, f"{selector} declares no {prop}"
    return float(value.removesuffix("rem")) * 16 if value.endswith("rem") else float(value)


def test_the_two_scurve_end_labels_never_print_on_top_of_each_other(
    client: TestClient, db: Session
) -> None:
    """Planned and actual finishing within a few percent of each other — the healthy
    case, and the one a reader most wants to read precisely — put both end labels in
    the same horizontal band: 7.1 user units apart under an 11.2px glyph box, two
    thousand-separated figures overprinted. They keep a line height between them,
    both stay inside the viewBox, and the actual label is tinted by its own series
    (it sat outside the <g> carrying the RAG colour, so neither was attributable)."""
    _project(db, _portfolio("Content Brands"), "GMS", planned=51000.0, spends=((JAN, 54260.0),))

    page = client.get("/").text
    labels = _curve_labels(page)
    assert [text for _, text in labels] == ["51,000", "54,260"], "both endpoints are labelled"
    height, (low, high) = _px("text.curve-label", "font-size"), sorted(y for y, _ in labels)
    assert high - low >= height, f"labels {high - low:.2f}u apart, under a {height:.1f}px line"
    assert low >= height * 0.8 and high <= 150 - height * 0.25, "both glyph boxes stay in view"
    assert min(labels)[1] == "54,260", "the higher figure keeps the higher label"
    tinted = re.search(r'<g class="(?:green|amber|red|unknown)">(.*?)</g>', page, re.S)
    assert tinted is not None and "54,260" in tinted.group(1), (
        "the actual end label is tinted by its own series, never left in --ink"
    )


def test_the_dashboard_says_why_the_scurve_is_missing(client: TestClient, db: Session) -> None:
    """Portfolios recorded and no approved baseline anywhere: ``curve.points`` is empty,
    so the whole S-curve section vanished while the treemap kept its slot beside it, and
    nothing told the reader a chart was missing or how to get it. The shared empty state
    stands in and names the next step, the way gantt.html does for the same input."""
    for name in ("Content", "Fleet"):
        db.add(m.Project(name=name, portfolio=_portfolio(name), delivery_mode="predictive"))
    db.commit()

    page = client.get("/").text
    assert 'class="scurve"' not in page, "no curve is drawn from figures that do not exist"
    assert 'id="curve-empty"' in page, "the shared empty state stands in for the chart"
    assert "/baselines" in page, "naming the next step, the way the Gantt does"


# The treemap's other two contracts, both computed rather than eyeballed: a label sits
# INSIDE a --rag-* rectangle, so that fill — not the page — is what it must clear; and
# the chart never claims an area it has no figures for. The WCAG machinery is
# test_web_a11y's, reused rather than restated, so one formula rates every pairing.
_RAG_FILLS = ("green", "amber", "red", "unknown")
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _home_css() -> str:
    """home.html's own stylesheet, Jinja comments stripped — the rules a browser sees."""
    block = re.search(r"<style>(.*?)</style>", (_TEMPLATES / "home.html").read_text(), re.S)
    assert block is not None, "home.html carries an inline <style> block"
    return re.sub(r"\{#.*?#\}", "", block.group(1), flags=re.S)


def _declared(selector: str, prop: str) -> str | None:
    """The value ``prop`` finally takes for ``selector`` in that stylesheet."""
    value = None
    for selectors, body in _RULE.findall(_home_css()):
        if any(part.strip() == selector for part in selectors.split(",")):
            for declaration in body.split(";"):
                name, _, found = declaration.partition(":")
                if name.strip() == prop:
                    value = found.strip()
    return value


def _fill_token(selector: str) -> str:
    """The palette token ``selector``'s fill resolves to. ``currentColor`` is the body's
    ``--ink``: no rule sets ``color`` on the treemap, its links or its text."""
    value = _declared(selector, "fill")
    if value == "currentColor":
        return "--ink"
    found = re.fullmatch(r"var\((--[a-z-]+)\)", value or "")
    assert found is not None, f"{selector} declares fill {value!r}, not a var(--token)"
    return found.group(1)


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_every_treemap_label_is_legible_on_the_rectangle_it_sits_in(scheme: str) -> None:
    """A label is drawn at ``x = r.x + 5`` — inside its own rect — so it is read
    against that --rag-* fill, never against the page. Both hexes come out of the
    shipped CSS and the ratio is computed here: ``currentColor`` resolved to --ink and
    every cell landed at 2.66–3.48:1 (light) / 1.74–2.51:1 (dark), under the 4.5:1 AA
    floor for 10.4px text. Opacity is rated too — compositing a pair back toward its
    background defeats the rating (the budget line ran .8, i.e. 2.37:1 on --rag-red)."""
    tokens, label = _token_sets()[scheme], _fill_token("text.tm-label")
    failures: list[str] = []
    for rag in _RAG_FILLS:
        fill = _fill_token(f"rect.tm.{rag}")
        ratio = _ratio(tokens[label], tokens[fill])
        if ratio < 4.5:
            failures.append(
                f"{scheme}: label {label} {tokens[label]} on {fill} {tokens[fill]} "
                f"is {ratio:.2f}:1, want 4.5:1"
            )
    assert not failures, "\n".join(failures)
    assert not any(_declared(sel, "opacity") for sel in ("text.tm-label", "text.tm-budget")), (
        "a treemap label carries no opacity: compositing defeats the rated pair above"
    )


def test_the_treemap_draws_no_area_when_no_portfolio_has_a_budget(
    client: TestClient, db: Session
) -> None:
    """Two portfolios with no approved baseline have no BAC between them, and the
    all-zero layout branch floored both evenly — an exact 50/50 split under a heading
    and an aria-label that each promise area proportional to BAC. There is no area to
    draw, so the surface says so and names the next step instead of inventing one."""
    for name in ("Content", "Fleet"):
        db.add(m.Project(name=name, portfolio=_portfolio(name), delivery_mode="predictive"))
    db.commit()

    page = client.get("/").text
    assert 'class="treemap"' not in page, "no rectangles are drawn for figures that do not exist"
    assert "proportional to BAC" not in page, "and nothing claims an area is proportional"
    assert 'id="treemap-empty"' in page, "the shared empty state stands in for the chart"
    assert "/baselines" in page, "naming the next step, the way the Gantt does"


_CANVAS = (340.0, 200.0)  # must match home.TREEMAP_W/TREEMAP_H


@pytest.mark.parametrize("count", [2, 4, 5, 8, 12, 20])
def test_the_treemap_stays_readable_as_portfolios_multiply(count: int) -> None:
    """Each item claimed its share of the REMAINING rect along an alternating axis, so
    rectangles degenerated as portfolios accumulated: measured on the real canvas, 20
    ran to 30.7:1 with a 10.5-unit edge, and the fixed ``w > 70 and h > 26`` label gate
    — a landscape test — left 1 of 20 named. Splitting on weight down the LONGER axis
    keeps every rectangle roughly square, and a fit test that degrades keeps a name in
    each. Both measured, never eyeballed."""
    rows = [(f"Portfolio {i}", Decimal("1000"), "green", i) for i in range(count)]
    rects = gather.treemap_layout(rows, *_CANVAS)
    worst = max(max(r.w, r.h) / min(r.w, r.h) for r in rects)
    assert worst <= 3.5, f"{count} portfolios: worst aspect ratio {worst:.1f}:1"
    assert all(r.lines for r in rects), (
        f"{count} portfolios: {sum(1 for r in rects if not r.lines)} rectangles go unnamed"
    )


def test_a_treemap_label_never_overflows_the_rectangle_it_is_drawn_in() -> None:
    """One portfolio carrying most of the budget is the commoner real distribution and
    was the worst case: rectangles 3.6 units wide. The old gate was blind in the other
    direction too — ``w > 70`` printed a 23-character name in a 71-unit box regardless
    of how wide that name really is. The layout now measures the fit and hands the
    template placed lines, so an overflowing label cannot be emitted at all."""
    rows = [("Content Brands Flagship", Decimal("100000"), "green", 0)] + [
        (f"Small portfolio {i}", Decimal("1000"), "green", i) for i in range(1, 9)
    ]
    rects = gather.treemap_layout(rows, *_CANVAS)
    assert max(max(r.w, r.h) / min(r.w, r.h) for r in rects) <= 3.5, "no rectangle is a sliver"
    assert rects[0].lines, "the dominant portfolio has room for its name and its budget"
    for rect in rects:
        for text, x, y in rect.lines:
            assert rect.x <= x and x + len(text) * gather._GLYPH <= rect.x + rect.w, (
                f"{text!r} overflows the {rect.w:.1f}-unit rectangle it is drawn in"
            )
            assert rect.y < y <= rect.y + rect.h, f"{text!r} is drawn outside its rectangle"


def test_every_figure_comes_from_the_calc_core(client: TestClient, db: Session) -> None:
    portfolio = _portfolio("Content Brands")
    high, closed, low = ("open", 0.5, 40_000.0), ("closed", 0.9, 90_000.0), ("open", 0.1, 1_000.0)
    _project(db, portfolio, "GMS", percent=25, spends=((JAN, 400.0),), risks=(high, closed, low))
    _project(db, portfolio, "BTB", percent=75, planned=3000.0, spends=((JAN, 2000.0),))

    page = client.get("/").text
    # Budget-weighted, never averaged: (1000*0.25 + 3000*0.75) / 4000 = 62%.
    assert (_tile(page, "budget"), _tile(page, "actual")) == ("4,000", "2,400")
    assert _tile(page, "complete") == "62%"
    assert _tile(page, "risks") == "1", "only open risks over the exposure threshold count"


def test_the_as_of_date_is_an_input_not_the_wall_clock(client: TestClient, db: Session) -> None:
    _project(db, _portfolio("Content Brands"), "GMS", spends=((JAN, 400.0), (JUN, 250.0)))

    assert _tile(client.get("/").text, "actual") == "400", "spend after as-of must not count"
    later = client.get("/", params={"as_of": JUN.isoformat()}).text
    assert _tile(later, "actual") == "650"
    assert JUN.isoformat() in later, "the page states the date it was computed for"


def test_rag_rolls_up_worst_child_wins(client: TestClient, db: Session) -> None:
    portfolio = _portfolio("Content Brands")
    # AAA is complete and its milestone met, yet the assessment engine rates it
    # amber (quality unmeasured, status reporting absent) — a met milestone no
    # longer forces the leaf green. BBB missed its milestone, so it is red.
    _project(db, portfolio, "AAA", percent=100, milestone="met")
    _project(db, portfolio, "BBB", milestone="missed")
    _project(db, _portfolio("Zeta"), "CCC", percent=100, milestone="met")

    page = client.get("/").text
    assert _rags(page) == ["red", "amber"], "portfolio rolls up worst child: red over amber"
    assert _tile(page, "on-track") == "0%", "the assessment finds gaps in every project"


def test_home_extends_base_nav_and_links_each_project_to_its_detail(
    client: TestClient, db: Session
) -> None:
    """The dashboard is no longer a dead end: it inherits base.html's shared nav
    (Dashboard | Threats) and every project row links to its project hub,
    so the issue-identification path is reachable from the first hop."""
    _project(db, _portfolio("Content Brands"), "GMS", percent=25)
    project = db.query(m.Project).one()

    page = client.get("/").text
    assert 'href="/threats"' in page, "the shared nav from base.html is present"
    assert f'href="/projects/{project.id}/hub"' in page, "each project row links to its hub page"


BURN_SAMPLES = 10  # must match home._burn_series's fixed sample count


def _burn_polyline(html: str) -> list[str]:
    """The AC burn polyline's coordinate pairs — one per fixed sample date."""
    found = re.search(r'class="burn-ac" points="([^"]*)"', html)
    assert found is not None, "the project row carries an AC burn polyline"
    return found.group(1).split()


def test_the_home_row_renders_a_burn_sparkline(client: TestClient, db: Session) -> None:
    """Each project row shows an inline-SVG burn sparkline: cumulative actual cost
    rising over time (a polyline built from the dated CostEntry rows) against the
    flat BAC reference line — honest, genuinely time-phased, and stored nowhere new."""
    _project(
        db,
        _portfolio("Content Brands"),
        "GMS",
        percent=50,
        planned=1000.0,
        spends=((JAN, 200.0), (date(2026, 2, 28), 300.0), (AS_OF, 100.0)),
    )
    page = client.get("/").text
    assert "<svg" in page and 'class="burn"' in page, "an inline sparkline renders"
    assert 'class="burn-bac"' in page, "the flat BAC reference line is drawn"
    # One AC point per fixed sample date proves the line is swept from the data.
    assert len(_burn_polyline(page)) == BURN_SAMPLES


def test_the_burn_budget_reference_is_not_clipped_by_its_own_viewbox(
    client: TestClient, db: Session
) -> None:
    """A project still under budget — the normal case — made ``ymax == bac``, so the
    dashed reference landed on y = 0, the exact top edge of the 24-unit viewBox. SVG
    clips overflow, so half the stroke was gone and the line read as a box edge or as
    absent. Measured off the rendered SVG: the whole stroke stays inside the box."""
    _project(db, _portfolio("Content Brands"), "GMS", planned=1000.0, spends=((JAN, 400.0),))

    page = client.get("/").text
    found = re.search(r'<line class="burn-bac"[^>]*y1="([\d.]+)"[^>]*y2="([\d.]+)"', page)
    assert found is not None, "an under-budget row still draws its budget reference"
    half, ys = _px(".burn-bac", "stroke-width") / 2, [float(g) for g in found.groups()]
    assert min(ys) >= half, f"the reference sits at y={min(ys)}, half-clipped by the top edge"
    assert max(ys) <= 24 - half, "and its whole stroke clears the bottom edge"


def test_the_home_handles_a_project_with_no_baseline(client: TestClient, db: Session) -> None:
    """A project with no baseline has nothing to burn against: its row renders a dash
    placeholder and the page stays 200 — never a broken ``points=""`` polyline."""
    db.add(
        m.Project(
            name="Unplanned", portfolio=_portfolio("Content Brands"), delivery_mode="predictive"
        )
    )
    db.commit()

    page = client.get("/")
    assert page.status_code == 200, page.text
    assert 'class="burn-empty"' in page.text, "the empty-baseline row renders a dash"
    assert 'points=""' not in page.text, "no broken empty polyline is emitted"


def test_burn_series_never_samples_past_as_of(db: Session) -> None:
    """A project whose planned start is still in the future must not push the
    burn curve's sample dates past ``as_of``: the old span clamp collapsed
    every sample onto that future start date itself -- which is AFTER as_of --
    so a burn line "as of AS_OF" was counting a cost entry dated after AS_OF."""
    future_start = date(2026, 5, 1)
    portfolio = _portfolio("Content Brands")
    project = m.Project(name="Future", portfolio=portfolio, delivery_mode="predictive")
    stream = m.Workstream(name="Future", project=project)
    task = m.Task(name="Future", workstream=stream, estimate_unit="hours", percent_complete=0)
    baseline = m.Baseline(project=project, version=1, status="approved")
    line = m.BaselineLine(baseline=baseline, task=task, planned_cost=3000.0)
    line.planned_start, line.planned_finish = future_start, date(2026, 5, 31)
    db.add(line)
    cost = m.CostEntry(
        project=project, category="labour", incurred_on=date(2026, 4, 15), amount=999.0
    )
    db.add(cost)
    db.commit()

    burn = _burn_series(project, [cost], AS_OF)

    assert burn["points"], "a baselined project still produces points"
    assert all(p == {"ac": 0.0} for p in burn["points"]), (
        "every sample must clamp to as_of: the cost entry dated between as_of "
        "and the future start must never be counted"
    )


def test_each_portfolio_drills_down_to_its_projects(client: TestClient, db: Session) -> None:
    """The leaves of the same rollup, listed under their portfolio — the drill-down
    reads calc's per-project KPIs, it does not re-aggregate anything."""
    portfolio = _portfolio("Content Brands")
    _project(db, portfolio, "GMS", percent=25, milestone="missed")
    _project(db, portfolio, "BTB", percent=75, planned=3000.0)

    page = client.get("/").text
    # Projects list in the byte-stable (name, id) order gather sorts by — the same
    # order the Portfolio Rollup document uses, so screen and document agree.
    assert _projects(page) == ["BTB", "GMS"]
    assert _rags(page) == ["red"], "portfolio rows still carry the rolled-up verdict"
    assert re.search(r'<tr class="project" data-rag="red">\s*<td[^>]*><a[^>]*>GMS</a></td>', page)
    assert ">75%<" in page, "each project shows its own percent complete, not the parent's"


def test_program_tier_renders_and_page_agrees_with_the_rollup_document(
    client: TestClient, db: Session
) -> None:
    """A program nests its projects (still real leaves, counted in the tiles), a
    program-less project stays a direct child, the single business's real name
    heads the page, and the page shares its figures with the Portfolio Rollup."""
    portfolio = _portfolio("Content Brands")
    _project(db, portfolio, "GMS", percent=25, program=m.Program(name="Video", portfolio=portfolio))
    _project(db, portfolio, "Solo", percent=75, planned=3000.0, spends=((JAN, 400.0),))

    page = client.get("/").text
    assert page == client.get("/").text, "a pinned as-of renders byte-identically"
    assert "<h1>BRC Content Brands</h1>" in page, "the real business name heads the dashboard"
    assert re.search(r'<tr class="program" data-rag="\w+">\s*<td><a[^>]*>Video</a></td>', page)
    assert re.search(r'class="project nested"[^>]*>\s*<td[^>]*><a[^>]*>GMS', page)
    assert _projects(page) == ["Solo"], "the program-less project stays a direct child"
    assert (_tile(page, "budget"), _tile(page, "complete")) == ("4,000", "62%")
    doc = business_rollup.render(db, AS_OF)
    for tile in ("budget", "actual", "on-track"):
        assert _tile(page, tile) in doc, f"dashboard and document disagree on {tile}"


def _freshness(html: str) -> list[str]:
    """The per-project 'last status' cell contents, in row order."""
    return re.findall(r'<td class="freshness">([^<]*)</td>', html)


def test_the_home_shows_status_freshness(client: TestClient, db: Session) -> None:
    """Each project row shows the taken_on of its most recent StatusSnapshot, so a
    viewer sees at a glance how fresh each project's weekly status reporting is —
    the newest reading wins, an older one never shadows it (finding #19)."""
    _project(db, _portfolio("Content Brands"), "GMS", percent=25)
    project = db.query(m.Project).one()
    old, latest = date(2026, 1, 15), date(2026, 3, 15)
    for taken_on in (old, latest):
        db.add(
            m.StatusSnapshot(
                project_id=project.id, taken_on=taken_on, percent_complete=50, rag_status="green"
            )
        )
    db.commit()

    page = client.get("/").text
    assert _freshness(page) == [latest.isoformat()], "the row shows the most recent status date"


def _rail_ids(html: str) -> list[str]:
    return re.findall(r'data-item-id="([^"]+)"', html)  # rail item ids, page order


def test_the_kpi_strip_and_rail_render_the_engine_figures_and_feed_verbatim(
    client: TestClient, db: Session
) -> None:
    """Two new strip tiles (open threats, pooled process completeness) and the
    rail: the feed's EXACT order, threat items carrying the /sign-off form with
    the raw threat ref, data signals linking their fix surface."""
    content = _portfolio("Content Brands")
    _project(db, content, "GMS", percent=20, spends=((JAN, 800.0),))
    # A plan with nothing spent or filed against it: the derived work-performance
    # resolvers lift a project WITH dated actuals over the threshold (GMS reads
    # 0.27), so this is the one still signalling low completeness.
    _project(db, content, "Bare")

    items = attention_feed(db, AS_OF)  # CPI 0.25 -> red cost threat leads the feed
    threats = sum(1 for i in items if i.kind == "threat")
    share = business_completeness(business_process_cells(db, AS_OF))
    assert threats and share is not None, "the seed must yield threats and a share"
    page = client.get("/").text
    assert _tile(page, "threats") == str(threats)
    assert _tile(page, "process") == f"{share * 100:.0f}%"
    assert _rail_ids(page) == [i.id for i in items], "rail order is the feed's, verbatim"
    threat = next(i for i in items if i.kind == "threat")
    assert f'name="subject_ref" value="{threat.id.removeprefix("threat:")}"' in page
    assert f'href="/projects/{threat.project_id}/status"' in page, "no_status links the fix"
    thin = next(i for i in items if i.kind == "low_completeness")
    assert f'href="/projects/{thin.project_id}/wizard"' in page, "low_completeness links it"
    assert 'href="/process-map"' in page, "the rail links the whole-business map"


def test_signing_off_from_the_rail_removes_the_threat_from_home(db: Session) -> None:
    """The rail's form posts the EXISTING /sign-off route; the next render of /
    no longer lists the suppressed threat — no bespoke write path."""
    _project(db, _portfolio("Content Brands"), "GMS", percent=20, spends=((JAN, 800.0),))
    threat = next(i for i in attention_feed(db, AS_OF) if i.kind == "threat")
    real_app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(real_app, base_url="https://testserver") as client:
            q = {"as_of": AS_OF.isoformat()}
            assert threat.id in _rail_ids(client.get("/", params=q).text)
            form = {"subject_ref": threat.id.removeprefix("threat:"), "decision": "accepted"}
            form |= {"subject_kind": "threat", "signal": str(threat.score), "as_of": q["as_of"]}
            form |= {"project_id": str(threat.project_id)}
            form |= {csrf.FIELD: client.cookies[csrf.COOKIE]}  # the pair the page handed out
            posted = client.post("/sign-off", follow_redirects=False, data=form)
            assert posted.status_code == 303
            assert threat.id not in _rail_ids(client.get("/", params=q).text)
    finally:
        real_app.dependency_overrides.clear()


def test_signing_off_from_the_rail_redirects_back_to_home(db: Session) -> None:
    """The rail's form carries the hidden ``next=/`` field, so a sign-off
    posted from the dashboard lands back on / (with as_of), not /threats."""
    _project(db, _portfolio("Content Brands"), "GMS", percent=20, spends=((JAN, 800.0),))
    threat = next(i for i in attention_feed(db, AS_OF) if i.kind == "threat")
    real_app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(real_app, base_url="https://testserver") as client:
            q = {"as_of": AS_OF.isoformat()}
            page = client.get("/", params=q).text
            assert 'name="next" value="/"' in page, "the rail form carries the redirect hint"
            form = {"subject_ref": threat.id.removeprefix("threat:"), "decision": "accepted"}
            form |= {"subject_kind": "threat", "signal": str(threat.score), "as_of": q["as_of"]}
            form |= {"project_id": str(threat.project_id), "next": "/"}
            form |= {csrf.FIELD: client.cookies[csrf.COOKIE]}  # the pair the page handed out
            posted = client.post("/sign-off", follow_redirects=False, data=form)
            assert posted.status_code == 303
            assert posted.headers["location"] == f"/?as_of={AS_OF.isoformat()}"
    finally:
        real_app.dependency_overrides.clear()


def test_the_home_marks_a_project_with_no_status_as_never(client: TestClient, db: Session) -> None:
    """A project that has never filed a status snapshot reads a clear 'never' marker
    — not a blank, not a crash — and the page still renders 200 (finding #19)."""
    _project(db, _portfolio("Content Brands"), "GMS", percent=25)

    page = client.get("/")
    assert page.status_code == 200, page.text
    assert _freshness(page.text) == ["never"], "a project with no status snapshot reads 'never'"


def test_the_rail_shows_a_trend_delta(client: TestClient, db: Session) -> None:
    """Mirrors the threat board's week-over-week trend (pages._trend_delta) on the
    attention rail: the same worked example (a spend inside the last week widens
    the seeded cost overspend, CPI-derived score rising 3.75 -> 4.80), the same
    badge idiom (arrow next to the signed amount, never colour/symbol alone) and
    the same 'vs last week' label. The compare is as-of derived, so a pinned
    as_of still renders byte-identically twice."""
    _project(
        db,
        _portfolio("Content Brands"),
        "GMS",
        percent=20,
        spends=((JAN, 800.0), (AS_OF - timedelta(days=2), 200.0)),
    )
    page = client.get("/").text
    assert page == client.get("/").text, "the trend compare is as-of derived, not wall-clock"
    assert "badge delta" in page
    assert "delta-up" in page and "▲" in page
    assert "+1.05" in page
    assert "vs last week" in page


def test_a_brand_new_rail_item_is_marked_new(client: TestClient, db: Session) -> None:
    """A project whose overspend begins entirely inside the last week has no
    counterpart threat a week ago, so its rail card reads 'new'."""
    _project(
        db,
        _portfolio("Content Brands"),
        "Fresh",
        percent=20,
        spends=((AS_OF - timedelta(days=2), 800.0),),
    )
    page = client.get("/").text
    assert "delta-new" in page


def test_trends_annotate_but_never_reorder_the_rail(client: TestClient, db: Session) -> None:
    """Trend deltas mark items up/down/new; the rail's order must stay the feed's
    own order regardless -- annotation, never re-ranking."""
    portfolio = _portfolio("Content Brands")
    _project(
        db, portfolio, "GMS", percent=20, spends=((JAN, 800.0), (AS_OF - timedelta(days=2), 200.0))
    )
    _project(db, portfolio, "Fresh", percent=20, spends=((AS_OF - timedelta(days=2), 800.0),))

    page = client.get("/").text
    assert _rail_ids(page) == [i.id for i in attention_feed(db, AS_OF)]


def test_the_kpi_tiles_carry_the_countup_hook(client: TestClient, db: Session) -> None:
    """Progressive enhancement: the JS-off value IS the complete final figure --
    ``data-countup`` only tells the client script which spans to animate on load;
    the server-rendered number never depends on JS running."""
    _project(db, _portfolio("Content Brands"), "GMS", percent=25, spends=((JAN, 400.0),))
    page = client.get("/").text
    for name in ("budget", "actual", "complete", "on-track", "risks", "threats", "process"):
        assert re.search(rf'id="kpi-{name}" class="value"[^>]*\bdata-countup\b', page), (
            f"kpi-{name} carries the count-up hook"
        )
    assert _tile(page, "budget") == "1,000", "the rendered value is the exact final figure"
