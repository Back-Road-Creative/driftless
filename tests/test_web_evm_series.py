"""The weekly-status S-curve tells its series apart without hue, and repeats them as text.

The planned (PV) and actual (AC) curves used to be two solid strokes separated by
colour alone, at a COMPUTED 1.14:1 (light) / 1.08:1 (dark) against each other — below
even the 3:1 WCAG 1.4.11 asks of a graphical object a reader must identify, and about
1:1 in greyscale, so in print or on a photocopied status pack the reader cannot tell
which line went above which where they cross. That crossing is the entire point of a
planned-vs-actual curve. The legend repeated the same two colours on identical solid
swatches, so it could not disambiguate what the chart could not.

Three properties, none of them satisfiable by swapping one hue for another:

*Separability* — every pair of plotted series either clears 3:1 as a computed ratio in
BOTH schemes or differs in ``stroke-dasharray``, so a second, non-hue channel always
carries the identity. The ratio is computed from ``base.html``'s own tokens by
``test_web_a11y._ratio``, never eyeballed, and a failure prints the number.

*Legend fidelity* — each key is drawn with its series' exact stroke AND dash, so the
legend cannot promise a distinction the chart does not draw.

*A text twin* — every plotted point is a row, in plot order, the same ``scroll.wide``
idiom ``gantt.html`` and ``home.html`` already use. WHAT THIS DOES NOT PROVE: that the
twin carries a DATE per row. ``pages.evm_curve`` returns only ``pv``/``ac`` per sample
and the SVG draws no date axis either, so the twin repeats exactly what the chart
draws — the sequence and the crossing. A dated twin needs ``evm_curve`` to keep the
sample date it already computes, as ``gather.business_curve`` does.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.assess import adapters
from driftless.models import Project
import test_web_pages
from test_web_a11y import _ratio, _token_sets

# The seeded https store and the sweep under test, reused as is (assigned, not
# imported: a test's own parameter must not read as a redefined import, and
# ``driftless.web.pages`` must not be the first web module imported — it and
# ``api.app`` import each other, so reaching it through the module that already
# imported the app is what keeps this file runnable on its own).
client, db = test_web_pages.client, test_web_pages.db
evm_curve = test_web_pages.evm_curve
AS_OF, Q = test_web_pages.AS_OF, test_web_pages.Q

SERIES_FLOOR = 3.0  # WCAG 1.4.11 — a series is a meaningful graphical object
_FIGURE = re.compile(r'<figure class="evm"[^>]*>(.*?)</figure>', re.S)
_ROW = re.compile(r"<tr><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td></tr>")
_VAR = re.compile(r"var\((--[a-z-]+)\)")


class _Series(HTMLParser):
    """Every element the figure marks as a plotted series or as a legend key, as the
    (token, dash) pair it is painted with — the two channels a reader can tell apart."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.plotted: dict[str, tuple[str, str]] = {}
        self.keys: dict[str, tuple[str, str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        token = _VAR.search(attr.get("stroke", ""))
        paint = (token.group(1) if token else attr.get("stroke", ""), attr.get("stroke-dasharray"))
        if name := attr.get("data-series"):
            self.plotted[name] = (paint[0], paint[1] or "")
        elif name := attr.get("data-series-key"):
            self.keys[name] = (paint[0], paint[1] or "")


def _figure(browser: TestClient) -> _Series:
    page = browser.get(f"/projects/1/status{Q}").text
    body = _FIGURE.search(page)
    assert body is not None, "the weekly-status page renders no EVM figure to read"
    marked = _Series()
    marked.feed(body.group(1))
    assert len(marked.plotted) >= 2, (
        f"the S-curve marks {sorted(marked.plotted)} as plotted series — every stroke a reader "
        'must identify needs data-series="<name>", or no gate can see it'
    )
    return marked


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_no_two_plotted_series_are_told_apart_by_hue_alone(
    client: TestClient, db: Session, scheme: str
) -> None:
    tokens, marked = _token_sets()[scheme], _figure(client)
    names = sorted(marked.plotted)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            (one, dash_one), (two, dash_two) = marked.plotted[first], marked.plotted[second]
            ratio = _ratio(tokens[one], tokens[two])
            assert ratio >= SERIES_FLOOR or dash_one != dash_two, (
                f"{scheme}: {first} ({one} {tokens[one]}) and {second} ({two} {tokens[two]}) are "
                f"{ratio:.2f}:1 apart and share the dash {dash_one!r} — the pair is separated by "
                f"hue alone, below the {SERIES_FLOOR}:1 floor and indistinguishable in greyscale. "
                "Give one of them a stroke-dasharray, or a token pair that clears the floor."
            )


def test_every_legend_key_is_drawn_exactly_as_its_series_is(
    client: TestClient, db: Session
) -> None:
    marked = _figure(client)
    assert marked.keys == marked.plotted, (
        f"the legend draws {marked.keys} where the chart draws {marked.plotted} — a key painted "
        "differently from its series cannot disambiguate what the chart does not"
    )


def test_every_plotted_point_is_a_row_of_the_evm_text_twin(client: TestClient, db: Session) -> None:
    page = client.get(f"/projects/1/status{Q}").text
    project = db.scalars(select(Project).options(*adapters.eager_project())).one()
    evm = evm_curve(project, adapters.project_costs(db, project), AS_OF)
    assert evm["points"], "the fixture must plot something for the twin to repeat"
    figure = _FIGURE.search(page)
    assert figure is not None, "the weekly-status page renders no EVM figure"

    assert _ROW.findall(figure.group(1)) == [
        (str(index), f"{point['pv']:,.0f}", f"{point['ac']:,.0f}")
        for index, point in enumerate(evm["points"], start=1)
    ], (
        "every point the S-curve plots must appear as a row carrying its planned and actual "
        "figures, in plot order — otherwise where actual crossed planned is readable by eye only"
    )


def test_the_twin_scrolls_and_is_captioned_rather_than_bare(
    client: TestClient, db: Session
) -> None:
    """The same containment ``test_web_responsive`` walks, pinned at the source: the
    twin is a real table in a named scroll box, not a second chart."""
    figure = _FIGURE.search(client.get(f"/projects/1/status{Q}").text)
    assert figure is not None
    markup = figure.group(1)
    assert 'class="scroll-x"' in markup and 'tabindex="0"' in markup, "the twin cannot be scrolled"
    assert '<caption class="sr-only">' in markup, "the table states what it repeats"
    assert markup.count('<th scope="col">') == 3, "point, planned, actual — each column scoped"


def test_a_project_with_no_baseline_renders_no_twin_at_all(client: TestClient, db: Session) -> None:
    """The honest empty state: no approved baseline means no points, so there is no
    chart AND no table — never an empty one under a caption promising rows."""
    bare = Project(name="Bare", portfolio_id=1, delivery_mode="predictive")
    db.add(bare)
    db.commit()

    page = client.get(f"/projects/{bare.id}/status{Q}").text
    assert _FIGURE.search(page) is None and "No cost baseline yet" in page
    assert "S-curve as text" not in page, "no caption may promise rows the sweep cannot fill"
