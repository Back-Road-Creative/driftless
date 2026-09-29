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
from driftless.pmbok.model import KnowledgeArea
from driftless.pmbok.rollup import business_area_shares, business_process_cells
from driftless.web.templating import TEMPLATES

AS_OF = date(2026, 3, 31)
Q = f"?as_of={AS_OF.isoformat()}"
IDENTIFY_RISKS = catalog.get("11.2")  # assessable: risk_register, risk_report, assumption_log
# One grid cell: its self-link names the process, the badge carries the wash and the
# printed share (the title repeats it). Attribute order here is the template's own.
_CELL = re.compile(r'&process=([\d.]+)#listing"><span class="badge st-(\w+)" title="([^"]*)">')
CHARTER = catalog.get("4.1")  # an exemplar process, named by the catalog rather than by hand


def humanized(value: str) -> str:
    """The word-shaping rule as the PAGE reaches it: the very filter object the
    template runs ``{{ area | humanize }}`` through, looked up at call time.

    Restating ``.replace("_", " ").title()`` here is what this file used to do, and
    a restated rule agrees with a broken product for as long as both are broken the
    same way: change the rule and the labels move, the expectation moves with them,
    nothing fails. Reached through ``env.filters`` rather than imported from
    ``driftless.naming`` so the comparison is against the function the render
    actually resolves — see the substitution test at the foot of this module.
    """
    shape: object = TEMPLATES.env.filters["humanize"]
    assert callable(shape)
    return str(shape(value))


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


def test_the_map_200s_a_cell_per_process_nav_link_and_byte_identical(client: TestClient) -> None:
    first = client.get(f"/process-map{Q}")
    assert first.status_code == 200
    body = first.text
    assert body.count("<br>") == len(catalog.PROCESSES)  # one cell badge per catalog process
    assert CHARTER.id in body and CHARTER.name in body
    assert 'href="/process-map"' in body
    assert 'href="/process-map"' in client.get(f"/{Q}").text  # linked from the dashboard too
    assert client.get(f"/process-map{Q}").text == body  # pinned as-of fetch twice -> identical


def test_rings_render_the_business_area_shares_as_their_labels(
    client: TestClient, db: Session
) -> None:
    """A bare store rings every area ``no data yet``; once a project exists, Communications
    measures a real share — 10.1's communications plan is a tracked kind since the
    management-plan resolver wave, and nobody has written one, so the ring reads an
    honest 0% rather than no data yet — and every ring label must equal
    ``business_area_shares``' own formatted output, area for area."""
    comms = humanized(KnowledgeArea.COMMUNICATIONS.value)
    bare_body = client.get(f"/process-map{Q}").text
    assert f'aria-label="{comms} completion no data yet"' in bare_body

    alpha = _project(db, "Alpha")
    db.add(Risk(project=alpha, description="r", probability=0.3, impact=1000.0))
    db.add(NarrativeArtifact(project=alpha, kind="assumption_log", body="drone weather"))
    db.commit()

    body = client.get(f"/process-map{Q}").text
    assert f'aria-label="{comms} completion 0%"' in body  # tracked now, unwritten
    shares = business_area_shares(business_process_cells(db, AS_OF))
    for share in shares:
        label = f"{share.share * 100:.0f}%" if share.share is not None else "no data yet"
        assert f'aria-label="{humanized(share.area.value)} completion {label}"' in body


def test_the_business_map_links_the_method_map_and_the_reference(client: TestClient) -> None:
    body = client.get(f"/process-map{Q}").text
    assert 'href="/map"' in body
    assert 'href="/pmbok"' in body


def test_every_cell_also_links_its_process_reference(client: TestClient) -> None:
    body = client.get(f"/process-map{Q}").text
    assert f'href="/pmbok/{CHARTER.id}"' in body
    assert body.count('href="/pmbok/') == len(catalog.PROCESSES)


def test_the_ring_caption_names_what_the_rings_measure(client: TestClient) -> None:
    body = client.get(f"/process-map{Q}").text
    assert "produced or signed off" in body


def test_the_intro_explains_what_a_washed_cell_means(client: TestClient) -> None:
    """ "Washed" names the page's own colour code and was never explained: a reader
    meeting it here for the first time must learn, in the same breath, that a
    cell's background colour is tinted in proportion to a number, and a bigger
    share reads as a stronger tint. Pins the idea, not the wording, so a later
    rewording that still teaches it does not fail here."""
    body = client.get(f"/process-map{Q}").text
    intro = body.split("<h1>", 1)[1].split("<dl", 1)[0].lower()
    assert "colour" in intro or "color" in intro
    assert "background" in intro
    assert "tint" in intro
    assert "bigger" in intro or "larger" in intro or "greater" in intro


def test_the_listing_has_its_own_anchor_and_every_cell_link_targets_it(
    client: TestClient, db: Session
) -> None:
    _project(db, "Alpha")
    body = client.get(f"/process-map{Q}").text
    assert body.count("#listing") == len(catalog.PROCESSES)

    listing = client.get(f"/process-map{Q}&process=11.2").text
    assert 'id="listing"' in listing


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
    # cell self-link; #listing lands the click below the 80vh scroll box the grid sits in
    assert f'href="/process-map?as_of={AS_OF.isoformat()}&process=11.2#listing"' in body

    listing = client.get(f"/process-map{Q}&process=11.2").text
    assert f'href="/projects/{alpha.id}/process-map?as_of={AS_OF.isoformat()}"' in listing
    assert "Alpha" in listing and humanized(st.ProcessState.PRODUCED.value) in listing
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
    """The cells were counted but never READ: no assert tied a cell's printed
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
    # empties the pool instead and reads no data yet, which is why 5.3 keeps two holders.
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
    assert len(drawn) == len(catalog.PROCESSES)
    assert sorted(drawn) == sorted(c.process_id for c in cells)
    for cell in cells:
        if cell.share is None or cell.share == 0.0:
            band = "muted"
        elif cell.share < 0.5:
            band = "warn"
        elif cell.share < 1.0:
            band = "ok"
        else:
            band = "signed"
        label = f"{cell.share * 100:.0f}%" if cell.share is not None else "no data yet"
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


def test_every_ring_label_moves_when_the_word_rule_itself_is_substituted(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard that a copy cannot pass. Two spellings that merely agree today
    agree forever without either one being the rule; so the rule is REPLACED — with
    a marker shape that restates none of its arithmetic — and every ring label is
    required to move to the new spelling and to leave the old one nowhere on the
    page. A test that rebuilt the label from the rule's own arithmetic fails here,
    which is the point: it would still be spelling the old rule.
    """
    _project(db, "Alpha")
    areas = [share.area.value for share in business_area_shares(business_process_cells(db, AS_OF))]
    assert areas, "no area rings rendered — the substitution would prove nothing"
    before = client.get(f"/process-map{Q}").text
    was = {area: humanized(area) for area in areas}
    for area in areas:
        assert f'aria-label="{was[area]} completion' in before

    monkeypatch.setitem(TEMPLATES.env.filters, "humanize", lambda text: f"({text})")
    after = client.get(f"/process-map{Q}").text
    for area in areas:
        assert f'aria-label="{humanized(area)} completion' in after, (
            f"{area}'s ring label kept its old spelling after the word rule was replaced — "
            "the page is not rendering through the rule this test reaches"
        )
        assert f'aria-label="{was[area]} completion' not in after, (
            f"{area}'s ring is still labelled by the old spelling as well"
        )


_CSS = Path(__file__).resolve().parents[1] / "driftless/web/static/driftless.css"
_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_RULES = re.compile(r"([^{}@]+)\{([^{}]*)\}")


def _declarations(selector: str) -> str:
    """Every declaration driftless.css writes for a rule naming ``selector``, joined —
    the frozen column takes one rule for the band and a second for the corner where it
    crosses the header, and reading only the first would pass a sheet that lost the other.
    Same helper, same reasoning as ``test_web_heatmap``'s."""
    return " ".join(
        body for sel, body in _RULES.findall(_COMMENT.sub("", _CSS.read_text())) if selector in sel
    )


def test_the_scroll_box_is_the_containing_block_its_off_screen_text_positions_against() -> None:
    """The 475px defect, pinned at the tier that can still see its CAUSE.

    ``_scroll.wide()`` was in the template and the box measured a correct 1232px, yet
    ``/process-map`` pushed the document to 2030px inside a 1280px viewport (1357px of
    overflow at 390px). ``.sr-only`` is ``position: absolute``, and an absolutely
    positioned box lays out against its nearest POSITIONED ancestor — with none, the
    initial containing block, which no intermediate overflow box clips. So all fifty
    off-screen spans in the grid sat outside the scroll box and stretched the document
    to the widest one's right edge. ``position: relative`` makes the box the containing
    block, and this is the one declaration the whole fix rests on: a stylesheet that
    drops it is red here rather than only in the opt-in browser tier.
    """
    scroll = _declarations(".scroll-x")
    assert re.search(r"position:\s*relative", scroll), (
        "driftless.css's .scroll-x is not a containing block, so an absolutely positioned "
        "descendant (.sr-only) escapes its clip and stretches the document sideways"
    )
    assert re.search(r"position:\s*absolute", _declarations(".sr-only")), (
        "the rule above is only load-bearing while .sr-only is absolutely positioned — "
        "if that changed, re-argue it rather than leaving a comment claiming a cause"
    )


def test_the_area_column_and_the_group_headings_stay_put_while_the_grid_scrolls(
    client: TestClient, db: Session
) -> None:
    """Ten knowledge-area rows by six process groups of stacked chips is wider than any
    viewport and taller than most, so both headings freeze: the area pins to the left edge
    while the groups pass under it, the group headings pin to the top while the areas pass
    under them. ``thead``/``tbody`` are written out because the rule addresses ``thead th``
    and a row the parser invents lands in ``tbody``, freezing nothing. Vertical freezing
    needs a scrollport, which is what the box's own max-height gives it."""
    _project(db, "Alpha")
    page = client.get(f"/process-map{Q}").text
    assert '<table class="process-grid">' in page, "the grid does not claim its own rule"
    assert "<thead>" in page and "<tbody>" in page, "the headings are not in a thead of their own"
    frozen = len(list(KnowledgeArea)) + 1  # one cell per area row, plus the column's own head
    assert page.count('class="pg-area"') == frozen, "the frozen column does not span the grid"

    band = _declarations(".pg-area")
    assert "position: sticky" in band and "box-sizing: border-box" in band, band
    assert re.search(r"left:\s*0\b", band), "the knowledge-area column is not pinned to the edge"
    width = re.search(r"(?<!max-)(?<!min-)width:\s*([\d.]+)rem", band)
    assert width is not None and float(width.group(1)) < 20.0, "no grid left to scroll on a phone"

    heads = _declarations(".process-grid thead th")
    assert "position: sticky" in heads and re.search(r"top:\s*0\b", heads), heads
    assert re.search(r"max-height:", _declarations(".scroll-x:has(> .process-grid)")), (
        "the box has no bounded height, so `top: 0` freezes the headings against nothing"
    )

    def _layer(selector: str) -> int:
        found = re.search(r"z-index:\s*(\d+)", _declarations(selector))
        assert found is not None, f"{selector} declares no stacking order"
        return int(found.group(1))

    # thead comes FIRST in the document, so at an equal z-index every row below would paint
    # over the frozen headings and the freeze would be invisible exactly while it mattered.
    column = _layer(".process-grid .pg-area")
    assert _layer(".process-grid thead th") > column, "the rows paint over the frozen headings"
    assert _layer(".process-grid thead .pg-area") > _layer(".process-grid thead th"), (
        "the corner where the two frozen bands cross sits under one of them"
    )
