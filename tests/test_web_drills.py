"""Portfolio and program drill pages: one node's own rollup KPIs plus its
children's rows, read through the identical ``gather.overview()`` tree home
renders — so a drill figure can never disagree with the dashboard."""

import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from tests.test_web_home import _portfolio, _project

AS_OF = date(2026, 3, 31)
JAN = date(2026, 1, 31)
Q = f"?as_of={AS_OF.isoformat()}"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    real_app.dependency_overrides[get_session] = lambda: db
    with TestClient(real_app) as test_client:
        yield test_client
    real_app.dependency_overrides.clear()


def _tile(html: str, name: str) -> str:
    found = re.search(rf'id="kpi-{name}" class="value"[^>]*>([^<]*)<', html)
    assert found is not None, f"no {name} KPI tile in the page"
    return found.group(1)


def _links(html: str, prefix: str) -> dict[str, str]:
    """Drill name -> href, for every ``<a href="{prefix}/N/rollup">`` in the page."""
    return {
        name: href for href, name in re.findall(rf'href="({prefix}/\d+/rollup)">([^<]+)</a>', html)
    }


def _seed(db: Session) -> None:
    """One real portfolio (a program with one project, plus a program-less
    project) behind an empty decoy committed FIRST, so "Content Brands" and
    "Video" take DB id 2 while sorting to walk position 1 — ids ≠ positions."""
    db.add(m.Program(name="Zed decoy", portfolio=_portfolio("Zed")))
    db.commit()
    portfolio = _portfolio("Content Brands")
    video = m.Program(name="Video", portfolio=portfolio)
    _project(db, portfolio, "GMS", percent=25, planned=1000.0, program=video)
    _project(db, portfolio, "Solo", percent=75, planned=3000.0, spends=((JAN, 400.0),))


def test_home_links_carry_real_db_ids_and_the_drill_resolves_them(
    client: TestClient, db: Session
) -> None:
    """First by name but second by id — a position counter would emit /portfolios/1."""
    _seed(db)
    home = client.get(f"/{Q}").text
    assert _links(home, "/portfolios")["Content Brands"] == "/portfolios/2/rollup"
    assert _links(home, "/programs")["Video"] == "/programs/2/rollup"
    drill = client.get(f"/portfolios/2/rollup{Q}")
    assert drill.status_code == 200 and "<h1>Content Brands</h1>" in drill.text


def test_the_portfolio_drill_agrees_with_the_dashboard_and_is_byte_stable(
    client: TestClient, db: Session
) -> None:
    """Home links both a portfolio and a program to their drills; the tiles
    agree (same store, same as-of); a pinned as-of fetch is byte-identical."""
    _seed(db)
    home = client.get(f"/{Q}").text
    assert "Video" in _links(home, "/programs"), "home links the program name too"
    href = _links(home, "/portfolios")["Content Brands"]
    first = client.get(f"{href}{Q}")
    assert first.status_code == 200, first.text
    assert "<h1>Content Brands</h1>" in first.text
    for tile in ("budget", "actual", "complete", "on-track", "risks"):
        assert _tile(first.text, tile) == _tile(home, tile), f"drill disagrees on {tile}"
    assert client.get(f"{href}{Q}").text == first.text, "a pinned as-of fetch is byte-identical"


def test_the_portfolio_drill_nests_its_program_and_lists_program_less_projects(
    client: TestClient, db: Session
) -> None:
    _seed(db)
    href = _links(client.get(f"/{Q}").text, "/portfolios")["Content Brands"]
    drill = client.get(f"{href}{Q}").text
    assert re.search(r'<tr class="program" data-rag="\w+">\s*<td>Video</td>', drill)
    assert re.search(r'<tr class="project nested" data-rag="\w+">\s*<td>GMS</td>', drill)
    assert re.search(r'<tr class="project" data-rag="\w+">\s*<td>Solo</td>', drill)


def test_the_program_drill_shows_its_own_rollup_and_its_projects(
    client: TestClient, db: Session
) -> None:
    _seed(db)
    href = _links(client.get(f"/{Q}").text, "/programs")["Video"]
    drill = client.get(f"{href}{Q}")
    assert drill.status_code == 200, drill.text
    assert "<h1>Video</h1>" in drill.text
    assert (_tile(drill.text, "budget"), _tile(drill.text, "complete")) == ("1,000", "25%")
    assert re.search(r'<tr class="project" data-rag="\w+">\s*<td>GMS</td>', drill.text)
    assert "Solo" not in drill.text, "a program drill lists only its own projects"


def test_an_unknown_portfolio_or_program_id_404s(client: TestClient, db: Session) -> None:
    _seed(db)
    assert client.get(f"/portfolios/999/rollup{Q}").status_code == 404
    assert client.get(f"/programs/999/rollup{Q}").status_code == 404
