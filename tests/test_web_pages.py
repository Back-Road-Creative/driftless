"""The ITTO web surface, reached through the real app the server serves (§12 UI).

Threat board, process map, wizard and the weekly-status edit — each 200 with the
expected content — plus the write flows: a sign-off removes a threat from the
board, an apply advances the wizard, and a status submission stamps a snapshot,
all through the validated boundary. A file-based SQLite is used so every request
connection sees the same seeded database.
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.models import (
    Baseline,
    BaselineLine,
    Business,
    CostEntry,
    Portfolio,
    Project,
    SignOff,
    StatusSnapshot,
    Task,
    Workstream,
)
from driftless.web import csrf
from driftless.web.pages import evm_curve

JAN, AS_OF = date(2026, 1, 1), date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)
    register_changelog(factory)
    with factory() as session:
        _seed(session)
    with factory() as session:
        yield session


def _seed(session: Session) -> None:
    """A project overspending badly, so the threat board has something to show."""
    project = Project(
        name="GMS",
        portfolio=Portfolio(name="Content", business=Business(name="BRC")),
        delivery_mode="predictive",
    )
    stream = Workstream(name="Post", project=project)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = Baseline(project=project, version=1, status="approved")
    line = BaselineLine(
        baseline=baseline, task=task, planned_cost=1000.0, planned_start=JAN, planned_finish=AS_OF
    )
    session.add(line)
    session.add(CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
    session.commit()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    # https, as production serves: the CSRF cookie is ``Secure``, so an http jar
    # would drop the pair's cookie half and no form could ever post back.
    with TestClient(real_app, base_url="https://testserver") as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def _pair(client: TestClient) -> dict[str, str]:
    """The form half of the CSRF pair the last page render handed this browser."""
    return {csrf.FIELD: client.cookies[csrf.COOKIE]}


def test_the_static_asset_is_served(client: TestClient) -> None:
    page = client.get("/static/driftless.js")
    assert page.status_code == 200
    assert "addEventListener" in page.text


def test_the_core_pages_render(client: TestClient) -> None:
    assert client.get("/").status_code == 200
    assert client.get(f"/threats{Q}").status_code == 200
    assert client.get(f"/projects/1/process-map{Q}").status_code == 200
    assert client.get(f"/projects/1/wizard{Q}").status_code == 200
    assert client.get(f"/projects/1/status{Q}").status_code == 200


def test_threat_board_shows_the_overspend(client: TestClient) -> None:
    body = client.get(f"/threats{Q}").text
    assert "cost" in body and "Top threats" in body


def test_threat_cards_name_link_and_recommend_actions(client: TestClient) -> None:
    body = client.get(f"/threats{Q}").text
    # (a) each card names its project, not just kind/description/score.
    assert "GMS" in body
    # (b) and links that project to its process map.
    assert "/projects/1/process-map" in body
    # (c) and renders at least one recommended action — label and rationale.
    assert "Run a quality audit" in body
    assert "Independently review whether quality processes" in body


def _add_overspender(db: Session, name: str) -> Project:
    """A second project overspending exactly like the seed, so the board has two
    groups and the ranked feed interleaves them (grouping has real work to do)."""
    project = Project(name=name, portfolio_id=1, delivery_mode="predictive")
    stream = Workstream(name="Post", project=project)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = Baseline(project=project, version=1, status="approved")
    line = BaselineLine(
        baseline=baseline, task=task, planned_cost=1000.0, planned_start=JAN, planned_finish=AS_OF
    )
    db.add(line)
    db.add(CostEntry(project=project, category="labour", incurred_on=JAN, amount=800.0))
    db.commit()
    return project


def test_the_threat_board_groups_cards_by_project(client: TestClient, db: Session) -> None:
    _add_overspender(db, "Alpha")
    body = client.get(f"/threats{Q}").text
    # Two per-project group headings, each naming its project and linking its map.
    assert body.count('class="project-group"') == 2
    assert "GMS" in body and "Alpha" in body
    # Each project's heading precedes that project's own cards — the flat rank
    # interleaves the two projects, but grouping collects each project together.
    assert body.index("/projects/1/process-map") < body.index('value="cost:project:1"')
    assert body.index("/projects/2/process-map") < body.index('value="cost:project:2"')


def test_the_threat_board_paginates_when_long(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The single seed makes 5 ranked threats; a page size of 2 forces 3 pages, so the
    # pager and cross-page slicing are exercised without seeding a huge board.
    from driftless.web import pages

    monkeypatch.setattr(pages, "THREATS_PER_PAGE", 2)
    first = client.get(f"/threats{Q}").text
    # Page 1 carries the pager: a "page 1 of 3" indicator and a link to page 2.
    assert "page 1 of 3" in first
    assert "page=2" in first
    first_ids = _threat_ids(first)
    second = client.get(f"/threats{Q}&page=2")
    # Page 2 renders 200 with a DIFFERENT slice of the same ranked feed.
    assert second.status_code == 200
    second_ids = _threat_ids(second.text)
    assert first_ids and second_ids
    assert set(first_ids).isdisjoint(second_ids)


def test_signing_off_a_threat_clears_it_from_the_board(client: TestClient, db: Session) -> None:
    body = client.get(f"/threats{Q}").text
    assert "cost" in body
    # Sign off the cost threat at its current score (echoed by the form).
    threat = next(t for t in _threat_ids(body) if t.startswith("cost:"))
    resp = client.post(
        "/sign-off",
        data={
            "subject_kind": "threat",
            "subject_ref": threat,
            "decision": "accepted",
            "signal": "999",
            "signed_by": "tester",
            "project_id": "1",
            "as_of": AS_OF.isoformat(),
            **_pair(client),
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert db.scalars(select(SignOff)).all(), "the sign-off was recorded"
    assert "cost:" not in "".join(_threat_ids(client.get(f"/threats{Q}").text))


def test_threats_page_sign_off_lands_back_on_threats(client: TestClient, db: Session) -> None:
    """threats.html's form carries no ``next`` field — the redirect keeps
    landing on /threats, as it always has."""
    body = client.get(f"/threats{Q}").text
    threat = next(t for t in _threat_ids(body) if t.startswith("cost:"))
    resp = client.post(
        "/sign-off",
        data={
            "subject_kind": "threat",
            "subject_ref": threat,
            "decision": "accepted",
            "signal": "999",
            "signed_by": "tester",
            "project_id": "1",
            "as_of": AS_OF.isoformat(),
            **_pair(client),
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/threats?as_of={AS_OF.isoformat()}"


@pytest.mark.parametrize("bad_next", ["https://evil.example", "//evil", "/admin"])
def test_a_malicious_next_value_falls_back_to_threats(
    client: TestClient, db: Session, bad_next: str
) -> None:
    """``next`` is a strict allowlist, not a trusted redirect target — anything
    outside {"/", "/threats"} falls back to /threats (no open redirect)."""
    body = client.get(f"/threats{Q}").text
    threat = next(t for t in _threat_ids(body) if t.startswith("cost:"))
    resp = client.post(
        "/sign-off",
        data={
            "subject_kind": "threat",
            "subject_ref": threat,
            "decision": "accepted",
            "signal": "999",
            "signed_by": "tester",
            "project_id": "1",
            "as_of": AS_OF.isoformat(),
            "next": bad_next,
            **_pair(client),
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/threats?as_of={AS_OF.isoformat()}"


def test_the_threat_board_shows_a_trend_delta(client: TestClient, db: Session) -> None:
    # The seeded cost threat is flat across the 7-day window on its own (the overspend
    # is fully incurred back in JAN), so add a fresh spend dated inside the last week:
    # AC at as_of jumps but AC a week earlier does not, so the cost threat's score rises
    # (3.75 -> 4.80). Deterministic — the window is computed from as_of, not the clock.
    db.add(CostEntry(project_id=1, category="labour", incurred_on=date(2026, 3, 28), amount=200.0))
    db.commit()
    body = client.get(f"/threats{Q}").text
    # (a) every rendered card carries a trend-delta indicator — one per card.
    assert body.count("badge delta") == body.count('class="card sev-')
    # (b) the cost threat worsened week-over-week: a rising arrow with its delta class,
    #     the signed amount (+1.05 = 4.80 now vs 3.75 a week ago), and a readable label.
    assert "delta-up" in body
    assert "▲" in body  # the up-triangle glyph marks a worsening trend
    assert "+1.05" in body
    assert "vs last week" in body


def test_a_brand_new_threat_is_marked_new(client: TestClient, db: Session) -> None:
    from driftless.web import pages

    # A project whose overspend only begins inside the last week: at as_of it has a cost
    # threat, but a week earlier AC was 0 (CPI undefined) so no cost threat existed — the
    # current card's id is therefore absent from the prior-week set and reads as "new".
    fresh = Project(name="Fresh", portfolio_id=1, delivery_mode="predictive")
    stream = Workstream(name="Post", project=fresh)
    task = Task(name="Grade", workstream=stream, estimate_unit="hours", percent_complete=20)
    baseline = Baseline(project=fresh, version=1, status="approved")
    line = BaselineLine(
        baseline=baseline, task=task, planned_cost=1000.0, planned_start=JAN, planned_finish=AS_OF
    )
    db.add(line)
    db.add(CostEntry(project=fresh, category="labour", incurred_on=date(2026, 3, 28), amount=800.0))
    db.commit()

    cards = pages.threat_cards(db, AS_OF)
    fresh_cost = next(c for c in cards if c["id"] == f"cost:project:{fresh.id}")
    assert fresh_cost["delta"]["dir"] == "new"
    assert fresh_cost["delta"]["amount"] is None
    # And the board renders a distinct "new" marker for it.
    assert "delta-new" in client.get(f"/threats{Q}").text


def test_trend_delta_is_the_shared_feed_function() -> None:
    """No drift pair: ``pages._trend_delta`` IS ``feed.trend_delta`` — one body,
    not two identical ones kept in sync by comment."""
    from driftless.assess import feed
    from driftless.web import pages

    assert pages._trend_delta is feed.trend_delta


def test_the_process_map_grid_lists_processes(client: TestClient) -> None:
    body = client.get(f"/projects/1/process-map{Q}").text
    assert "4.1" in body and "completeness" in body.lower()
    assert "Develop Project Charter" in body


def test_the_wizard_page_and_apply_advance_onboarding(client: TestClient, db: Session) -> None:
    body = client.get(f"/projects/1/wizard{Q}").text
    assert "Next:" in body or "complete" in body
    resp = client.post(
        f"/projects/1/wizard/apply{Q}",
        data={"kind": "stakeholder_register", "as_of": AS_OF.isoformat(), "name": "Ada Lovelace"}
        | _pair(client),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    from driftless.models import Stakeholder

    # The posted name, not a placeholder: the producer refuses rather than inventing one.
    assert db.scalars(select(Stakeholder)).one().name == "Ada Lovelace"


PROSE = "Vendor lead times hold at six weeks; the drone crew is weather-bound in March."


def test_the_wizard_stores_the_prose_a_browser_typed(client: TestClient, db: Session) -> None:
    """Four producible kinds ARE prose, and the browser's form had nowhere to type it.

    Every narrative row a browser produced therefore held the producer's fallback
    string rather than the operator's words, and no page, report or export could
    show what was never stored. The assertion is quote-for-quote deliberately: a
    textarea that renders and then drops what it collected is the same bug.
    """
    from driftless.models import NarrativeArtifact

    page = client.get(f"/projects/1/wizard{Q}").text
    assert 'name="body"' in page, "the wizard's form offers no way to type the prose"
    resp = client.post(
        f"/projects/1/wizard/apply{Q}",
        data={"kind": "assumption_log", "as_of": AS_OF.isoformat(), "body": PROSE} | _pair(client),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    row = db.scalars(select(NarrativeArtifact)).one()
    assert row.body == PROSE, f"the store holds {row.body!r}, not what the browser typed"


def test_the_wizard_refuses_a_narrative_kind_with_no_prose(client: TestClient, db: Session) -> None:
    """Blank is refused, not stored. Storing it would leave a row that
    ``pmbok.mapping`` reads as absent — an output the wizard claims to have produced
    and every completeness figure still counts as missing — behind a unique
    ``(project, kind)`` that makes the honest retry a duplicate-key 500.
    """
    from driftless.models import NarrativeArtifact

    client.get(f"/projects/1/wizard{Q}")  # mints the pair
    resp = client.post(
        f"/projects/1/wizard/apply{Q}",
        data={"kind": "assumption_log", "as_of": AS_OF.isoformat(), "body": "   "} | _pair(client),
    )
    assert resp.status_code == 422
    assert not db.scalars(select(NarrativeArtifact)).all(), "a blank body still wrote a row"


def test_the_wizard_refuses_a_kind_it_cannot_produce(client: TestClient, db: Session) -> None:
    """The posted ``kind`` is client-controlled bytes like any other:
    ``wizard_cli.produce`` raises ``KeyError`` for one it has no producer for,
    and the route must answer 422 as a rendered page — never a 500, never a
    traceback, and never raw JSON on a surface a person is looking at.

    Which page is deliberately not pinned: the refusal may arrive as the designed
    error shell or as the wizard form re-rendered around the refusal, and both are
    honest answers to a kind nobody can produce. What must hold either way is that
    it is a page and that nothing from the exception leaks into it."""
    from driftless.wizard import cli as wizard_cli

    assert "risk_report" not in wizard_cli.producible_kinds(), "the probe kind grew a producer"
    client.get(f"/projects/1/wizard{Q}")  # mints the pair
    resp = client.post(
        f"/projects/1/wizard/apply{Q}",
        data={"kind": "risk_report", "as_of": AS_OF.isoformat()} | _pair(client),
    )
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("text/html"), "a page surface answers HTML"
    assert "<html" in resp.text, "a page-surface 422 renders a page, not a bare body"
    assert "Traceback" not in resp.text and "KeyError" not in resp.text


def test_the_body_field_is_derived_from_the_narrative_vocabulary() -> None:
    """Which kinds take prose is read off the producer table, never hand-listed —
    so a narrative kind given a producer is asked for by the form on the same
    commit, with no template edit to forget. The stored vocabulary may run ahead
    of the producer table (a kind is storable before its resolver wave makes it
    producible), but never the reverse: every producer's stored target must be a
    kind the CHECK accepts, and the four founding kinds must never stop asking."""
    from driftless.models import NARRATIVE_KINDS
    from driftless.wizard import cli as wizard_cli

    asks = wizard_cli.body_kinds()
    stored_targets = set(wizard_cli._NARRATIVE.values())
    assert stored_targets <= set(NARRATIVE_KINDS), "a producer writes an off-vocabulary kind"
    assert asks <= set(wizard_cli.producible_kinds()), "a body kind the wizard cannot produce"
    founding = {
        "assumption_log",
        "lessons_learned_register",
        "enterprise_environmental_factors",
        "organizational_process_assets",
    }
    assert founding <= asks, "a founding narrative kind stopped asking for its prose"


def test_the_weekly_status_form_stamps_the_percent(client: TestClient, db: Session) -> None:
    assert client.get(f"/projects/1/status{Q}").status_code == 200  # mints the CSRF pair
    resp = client.post(
        f"/projects/1/status{Q}",
        data={"rag_status": "amber", "note": "on watch", "as_of": AS_OF.isoformat()}
        | _pair(client),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    snap = db.scalars(select(StatusSnapshot)).one()
    assert snap.rag_status == "amber"
    assert snap.percent_complete == 20, "the percent is stamped from calc, not typed"


def test_the_rag_palette_is_single_sourced(client: TestClient) -> None:
    body = client.get("/").text
    # The canonical RAG token is DEFINED once, in base.html's :root block...
    assert "--rag-red: #b3261e" in body
    # ...and REFERENCED through var(), never re-hardcoded per page.
    assert "var(--rag-red)" in body
    # The home page no longer carries its own raw RAG hex: its .red class now
    # points at the token, so #b3261e survives only as the single :root definition.
    assert body.count("#b3261e") == 1
    assert ".red { color: var(--rag-red)" in body


def test_the_base_layout_ships_a_dark_mode_theme(client: TestClient) -> None:
    body = client.get("/").text
    # The app themes itself via a single prefers-color-scheme media query...
    assert "@media (prefers-color-scheme: dark)" in body
    # ...which re-points the single-sourced RAG tokens to dark-legible variants...
    assert "--rag-red: #f2665a" in body
    # ...and overrides the base surface with a dark body background + light text.
    assert "background: #151515" in body


def test_the_threat_card_shows_a_readable_severity_word(client: TestClient) -> None:
    import re

    body = client.get(f"/threats{Q}").text
    match = re.search(r'class="card sev-(\w+)"', body)
    assert match, "a severity-bearing threat card renders"
    sev = match.group(1)
    # Severity reads as a word, not colour alone: the same class that tints the
    # card's border also fills the badge, and the badge shows the severity text.
    assert f'class="badge sev-badge">{sev}<' in body


def test_the_status_page_renders_a_trend_svg_from_snapshots(
    client: TestClient, db: Session
) -> None:
    # Seed the append-only series the chart is drawn from: one snapshot per week.
    for taken_on, percent, rag in [
        (date(2026, 1, 15), 40, "red"),
        (date(2026, 2, 15), 60, "amber"),
        (date(2026, 3, 15), 85, "green"),
    ]:
        db.add(
            StatusSnapshot(
                project_id=1, taken_on=taken_on, percent_complete=percent, rag_status=rag
            )
        )
    db.commit()
    body = client.get(f"/projects/1/status{Q}").text
    # An inline SVG trend line, with one plotted reading per seeded snapshot.
    assert "<svg" in body
    assert "<polyline" in body
    assert body.count("<circle") == 3
    # Built FROM the stored series: a seeded percent (not the stamped 20%) shows in it.
    assert "85%" in body


def test_the_status_page_handles_no_snapshot_history(client: TestClient) -> None:
    resp = client.get(f"/projects/1/status{Q}")
    assert resp.status_code == 200
    # Friendly empty state instead of a broken chart.
    assert "No status history yet" in resp.text
    assert 'points=""' not in resp.text


def test_the_status_page_renders_an_evm_scurve(client: TestClient) -> None:
    # The seeded project has a baseline (planned JAN->AS_OF, cost 1000) and an
    # 800 cost entry, so PV(t) and AC(t) both exist and it is overspending.
    body = client.get(f"/projects/1/status{Q}").text
    # An inline SVG carrying exactly two curves -- PV and AC. There is deliberately
    # NO third, swept EV line: the model keeps only each task's current percent, so
    # a swept EV would be a flat, misleading fiction -- hence the honesty caption.
    # The seeded project has no status snapshots, so the trend chart is empty and
    # the two EVM polylines are the only polylines on the page.
    assert "<svg" in body
    assert body.count("<polyline") == 2
    assert "per-task progress history is not retained" in body
    # The CURRENT earned-value position shows as text: EV=200 (1000 x 20%),
    # CPI=EV/AC=200/800=0.25.
    assert "EV" in body and "CPI" in body
    assert "0.25" in body


def test_the_evm_polylines_plot_the_computed_series_point_for_point(
    client: TestClient, db: Session
) -> None:
    """Two polylines were counted but never read as values: a chart plotting
    both series identical, PV flat, or the axis inverted stayed green. Each
    plotted pair must be the template's own mapping of ``evm_curve``'s series —
    x by sample index, y scaled to the peak of PV, AC and the budget line."""
    import re

    from driftless.assess import adapters

    body = client.get(f"/projects/1/status{Q}").text
    drawn = {
        name: [tuple(float(value) for value in xy.split(",")) for xy in points.split()]
        for name, points in re.findall(r'<polyline data-series="(\w+)"[^>]*points="([^"]*)"', body)
    }
    assert sorted(drawn) == ["ac", "pv"]
    project = db.get(Project, 1)
    assert project is not None
    evm = evm_curve(project, adapters.project_costs(db, project), AS_OF)
    points = evm["points"]
    span = max(len(points) - 1, 1)
    peak = max([p["pv"] for p in points] + [p["ac"] for p in points] + [evm["bac"]]) or 1
    for series in ("pv", "ac"):
        expected = [
            (40 + index / span * 270, 12 + (1 - p[series] / peak) * 118)
            for index, p in enumerate(points)
        ]
        flat = [value for pair in drawn[series] for value in pair]
        want = [value for pair in expected for value in pair]
        assert flat == pytest.approx(want, abs=0.06), f"the {series} polyline drifts off its series"
    assert drawn["pv"] != drawn["ac"], (
        "the two curves plot one series — the equality proves nothing"
    )


def test_the_status_evm_handles_no_baseline(client: TestClient, db: Session) -> None:
    # A project with no baseline at all -- PV/AC are undefined, so the S-curve must
    # show a friendly empty state, never a broken points="" polyline.
    bare = Project(name="Bare", portfolio_id=1, delivery_mode="predictive")
    db.add(bare)
    db.commit()
    resp = client.get(f"/projects/{bare.id}/status{Q}")
    assert resp.status_code == 200
    assert "No cost baseline yet" in resp.text
    assert 'points=""' not in resp.text


def test_evm_curve_never_samples_past_as_of(db: Session) -> None:
    """A project whose planned start is still in the future must not push the
    EVM curve's sample dates past ``as_of``: the old span clamp collapsed every
    sample onto that future start date itself -- which is AFTER as_of -- so a
    curve "as of AS_OF" was counting a cost entry dated after AS_OF."""
    future_start = date(2026, 5, 1)
    project = Project(
        name="Future",
        portfolio=Portfolio(name="Later", business=Business(name="BRC Later")),
        delivery_mode="predictive",
    )
    stream = Workstream(name="Future", project=project)
    task = Task(name="Future", workstream=stream, estimate_unit="hours", percent_complete=0)
    baseline = Baseline(project=project, version=1, status="approved")
    line = BaselineLine(
        baseline=baseline,
        task=task,
        planned_cost=3000.0,
        planned_start=future_start,
        planned_finish=date(2026, 5, 31),
    )
    db.add(line)
    cost = CostEntry(
        project=project, category="labour", incurred_on=date(2026, 4, 15), amount=999.0
    )
    db.add(cost)
    db.commit()

    evm = evm_curve(project, [cost], AS_OF)

    assert evm["points"], "a baselined project still produces points"
    assert all(p == {"pv": 0.0, "ac": 0.0} for p in evm["points"]), (
        "every sample must clamp to as_of: PV is 0 (the plan has not started as "
        "of as_of) and the cost entry dated between as_of and the future start "
        "must never be counted"
    )


def test_the_pmbok_reference_grid_lists_all_processes(client: TestClient) -> None:
    body = client.get("/pmbok").text
    assert client.get("/pmbok").status_code == 200
    # A known process shows by id and name, straight from the frozen catalog.
    assert "4.1" in body and "Develop Project Charter" in body
    # Group/area headers read as words, not raw enum values.
    assert "Monitoring Controlling" in body
    assert "monitoring_controlling" not in body


def test_the_pmbok_detail_shows_itto(client: TestClient) -> None:
    resp = client.get("/pmbok/4.1")
    assert resp.status_code == 200
    body = resp.text
    # The ITTO the catalog carries for 4.1 — a real input and a real output.
    assert "business_case" in body  # an input
    assert "project_charter" in body  # an output
    assert "expert_judgment" in body  # a tool/technique


def test_an_unknown_pmbok_id_is_404(client: TestClient) -> None:
    assert client.get("/pmbok/99.9").status_code == 404


def test_the_process_map_cell_links_to_the_reference(client: TestClient) -> None:
    body = client.get(f"/projects/1/process-map{Q}").text
    # Each project cell drills into the process's ITTO reference (finding #12) —
    # carrying the project and the pinned as-of, so the drill reads THIS project's
    # process rather than dropping both at the first click (tests/test_web_pmbok_drill).
    assert f'href="/pmbok/4.1?project=1&amp;as_of={AS_OF.isoformat()}"' in body


def test_pmbok_is_in_the_nav(client: TestClient) -> None:
    assert 'href="/pmbok"' in client.get("/").text


def test_signed_off_has_its_own_process_map_class(client: TestClient) -> None:
    from driftless.web import pages

    # signed_off no longer shares produced's "ok" class — it maps to its own
    # "signed" wash — and a not-yet-started process reads neutral, not alarming
    # red (findings #12 / #18).
    assert pages.STATE_RANK["produced"] == "ok"
    assert pages.STATE_RANK["signed_off"] == "signed"
    assert pages.STATE_RANK["not_started"] == "muted"
    # The base layout defines that .st-signed wash, so signed_off is visually
    # distinct from produced on every rendered page.
    assert ".st-signed" in client.get("/").text


def test_the_process_map_has_a_state_legend(client: TestClient) -> None:
    import re

    from driftless.pmbok.state import ProcessState
    from driftless.web import pages

    # Derived, not hardcoded: the expected set comes from ProcessState — the same
    # enum the state engine computes against — so a state added there and forgotten
    # in pages._LEGEND fails HERE instead of shipping a legend that silently omits
    # a state the grid can render (finding KA-F4: completeness held by inspection,
    # not by construction).
    assert {st for st, _rank, _mark in pages._LEGEND} == {m.value for m in ProcessState}

    body = client.get(f"/projects/1/process-map{Q}").text
    match = re.search(r'class="legend".*?</dl>', body, re.S)
    assert match, 'the process map carries a <dl class="legend"> region'
    legend = match.group(0)
    # Every state is named, humanized, inside the legend, each with a swatch that
    # reuses the grid's live st- class — walking pages._LEGEND itself rather than a
    # hand-typed list, so a rendering gap can't hide behind a stale expectation.
    for state, rank, _mark in pages._LEGEND:
        label = state.replace("_", " ").title()
        assert label in legend, f"legend names {label}"
        assert f"st-{rank}" in legend, f"legend swatch uses st-{rank}"


def test_the_process_map_shows_per_area_completion_rings(client: TestClient, db: Session) -> None:
    import re

    from driftless.pmbok import state
    from driftless.pmbok.model import KnowledgeArea
    from driftless.web import pages

    project = db.get(Project, 1)
    assert project is not None
    # Independently compute the expected per-area completion (raw fractions), then
    # confirm the page renders each area's ring from THAT, not a hard-coded value.
    rings = pages.area_completeness(state.project_process_states(project, db, AS_OF))

    body = client.get(f"/projects/1/process-map{Q}").text
    humanize = pages.TEMPLATES.env.filters["humanize"]
    # One inline-SVG completion ring per knowledge area.
    assert body.count('<svg class="ring"') == len(list(KnowledgeArea))
    # Each ring's label equals pct of the computed fraction for its area, so the
    # rings track the same states the grid renders (drift-free) and cannot be a
    # single constant: the seeded project spans 0%, 17%, 33% and 50% across areas.
    for area, frac in rings.items():
        match = re.search(rf'aria-label="{humanize(area)} completion ([^"]+)"', body)
        assert match, f"a ring is labelled for {area}"
        assert match.group(1) == pages.pct(frac)
    # Concrete, non-uniform spot-checks that pin the values are computed per area.
    assert pages.pct(rings["scope"]) == "50%"
    assert pages.pct(rings["schedule"]) == "33%"
    # Every area holds an assessable process, so no ring reads n/a for a real
    # project. Communications fell to a third (50% before): project_communications
    # gained a resolver, so Manage Communications entered the denominator, and the
    # seed's snapshots carry no note — a number filed is not a communication made, so
    # it counts and is not done. It is the only ring the plan-and-communications wave
    # moved: 4.2 joined an integration area already reading 0%.
    assert rings["communications"] == pytest.approx(1 / 3)
    assert "completion n/a" not in body and "completion 25%" in body


def test_a_zero_percent_ring_draws_no_progress_arc(client: TestClient, db: Session) -> None:
    """A 0% completion ring shows only its grey track — never a green arc.

    The green arc is a dashed circle with ``stroke-linecap="round"``: at 0% the
    dash is zero-length (``stroke-dasharray="0 100"``), and a round cap renders a
    zero-length dash as a filled dot at 12 o'clock — reading as a sliver of
    progress where there is none. The seeded project has 0% areas (integration, risk)
    alongside 25% ones (cost, stakeholder), so the page must omit the arc for the former
    while keeping it for the latter.
    """
    from driftless.pmbok import state
    from driftless.web import pages

    project = db.get(Project, 1)
    assert project is not None
    rings = pages.area_completeness(state.project_process_states(project, db, AS_OF))
    assert any(frac == 0.0 for frac in rings.values()), "fixture must exercise a 0% area"

    body = client.get(f"/projects/1/process-map{Q}").text
    # No zero-length green arc anywhere — a 0% ring is track-only, no dot.
    assert 'stroke-dasharray="0 100"' not in body
    # A partial ring still draws its arc, so the guard dropped only the empty dot.
    assert 'stroke-dasharray="25 75"' in body  # the cost and stakeholder areas are 25%


def test_area_completeness_mirrors_the_completeness_rule_per_area(db: Session) -> None:
    from driftless.pmbok import state
    from driftless.pmbok.model import KnowledgeArea
    from driftless.web import pages

    project = db.get(Project, 1)
    assert project is not None
    rings = pages.area_completeness(state.project_process_states(project, db, AS_OF))

    # Keyed by every knowledge area; each value a fraction in [0, 1] or None.
    assert set(rings) == {a.value for a in KnowledgeArea}
    for value in rings.values():
        assert value is None or 0.0 <= value <= 1.0

    # Same rule as state.completeness, grouped by process.area: recompute it here
    # from the identical states and assert an exact match (so it can never drift).
    counted: dict[str, int] = {a.value: 0 for a in KnowledgeArea}
    done: dict[str, int] = {a.value: 0 for a in KnowledgeArea}
    for process, ps in state.project_process_states(project, db, AS_OF):
        if ps is state.ProcessState.WAIVED or not state.is_assessable(process):
            continue
        counted[process.area.value] += 1
        if ps in (state.ProcessState.PRODUCED, state.ProcessState.SIGNED_OFF):
            done[process.area.value] += 1
    expected = {a: (done[a] / counted[a] if counted[a] else None) for a in counted}
    assert rings == expected
    # And the per-area split reconstructs the single global completeness exactly.
    assert state.completeness(project, db, AS_OF) == sum(done.values()) / sum(counted.values())


def _threat_ids(html: str) -> list[str]:
    import re

    return re.findall(r'name="subject_ref" value="([^"]+)"', html)
