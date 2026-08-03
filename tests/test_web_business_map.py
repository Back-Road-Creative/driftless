"""The business-wide process map page (§ B2/B4a): the per-project grid rolled up
across every project, topped by a per-knowledge-area completion ring row, plus a
``?process={id}`` per-cell listing of that process's applicable projects. Every
catalog process gets a cell regardless of data."""

import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.models import Business, NarrativeArtifact, Portfolio, Project, Risk, SignOff
from driftless.pmbok import catalog
from driftless.pmbok import state as st
from driftless.pmbok.rollup import business_area_shares, business_process_cells

AS_OF = date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"
IDENTIFY_RISKS = catalog.get("11.2")  # assessable: risk_register, risk_report, assumption_log
# One grid cell: its self-link names the process, the badge carries the wash and the
# printed share (the title repeats it). Attribute order here is the template's own.
_CELL = re.compile(r'&process=([\d.]+)"><span class="badge st-(\w+)" title="([^"]*)">')


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


def _project(db: Session, name: str) -> Project:
    project = Project(
        name=name, portfolio=Portfolio(name=f"{name} port", business=Business(name=f"{name} biz"))
    )
    db.add(project)
    db.commit()
    return project


def test_the_map_200s_49_cells_nav_link_and_byte_identical(client: TestClient) -> None:
    first = client.get(f"/process-map{Q}")
    assert first.status_code == 200
    body = first.text
    assert body.count("<br>") == 49  # one cell badge per catalog process
    assert "4.1" in body and "Develop Project Charter" in body
    assert 'href="/process-map"' in body
    assert 'href="/process-map"' in client.get(f"/{Q}").text  # linked from the dashboard too
    assert client.get(f"/process-map{Q}").text == body  # pinned as-of fetch twice -> identical


def test_rings_render_the_business_area_shares_as_their_labels(
    client: TestClient, db: Session
) -> None:
    """A bare store rings every area ``n/a``; once a project exists, Communications
    measures a real share — 10.1's communications plan is a tracked kind since the
    management-plan resolver wave, and nobody has written one, so the ring reads an
    honest 0% rather than n/a — and every ring label must equal
    ``business_area_shares``' own formatted output, area for area."""
    bare_body = client.get(f"/process-map{Q}").text
    assert 'aria-label="Communications completion n/a"' in bare_body

    alpha = _project(db, "Alpha")
    db.add(Risk(project=alpha, description="r", probability=0.3, impact=1000.0))
    db.add(NarrativeArtifact(project=alpha, kind="assumption_log", body="drone weather"))
    db.commit()

    body = client.get(f"/process-map{Q}").text
    assert 'aria-label="Communications completion 0%"' in body  # tracked now, unwritten
    shares = business_area_shares(business_process_cells(db, AS_OF))
    for share in shares:
        label = f"{share.share * 100:.0f}%" if share.share is not None else "n/a"
        humanized = share.area.value.replace("_", " ").title()
        assert f'aria-label="{humanized} completion {label}"' in body


def test_process_query_listing_shows_exactly_the_applicable_projects(
    client: TestClient, db: Session
) -> None:
    """``?process=11.2`` lists only Alpha (produced, applicable); Beta's 11.2 is
    waived so it is excluded from the listing exactly as it is from ``applicable``
    — the same exclusion the grid's own share pools. Each row links to that
    project's own process map. A cell in the grid links to itself with the SAME
    query param (plus the pinned as-of, so the pin survives the click)."""
    alpha, beta = _project(db, "Alpha"), _project(db, "Beta")
    db.add(Risk(project=alpha, description="r", probability=0.3, impact=1000.0))
    db.add(NarrativeArtifact(project=alpha, kind="assumption_log", body="drone weather"))
    db.add(
        SignOff(
            project=beta,
            subject_kind="process",
            subject_ref=st.process_subject_ref(IDENTIFY_RISKS, beta),
            decision="waived",
        )
    )
    db.commit()

    body = client.get(f"/process-map{Q}").text
    assert f'href="/process-map?as_of={AS_OF.isoformat()}&process=11.2"' in body  # cell self-link

    listing = client.get(f"/process-map{Q}&process=11.2").text
    assert f'href="/projects/{alpha.id}/process-map?as_of={AS_OF.isoformat()}"' in listing
    assert "Alpha" in listing and "Produced" in listing
    assert f'href="/projects/{beta.id}/process-map?as_of={AS_OF.isoformat()}"' not in listing
    assert listing.count('href="/projects/') == 1  # only the one applicable project

    # The listing must agree with the exclusion predicate itself, row for row —
    # not merely reproduce it by coincidence for this one fixture.
    cell = next(c for c in business_process_cells(db, AS_OF) if c.process_id == "11.2")
    for pc in cell.projects:
        applicable = not st.excluded_from_completeness(IDENTIFY_RISKS, pc.state)
        assert (f'href="/projects/{pc.project_id}/' in listing) is applicable


def test_unknown_or_absent_process_id_renders_with_no_listing(
    client: TestClient, db: Session
) -> None:
    """An unknown process id 404-shaped input must never 500 — the page renders
    the same grid, just with no listing section; same for no ``process=`` at
    all (the default, already covered by the byte-identical test)."""
    plain = client.get(f"/process-map{Q}")
    assert plain.status_code == 200
    assert "process-listing" not in plain.text

    unknown = client.get(f"/process-map{Q}&process=nope-not-a-process")
    assert unknown.status_code == 200
    assert "process-listing" not in unknown.text


def test_every_cell_prints_the_rollups_own_share_washed_by_its_band(
    client: TestClient, db: Session
) -> None:
    """The 49 cells were counted but never READ: no assert tied a cell's printed
    share or its wash to ``business_process_cells``, so a grid rendering every
    share alike — or washing an under-half cell ``ok`` — stayed green. The seed
    reaches all four bands (1/3 warn, 1/2 ok, 1/1 signed, untouched muted), and
    the band arithmetic is written out here on purpose: an expectation imported
    from the module under test would mutate along with it."""
    alpha, beta, cass = (_project(db, name) for name in ("Alpha", "Beta", "Cass"))
    db.add(Risk(project=alpha, description="r", probability=0.3, impact=1000.0))
    db.add(NarrativeArtifact(project=alpha, kind="assumption_log", body="drone weather"))
    # Alpha's artifacts light several processes at 1/3; waivers thin the applicable
    # pools so the SAME seed also reaches the half+ and all-done bands. 11.3 is
    # thinned to Alpha alone — the one project that produced it — so it lands at
    # 1/1, while its 11.x siblings stay at 1/3. Waiving EVERY project for a process
    # empties the pool instead and reads n/a, which is why 5.3 keeps two holders.
    for project, process_id in (
        (beta, "4.1"),
        (beta, "5.3"),
        (cass, "5.3"),
        (beta, "11.3"),
        (cass, "11.3"),
    ):
        db.add(
            SignOff(
                project=project,
                subject_kind="process",
                subject_ref=st.process_subject_ref(catalog.get(process_id), project),
                decision="waived",
            )
        )
    db.commit()

    drawn = {
        pid: (rank, share)
        for pid, rank, share in _CELL.findall(client.get(f"/process-map{Q}").text)
    }
    cells = business_process_cells(db, AS_OF)
    assert len(drawn) == 49 and sorted(drawn) == sorted(c.process_id for c in cells)
    for cell in cells:
        if cell.share is None or cell.share == 0.0:
            band = "muted"
        elif cell.share < 0.5:
            band = "warn"
        elif cell.share < 1.0:
            band = "ok"
        else:
            band = "signed"
        label = f"{cell.share * 100:.0f}%" if cell.share is not None else "n/a"
        assert drawn[cell.process_id] == (band, label), (cell.process_id, cell.share)
    assert drawn["11.2"] == ("warn", "33%"), "an under-half share must wash warn, not ok"
    assert {rank for rank, _ in drawn.values()} == {"muted", "warn", "ok", "signed"}, (
        "the fixture no longer exercises every share band — the walk above proves less"
    )


def test_process_query_pinned_as_of_double_fetch_byte_identical(
    client: TestClient, db: Session
) -> None:
    alpha = _project(db, "Alpha")
    db.add(Risk(project=alpha, description="r", probability=0.3, impact=1000.0))
    db.add(NarrativeArtifact(project=alpha, kind="assumption_log", body="drone weather"))
    db.commit()

    url = f"/process-map{Q}&process=11.2"
    assert client.get(url).text == client.get(url).text
