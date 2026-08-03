"""The dashboard S-curve carries the same figures as text, on the argument that
earned the Gantt its table twin (``gantt.html``): the endpoint pair was already
reachable through the SVG's ``aria-label``, but the SHAPE — where actual crossed
planned, and by how much at each sampled date — was reachable by eye alone.

What is asserted is the PAIRING, not the arithmetic: every point
``gather.business_curve`` plots must appear as a row carrying its date and both
figures, in plot order, formatted exactly as the chart's own end labels are. A
point added to the sweep with no row, or a row the sweep does not produce, is a
chart a screen reader reads a summary of and nothing else."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.report import gather
import test_web_home

# The seeded store and its row helpers, reused as is (assigned, not imported: a
# test's own parameter must not read as a redefined import).
client, db = test_web_home.client, test_web_home.db
AS_OF, JAN = test_web_home.AS_OF, test_web_home.JAN
_portfolio, _project = test_web_home._portfolio, test_web_home._project

_SECTION = re.compile(r'<section class="chart-curve">(.*?)</section>', re.S)
_ROW = re.compile(r"<tr><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td></tr>")


def test_every_plotted_point_is_a_row_of_the_s_curve_text_twin(
    client: TestClient, db: Session
) -> None:
    _project(db, _portfolio("Content Brands"), "GMS", percent=25, spends=((JAN, 400.0),))

    page = client.get("/").text
    curve = gather.business_curve(gather.leaf_projects(db), gather.project_costs(db), AS_OF)
    assert curve["points"], "the fixture must plot something for the twin to repeat"
    section = _SECTION.search(page)
    assert section is not None, "the dashboard renders no S-curve section"

    assert _ROW.findall(section.group(1)) == [
        (point["date"], f"{point['pv']:,.0f}", f"{point['ac']:,.0f}") for point in curve["points"]
    ], (
        "every point the S-curve plots must appear as a row carrying its date, its planned "
        "figure and its actual one, in plot order — otherwise the shape of the two lines is "
        "readable by eye only"
    )


def test_the_twin_scrolls_and_is_captioned_rather_than_bare(
    client: TestClient, db: Session
) -> None:
    """The same containment ``test_web_responsive`` walks, pinned at the source:
    the twin is a real table in a named scroll box, not a second chart."""
    _project(db, _portfolio("Content Brands"), "GMS", percent=25, spends=((JAN, 400.0),))

    section = _SECTION.search(client.get("/").text)
    assert section is not None
    markup = section.group(1)
    assert 'class="scroll-x"' in markup and 'tabindex="0"' in markup, "the twin cannot be scrolled"
    assert '<caption class="sr-only">' in markup, "the table states what it repeats"
    assert markup.count('<th scope="col">') == 3, "date, planned, actual — each column scoped"


def test_a_business_with_nothing_baselined_renders_no_twin_at_all(
    client: TestClient, db: Session
) -> None:
    """The honest empty state: no baseline anywhere means no points, so there is
    no chart AND no table — never an empty one under a caption promising rows."""
    db.add(m.Project(name="Bare", portfolio=_portfolio("Content"), delivery_mode="predictive"))
    db.commit()

    page = client.get("/").text
    assert gather.business_curve(gather.leaf_projects(db), gather.project_costs(db), AS_OF) == {
        "points": []
    }
    assert 'class="scurve"' not in page and _SECTION.search(page) is None
    assert "S-curve as text" not in page, "no caption may promise rows the sweep cannot fill"
