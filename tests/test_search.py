"""One search box over the hierarchy: the JSON endpoint and the page.

Pins the hit shape a caller depends on, the kinds searched, the order and the per-kind cap —
plus the two properties a search box quietly loses: its cost (one statement per kind, flat in
the row count) and its links (each hit's path is matched against the running app's OWN route
table, so a renamed page fails here, not in a browser). The empty query and no-match are the
product states they are; a viewer's read is confirmed, not assumed."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api import secure
from driftless.api.app import app as real_app
from driftless.api.search import PER_KIND, SEARCHED, Hit, search
from driftless.auth import sessions
import test_web_pages
from test_web_routes_not_shadowed import _leaves

# The seeded https store, reused as is (assigned, not imported: a parameter of that name
# must not read as a redefined import).
client, db = test_web_pages.client, test_web_pages.db
TERM = "falcon"
NOW = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
SECRET = "test-signing-secret"  # pragma: allowlist secret  (throwaway in-test signing key)


def _findable(db: Session) -> m.Workstream:
    """One row of every searched kind carrying ``TERM`` — the seed names none of them."""
    project = db.scalars(select(m.Project)).one()
    project.portfolio.name, project.name = "Falcon Portfolio", "Falcon Project"
    project.program = m.Program(name="Falcon Program", portfolio=project.portfolio)
    stream = m.Workstream(name="falcon edit", project=project)
    db.add(m.Task(name="Grade the FALCON reel", workstream=stream))
    db.add(m.Risk(project=project, description="falcon lens", probability=0.5, impact=1.0))
    db.commit()
    return stream


def _statements(db: Session, call: Callable[[], object]) -> int:
    """How many SQL statements ``call`` runs against ``db``'s engine."""
    seen: list[object] = []
    bind, watch = db.get_bind(), lambda *_: seen.append(None)
    event.listen(bind, "before_cursor_execute", watch)
    try:
        call()
    finally:
        event.remove(bind, "before_cursor_execute", watch)
    return len(seen)


def _routed(path: str) -> bool:
    """Whether the app the server runs really serves a GET at ``path``."""
    for route in real_app.routes:
        for leaf in _leaves(route):
            pattern = getattr(leaf, "path_regex", None)
            if pattern is not None and pattern.fullmatch(path):
                return "GET" in (getattr(leaf, "methods", None) or ())
    return False


def test_one_term_finds_every_kind_that_names_it_and_the_json_shape_is_pinned(
    client: TestClient, db: Session
) -> None:
    _findable(db)
    # risk id 2, not 1: test_web_pages._seed now seeds one Risk of its own (for the
    # risk-response planner's own coverage), so the "falcon lens" row this test adds
    # is the SECOND risk row, never the first.
    assert [(hit.kind, hit.id, hit.label) for hit in search(db, "FALCON")] == [
        ("portfolio", 1, "Falcon Portfolio"),
        ("program", 1, "Falcon Program"),
        ("project", 1, "Falcon Project"),
        ("workstream", 2, "falcon edit"),
        ("task", 2, "Grade the FALCON reel"),
        ("risk", 2, "falcon lens"),
    ]
    assert search(db, "FALCON") == search(db, TERM)  # the term's case never moves a hit
    assert [hit.kind for hit in search(db, "reel")] == ["task"]  # mid-string, not a prefix
    body = client.get(f"/search/results?q={TERM}").json()  # and the same hits over the wire
    top = {"kind": "portfolio", "id": 1, "label": "Falcon Portfolio"}
    assert body[0] == top | {"path": "/portfolios/1/rollup"}  # the shape a caller pins
    assert all(set(hit) == {"kind", "id", "label", "path"} for hit in body)


def test_the_method_registries_are_searched_too(client: TestClient, db: Session) -> None:
    """One representative query per registry kind: a process, a technique, an artifact,
    a glossary term and a method practice, none of them backed by a store row."""
    by_kind = {hit.kind: hit for hit in search(db, "integrated change control")}
    assert by_kind["process"] == Hit(
        kind="process", id="4.6", label="Perform Integrated Change Control", path="/pmbok/4.6"
    )
    by_kind = {hit.kind: hit for hit in search(db, "turns its options into one chosen course")}
    assert by_kind["technique"] == Hit(
        kind="technique",
        id="decision_making",
        label="Decision Making",
        path="/techniques/decision-making",
    )
    by_kind = {hit.kind: hit for hit in search(db, "cost management plan")}
    assert by_kind["artifact"] == Hit(
        kind="artifact",
        id="cost_management_plan",
        label="Cost Management Plan",
        path="/artifacts/cost-management-plan",
    )
    by_kind = {hit.kind: hit for hit in search(db, "critical path")}
    assert by_kind["glossary"] == Hit(
        kind="glossary", id="critical-path", label="Critical path", path="/glossary#critical-path"
    )
    by_kind = {hit.kind: hit for hit in search(db, "limit work in progress")}
    assert by_kind["practice"] == Hit(
        kind="practice",
        id="kanban:limit_work_in_progress",
        label="Limit Work in Progress",
        path="/methods/kanban",
    )
    for path in (
        "/pmbok/4.6",
        "/techniques/decision-making",
        "/artifacts/cost-management-plan",
        "/glossary",
        "/methods/kanban",
    ):
        assert client.get(path).status_code == 200, path


def test_a_registry_hit_needs_no_project(db: Session) -> None:
    """A registry query on an empty project still finds its matches — the Method
    registries are frozen, in-memory data, never scoped to a project's rows."""
    assert [hit.kind for hit in search(db, "cost management plan")] == ["artifact"]


def test_no_match_and_no_term_are_product_states_the_page_names(client: TestClient) -> None:
    for query in ("?q=kestrel", ""):
        assert client.get(f"/search/results{query}").json() == []
        page = client.get(f"/search{query}")
        assert page.status_code == 200 and "data-empty" in page.text
    assert "kestrel" in client.get("/search?q=kestrel").text  # it names what it looked for


def test_the_cap_holds_and_the_cost_stays_one_statement_per_kind(db: Session) -> None:
    """Both bounds at once, one growth: however many rows match, a kind returns at most
    PER_KIND of them and search runs one query per kind, never one per row."""
    stream = _findable(db)
    small = _statements(db, lambda: search(db, TERM))
    db.add_all(m.Task(name=f"falcon {n:03d}", workstream=stream) for n in range(60))
    db.commit()
    assert [hit.kind for hit in search(db, TERM)].count("task") == PER_KIND
    assert small == _statements(db, lambda: search(db, TERM)) == len(SEARCHED), (
        "search must run one query per searched kind — never one per row"
    )


def test_a_viewer_may_search_because_a_search_is_a_read(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(sessions.SECRET_ENV, SECRET)
    db.add(m.User(username="jp", password_hash="x", role="viewer"))
    db.commit()
    value = sessions.issue(1, "jp", "viewer", NOW.replace(year=2099), SECRET, 0)
    gate = secure.TokenGate(real_app, "t", session_scope=lambda: nullcontext(db), clock=lambda: NOW)
    gated = TestClient(gate, base_url="https://testserver")
    for path in (f"/search?q={TERM}", f"/search/results?q={TERM}"):
        assert gated.get(path, headers={"Cookie": f"{sessions.COOKIE}={value}"}).status_code == 200


def test_the_page_groups_its_hits_and_every_path_resolves_to_a_real_route(
    client: TestClient, db: Session
) -> None:
    """A hit's path is a link built with no second round trip: rename a page and this fails."""
    assert not _routed("/no/such/place"), "guard the guard: an invented path must not resolve"
    assert _routed("/search") and _routed("/search/results"), "both surfaces are registered"
    _findable(db)
    assert (hits := search(db, TERM))
    for hit in hits:
        assert _routed(hit.path), f"a {hit.kind} hit links to {hit.path}, which no route serves"
        assert client.get(hit.path).status_code == 200, hit.path
    body = client.get(f"/search?q={TERM}").text
    assert body.count("<caption") == len({hit.kind for hit in hits})  # grouped by kind
    assert '<th scope="col">' in body and '<a href="/projects/1/hub">' in body
