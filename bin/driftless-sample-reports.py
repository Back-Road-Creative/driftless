#!/usr/bin/env python3
"""Render the demo store's report documents, the bundle committed under docs/samples/.

    bin/driftless-sample-reports.py --out docs/samples --anchor 2026-07-01

Same store and the same pinning as ``bin/driftless-snapshot-pages.py``:
``driftless.demo.data`` builds every row from a fixed anchor by fixed offsets — no
``date.today()``, no randomness — seeded through the validated API into a throwaway
SQLite file, never raw SQL. Rendering then goes through ``driftless report all``
itself, at that anchor as the as-of, so the bundle is literally what an operator's
own run produces rather than a second rendering path free to disagree with it.

This bundle is **committed**, which is the one place it parts company with the page
snapshots and with ``reports/`` — both git-ignored on the reasoning that regenerable
output only rots. That reasoning is right about output nobody diffs. It is what the
drift gate in ``.github/workflows/ci.yml`` answers: every tracked file here is
rebuilt and diffed on every pull request, so a template or figure change either
refreshes the bundle in the same change or fails the run. The reason to pay that is
a reader — somebody deciding whether this tool is worth installing has, without
these files, nothing in the repository that shows what it actually produces.

Alongside the rendered documents, ``<out>/<anchor>/method-map.svg`` is the same
theory read the docs point a reader at: ``GET /map`` with no ``?project=``, so no
project's state washes any node, fetched off the identical seeded store through the
plain (unwrapped) app the demo store itself uses — no separate rendering path to
disagree with the one an operator's own browser hits. The graph is picked out by its
``aria-label`` rather than by being the first ``<svg>`` on the page — the legend
renders a swatch per shape and per knowledge area above it, so the positional read
committed a 153-byte chip. Only that one ``<svg>…</svg>`` element is kept, with the
whitespace between tags normalized to one newline per tag boundary — the template's
own per-node, per-edge line shape, kept rather than collapsed away, so a geometry
change re-churns the lines it actually touched instead of the whole (single-line)
file; the surrounding page prose is what ``docs/user-guide.md`` already says in
words.

Regenerating rewrites the whole ``<out>/<anchor>/`` subtree, so a document that goes
away leaves no stale sample behind. It deletes before it writes, and ``--out`` is
free-form operator input, so it takes the same rail its sibling does rather than
resting on the subtree name being an ISO date: :func:`claim` writes into a directory
this tool created or an empty one, and refuses anything else.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

# Pinned BEFORE any driftless import: driftless.calc.receipt reads the git SHA
# once, at import time, into the reproducibility receipt this generator now
# bakes into every committed sample. The real ``git rev-parse HEAD`` changes on
# every commit, which would make the committed bundle differ from what this
# script regenerates on the very next commit — the drift gate would never be
# green twice in a row. A fixed, obviously-fake SHA keeps the bundle (and the
# drift gate) exactly as deterministic as the fixed ``ANCHOR`` date already
# makes it.
os.environ.setdefault("DRIFTLESS_GIT_SHA", "sample")

from driftless.api.app import app, get_session  # noqa: E402
from driftless.db import Base, new_engine, new_session_factory  # noqa: E402
from driftless.demo.cli import seed  # noqa: E402
from driftless.demo.data import ANCHOR, demo_payload  # noqa: E402
from driftless.report import cli as report_cli  # noqa: E402

#: Dropped into a bundle directory the first time it is written, so a later run can tell
#: a directory this tool owns from one an operator pointed it at by mistake. Committed
#: with the samples, so a fresh clone regenerates in place instead of refusing its own.
MARKER = ".driftless-sample-reports"
MARKER_TEXT = (
    "Written by bin/driftless-sample-reports.py. Every document beside this file is\n"
    "regenerated output, committed so a reader can see it and diffed on every pull\n"
    "request so it cannot rot. Delete the directory, not this file, to hand the name\n"
    "back to something else.\n"
)

#: Every inline ``<svg>`` element on the page, in document order.
SVG_ELEMENT = re.compile(r"<svg\b.*?</svg>", re.DOTALL)
#: Which of them is the map. ``method_map.html`` renders a legend swatch per shape and
#: per knowledge area *before* the graph, every one of them ``aria-hidden="true"``, and
#: the graph is the only element on the page that names itself to a reader. Selecting on
#: that rather than on position is the whole point: "the first ``<svg>``" captured a
#: 153-byte chip, and because it captured the same chip every time, the drift gate — which
#: reruns this generator and diffs the bytes — stayed green over it. A gate comparing
#: generated output against a committed file can only prove the generator is
#: deterministic; it can never notice that it is deterministically wrong. The label also
#: survives what position does not: which view ``GET /map`` opens on, and how many
#: knowledge areas the legend enumerates.
LABELLED_SVG = re.compile(r"<svg\b[^>]*\baria-label=")
#: Whitespace between two tags carries nothing — no sibling in ``method_map.html`` ever
#: puts meaningful text there — so it is normalized to exactly one newline rather than
#: collapsed away: the template's ``{% for %}`` blocks already put every node and edge
#: on its own line, and keeping that shape means a geometry change re-churns only the
#: lines it actually touched instead of the whole (single-line, 78KB) file.
_INTER_TAG_WHITESPACE = re.compile(r">\s+<")


def _map_svg(client: TestClient, anchor: date) -> str:
    """The theory map's own SVG: no ``?project=``, so no project's reading is washed
    onto a node — the same picture a reader with no project in mind sees first."""
    response = client.get(f"/map?as_of={anchor.isoformat()}")
    if response.status_code != 200:
        raise SystemExit(f"GET /map -> {response.status_code}: could not render the map sample")
    found = [m.group(0) for m in SVG_ELEMENT.finditer(response.text)]
    labelled = [svg for svg in found if LABELLED_SVG.match(svg)]
    if not labelled:
        raise SystemExit(
            f"GET /map rendered no <svg> carrying an aria-label ({len(found)} unlabelled "
            f"element(s) on the page) — a legend swatch is not the map, so nothing is written"
        )
    if len(labelled) > 1:
        raise SystemExit(
            f"GET /map rendered {len(labelled)} labelled <svg> elements — which one is the "
            f"map is a guess, and guessing by position is the defect this refuses to repeat"
        )
    return _INTER_TAG_WHITESPACE.sub(">\n<", labelled[0])


def claim(out: Path) -> None:
    """Take ownership of ``out``, or refuse it.

    ``--out docs`` must not be able to clear documents nobody generated, so this
    writes only into a directory it created (marked by :data:`MARKER`), one that is
    empty, or one that does not exist yet — never into a directory holding files it
    cannot account for, rather than guessing which markdown is a sample.
    """
    if out.exists() and not (out / MARKER).exists() and any(out.iterdir()):
        raise SystemExit(
            f"{out}: has files and no {MARKER}, so it is not a bundle this tool wrote — "
            f"refusing to delete documents it did not write; pass a new or empty --out"
        )
    out.mkdir(parents=True, exist_ok=True)
    (out / MARKER).write_text(MARKER_TEXT, encoding="utf-8")


def _seed_store(client: TestClient, anchor: date) -> None:
    """Create the demo store through the API, exactly as ``driftless demo seed`` does."""

    def post(path: str, body: dict[str, Any]) -> int:
        response = client.post(path, json=body)
        if response.status_code >= 400:
            raise SystemExit(f"seed POST {path} -> {response.status_code}: {response.text[:200]}")
        return int(response.json()["id"])

    def patch(path: str, body: dict[str, Any]) -> None:
        response = client.patch(path, json=body)
        if response.status_code >= 400:
            raise SystemExit(f"seed PATCH {path} -> {response.status_code}: {response.text[:200]}")

    seed(post, demo_payload(anchor), patch)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the demo store's report documents.")
    parser.add_argument("--out", type=Path, default=Path("docs/samples"))
    parser.add_argument("--anchor", type=date.fromisoformat, default=ANCHOR, metavar="YYYY-MM-DD")
    args = parser.parse_args(argv)
    anchor: date = args.anchor
    out: Path = args.out

    with tempfile.TemporaryDirectory() as tmpdir:
        url = f"sqlite:///{Path(tmpdir) / 'samples.db'}"
        db_engine = new_engine(url)
        Base.metadata.create_all(db_engine)
        factory = new_session_factory(db_engine)

        def session() -> Iterator[Any]:
            with factory() as db:
                yield db

        app.dependency_overrides[get_session] = session
        try:
            client = TestClient(app, base_url="https://testserver")
            _seed_store(client, anchor)
            map_svg = _map_svg(client, anchor)
        finally:
            app.dependency_overrides.pop(get_session, None)

        claim(out)
        root = out / anchor.isoformat()
        if root.exists():
            # No ignore_errors: a half-cleared subtree would come back as a puzzling
            # drift diff in CI rather than as the failure it is, here.
            shutil.rmtree(root)
        rc = report_cli.main(
            ["report", "all", "--as-of", anchor.isoformat(), "--out", str(out), "--db-url", url]
        )
        if rc != 0:
            return rc
        (root / "method-map.svg").write_text(map_svg + "\n", encoding="utf-8")
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
