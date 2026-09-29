"""The weekly-status trend draws elapsed time, and its RAG history is readable as text.

The chart positioned every point by ROW INDEX (``34 + loop.index0 / span * 274``) while
calling itself a trend over ``taken_on``. Nothing enforces a weekly cadence — the only
rule on the series is ``uq_status_snapshot_project_date`` (one row per project per DATE,
``models/records.py``) and the form writes at whatever ``as_of`` it is posted — so three
readings on consecutive days and a fourth three months later plotted as four evenly
spaced points, and the slope between them read as a rate of progress it never was.

That is what separates this chart from the dashboard S-curve, the burn sparkline and the
EVM curve: those are index-plotted too, but honestly, because their samples come from
``gather.sample_dates``, which is evenly spaced BY CONSTRUCTION. This series is stored
rows at operator-chosen dates. **A fixture with evenly spaced snapshots cannot tell the
two apart** — hence the deliberately uneven one below.

Second property: each point's RAG was carried by a fill colour (adjacent RAG values sit
1.01–1.31:1 apart) and a hover-only ``<title>`` inside an SVG marked ``role="img"``,
which prunes it. The page carried no status history anywhere else, so the RAG series was
reachable by nobody but a mouse user with normal colour vision. It is now a text twin —
date, percent and RAG per row — in the same ``scroll.wide`` idiom the EVM twin uses.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless.models import StatusSnapshot

# A web route module must not be the first web import here — they and
# ``api.app`` import each other — so the seeded https client is reached through the
# module that already imported the app, exactly as ``test_web_evm_series`` does.
import test_web_pages

client, db = test_web_pages.client, test_web_pages.db
Q = test_web_pages.Q

# Three readings a day apart and a fourth nearly three months later. On an ordinal
# axis the first three spread across two thirds of the chart; on a time axis they
# are a cluster at the left edge.
UNEVEN: list[tuple[date, int, str]] = [
    (date(2026, 1, 5), 10, "red"),
    (date(2026, 1, 6), 12, "amber"),
    (date(2026, 1, 7), 14, "green"),
    (date(2026, 3, 31), 85, "green"),
]
_TREND = re.compile(r'<figure class="trend"[^>]*>(.*?)</figure>', re.S)
_CX = re.compile(r'<circle cx="([0-9.]+)"')
_LINE = re.compile(r'<polyline[^>]*points="([^"]*)"')
_AXIS = re.compile(r"<text[^>]*>(\d{4}-\d{2}-\d{2})</text>")
_ROW = re.compile(r"<tr><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td></tr>")


def _seed(session: Session, rows: Sequence[tuple[date, int, str]] = UNEVEN) -> None:
    for taken_on, percent, rag in rows:
        session.add(
            StatusSnapshot(
                project_id=1, taken_on=taken_on, percent_complete=percent, rag_status=rag
            )
        )
    session.commit()


def _figure(browser: TestClient) -> str:
    body = _TREND.search(browser.get(f"/projects/1/status{Q}").text)
    assert body is not None, "the weekly-status page renders no trend figure to read"
    return body.group(1)


def test_each_snapshot_is_plotted_at_its_real_distance_in_time(
    client: TestClient, db: Session
) -> None:
    _seed(db)
    first, last = UNEVEN[0][0], UNEVEN[-1][0]
    span = (last - first).days
    expected = [34 + (taken_on - first).days / span * 274 for taken_on, _, _ in UNEVEN]
    plotted = [float(x) for x in _CX.findall(_figure(client))]
    assert plotted == pytest.approx(expected, abs=0.2), (
        f"snapshots taken {[str(row[0]) for row in UNEVEN]} plot at x={plotted}, where their "
        f"real position along the elapsed span is {[round(x, 1) for x in expected]} — the axis "
        "is the row index, so the slope reports a rate of progress the dates do not support"
    )


def test_the_time_axis_names_the_span_it_is_drawn_over(client: TestClient, db: Session) -> None:
    _seed(db)
    first, last = UNEVEN[0][0], UNEVEN[-1][0]
    assert _AXIS.findall(_figure(client)) == [first.isoformat(), last.isoformat()], (
        "the trend carries no date on its axis, so the span a reader measures the slope "
        "against — a week or a year — is nowhere on the chart"
    )


def test_every_snapshots_rag_is_reachable_as_text(client: TestClient, db: Session) -> None:
    _seed(db)
    figure = _figure(client)
    assert _ROW.findall(figure) == [
        (taken_on.isoformat(), f"{percent}%", rag) for taken_on, percent, rag in UNEVEN
    ], (
        "the RAG history is carried by a dot's fill and a hover-only <title> inside a "
        'role="img" SVG that prunes it — every reading needs a row carrying its date, '
        "percent and RAG, or the series is readable by mouse and normal colour vision only"
    )
    assert 'class="scroll-x"' in figure and '<caption class="sr-only">' in figure, (
        "the twin is a named, scrollable table, not a second chart"
    )


def test_the_polyline_plots_percent_against_elapsed_time_point_for_point(
    client: TestClient, db: Session
) -> None:
    """The dots' x-positions are pinned above; the LINE through them was never
    read as values, so a polyline looping the wrong series — every y at zero,
    or x by row index again — stayed green. Each pair must be the template's
    own mapping of the stored rows: x along the elapsed span, y the percent."""
    _seed(db)
    line = _LINE.search(_figure(client))
    assert line is not None, "the trend draws no polyline through its readings"
    plotted = [float(value) for xy in line.group(1).split() for value in xy.split(",")]
    first, span = UNEVEN[0][0], (UNEVEN[-1][0] - UNEVEN[0][0]).days
    expected: list[float] = []
    for taken_on, percent, _ in UNEVEN:
        expected.append(34 + (taken_on - first).days / span * 274)
        expected.append(12 + (100 - percent) / 100 * 104)
    assert plotted == pytest.approx(expected, abs=0.06), (
        "the trend polyline does not pass through the stored readings"
    )


def test_a_single_snapshot_still_renders(client: TestClient, db: Session) -> None:
    """One reading spans zero days: the position is 0/0, which must not divide."""
    _seed(db, [UNEVEN[0]])
    assert len(_CX.findall(_figure(client))) == 1
