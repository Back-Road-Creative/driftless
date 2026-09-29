"""``bin/driftless-sample-reports.py``'s ``method-map.svg``: the theory map, no
project, extracted from ``GET /map`` and written beside the rendered reports so
``bin/driftless-gates.sh --samples`` byte-diffs it exactly like the rest of the
committed bundle (:mod:`test_sample_drift_gate`).

``_map_svg`` is unit-tested against a stub client first — the selection rule
(the one ``<svg>`` element that names itself with an ``aria-label``, never the
one that happens to come first) should not need the real app to prove. ``GET
/map`` renders a legend swatch per shape and per knowledge area *before* the
graph, so "the first ``<svg>``" is a 153-byte chip; the committed sample was
exactly that for as long as the drift gate has been green, because a gate that
diffs generated output against a committed file proves only that the generator
is deterministic, never that it captured the right element. The full run,
seeding the demo store and regenerating twice, proves byte-identical output —
and the committed bundle is checked for the map's own identity, which no legend
chip can satisfy.
"""

from __future__ import annotations

import importlib.util
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from driftless.pmbok.catalog import PROCESSES

REPO = Path(__file__).resolve().parents[1]


def _load(name: str, script: str) -> Any:
    """Import ``bin/driftless-sample-reports.py`` by path — a command, not a package."""
    spec = importlib.util.spec_from_file_location(name, REPO / "bin" / script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


samples = _load("driftless_sample_reports_map_svg", "driftless-sample-reports.py")
ANCHOR = date(2026, 7, 1)

#: One of the thirteen legend swatches ``method_map.html`` renders above the graph —
#: an ``aria-hidden`` chip, and the element the old positional rule captured.
LEGEND_CHIP = (
    '<svg class="map-legend-swatch" viewBox="0 0 16 16" aria-hidden="true">'
    '<rect x="1" y="1" width="14" height="14" rx="3" class="map-legend-process"/></svg>'
)
#: The graph itself, shaped as the template writes it: labelled, never hidden.
MAP_SVG = (
    '<svg viewBox="0 0 1648 1212" aria-label="The method graph: every process, '
    'technique and artifact, and every tie between them">'
    '<g class="node node-process" data-node="p1"/></svg>'
)


def _assert_is_the_method_graph(svg: str) -> None:
    """Properties a legend swatch can never hold: the graph's own viewBox and label,
    and a node for at least every PMBOK process. ``len(PROCESSES)`` rather than a
    number typed here, so the floor tracks the catalog — and it holds whichever view
    ``GET /map`` opens on, since every view draws the processes."""
    assert 'aria-label="The method graph' in svg
    assert re.search(r'<svg\b[^>]*\bviewBox="0 0 \d{3,} \d{3,}"', svg), svg[:200]
    assert "map-legend-swatch" not in svg
    assert svg.count('data-node="') >= len(PROCESSES), svg.count('data-node="')


class _Response:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


class _Client:
    def __init__(self, status_code: int, text: str) -> None:
        self._response = _Response(status_code, text)
        self.requested: str | None = None

    def get(self, url: str) -> _Response:
        self.requested = url
        return self._response


def test_the_svg_element_is_extracted_and_nothing_else_on_the_page() -> None:
    page = f"<html><body><p>prose</p>{MAP_SVG}</body></html>"
    client = _Client(200, page)

    extracted = samples._map_svg(client, ANCHOR)  # type: ignore[arg-type]

    assert extracted == MAP_SVG
    assert client.requested == "/map?as_of=2026-07-01"


def test_the_map_is_chosen_by_its_label_not_by_coming_first_on_the_page() -> None:
    """The defect: thirteen legend chips render before the graph, so the first
    ``<svg>`` on the page is a 153-byte swatch."""
    page = f"<html><body>{LEGEND_CHIP * 13}{MAP_SVG}</body></html>"
    client = _Client(200, page)

    extracted = samples._map_svg(client, ANCHOR)  # type: ignore[arg-type]

    assert extracted == MAP_SVG
    assert "map-legend-swatch" not in extracted


def test_a_page_of_legend_chips_alone_is_refused_rather_than_written() -> None:
    """A chip is not a near-miss for the map — writing one is the bug, so refuse."""
    client = _Client(200, f"<html><body>{LEGEND_CHIP * 13}</body></html>")

    with pytest.raises(SystemExit) as refusal:
        samples._map_svg(client, ANCHOR)  # type: ignore[arg-type]

    assert "no <svg>" in str(refusal.value)


def test_two_labelled_svgs_are_refused_rather_than_guessed_between() -> None:
    """Selection has to stay unambiguous: if the page ever grows a second labelled
    figure, picking one by position is the mistake this fix exists to end."""
    client = _Client(200, f"<html><body>{MAP_SVG}{MAP_SVG}</body></html>")

    with pytest.raises(SystemExit) as refusal:
        samples._map_svg(client, ANCHOR)  # type: ignore[arg-type]

    assert "2" in str(refusal.value)


def test_whitespace_between_tags_is_one_newline_but_a_labels_own_space_survives() -> None:
    """The template's per-element whitespace becomes exactly one newline per tag
    boundary — enough to make a geometry diff readable — while the space inside a
    label's own text (not whitespace *between* two tags) is untouched."""
    page = (
        '<html><body><svg viewBox="0 0 1648 1212" aria-label="The method graph">\n'
        '<path d="M 0 0"/>\n'
        '<text><tspan aria-hidden="true">x</tspan> Label</text>\n'
        "</svg></body></html>"
    )
    client = _Client(200, page)

    extracted = samples._map_svg(client, ANCHOR)  # type: ignore[arg-type]

    assert extracted == (
        '<svg viewBox="0 0 1648 1212" aria-label="The method graph">\n'
        '<path d="M 0 0"/>\n'
        '<text><tspan aria-hidden="true">x</tspan> Label</text>\n'
        "</svg>"
    )
    assert '<tspan aria-hidden="true">x</tspan> Label</text>' in extracted


def test_a_non_200_response_is_refused_rather_than_written() -> None:
    client = _Client(500, "boom")

    with pytest.raises(SystemExit) as refusal:
        samples._map_svg(client, ANCHOR)  # type: ignore[arg-type]

    assert "500" in str(refusal.value)


def test_a_page_with_no_svg_element_is_refused() -> None:
    client = _Client(200, "<html><body>no chart here</body></html>")

    with pytest.raises(SystemExit) as refusal:
        samples._map_svg(client, ANCHOR)  # type: ignore[arg-type]

    assert "no <svg>" in str(refusal.value)


def test_regenerating_the_bundle_writes_a_byte_identical_map_svg(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"

    assert samples.main(["--out", str(first), "--anchor", ANCHOR.isoformat()]) == 0
    assert samples.main(["--out", str(second), "--anchor", ANCHOR.isoformat()]) == 0

    name = ANCHOR.isoformat() + "/method-map.svg"
    one, two = (first / name).read_bytes(), (second / name).read_bytes()
    assert one == two
    assert one.startswith(b"<svg") and one.strip().endswith(b"</svg>")
    assert one.count(b"\n") > 100, "one element per line keeps a geometry diff readable"
    _assert_is_the_method_graph(one.decode("utf-8"))


def test_the_committed_sample_is_the_graph_and_not_a_legend_chip() -> None:
    """What the drift gate structurally cannot ask. It reruns the generator and diffs
    the bytes, so a consistently wrong capture is a consistently green gate; the
    committed file has to be checked for what it *is*, not only that it is stable."""
    _assert_is_the_method_graph(
        (REPO / "docs" / "samples" / "2026-07-01" / "method-map.svg").read_text(encoding="utf-8")
    )
