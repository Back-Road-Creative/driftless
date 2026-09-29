#!/usr/bin/env python3
"""Capture every page driftless serves as rendered HTML, from the shipped demo store.

    bin/driftless-snapshot-pages.py --out docs/page-snapshots --anchor 2026-07-01

**Rendered HTML, not a headless browser** — a decision, not a shortcut. Every chart on
this surface is inline SVG emitted server-side by a Jinja template, with no build step
and nothing rendered client-side, so the HTML response *is* the complete visual truth:
geometry, colour tokens, labels and all. A browser would add a heavyweight CI dependency
whose only new information is font rasterization.

The store is the demo one, created through the validated API by ``driftless demo seed``
(never raw SQL) into a throwaway SQLite file, at an ``--anchor`` passed explicitly so a
bundle can never float when that default moves.

The page list is **discovered, never written down**: :func:`page_templates` walks
``app.routes`` recursively — the descent an ``include_router`` holder needs, without
which a naive walk finds no page at all — and takes every ``PageRoute`` serving GET. A
hand-written list is what let ``/search``, ``/gantt``, ``/board`` and ``/org/heatmap``
escape the route probe for months, and a parameter nothing resolves raises rather than
being skipped: that is how ``/pmbok/{process_id}`` was dropped, its ids coming from the
frozen catalog rather than the store. Store-backed pages are captured once per seeded
row, so the demo's deliberately empty project sits in the bundle beside the full ones.

Determinism is what makes the bundle worth diffing: one anchor, the same bytes. Exactly
one value moves per render — the CSRF token, minted fresh whenever the browser holds no
cookie (``driftless/web/csrf.py``) — so :func:`normalize` replaces the hidden input's
value with a placeholder. Two runs compared byte for byte showed nothing else: no page
reads a wall clock, the as-of is pinned on every request, ids are insertion order. The
bundle is regenerable output, like ``reports/``: git-ignored, never committed — and
written only into a directory this tool created or an empty one, since a rerun clears
``*.html`` and ``--out`` is whatever an operator typed.

A page with a form ALSO carries a second value that moves with the token: the
reproducibility receipt's sha256 (``driftless/web/receipt.py``) is deliberately hashed
over the exact bytes served — CSRF field included, by design, so a saved copy of the
real page verifies against it (``tests/test_report_receipt.py``). Normalizing the token
in the served HTML without normalizing that derived digest would leave one value still
moving after :func:`normalize` claimed to have stopped it, so the digest is normalized
right alongside the token it is a function of.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import date
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.session import temporary_factory
from driftless.demo.cli import seed
from driftless.demo.data import ANCHOR, demo_payload
from driftless.pmbok import catalog
from driftless.web.artifacts import BY_SLUG as ARTIFACT_BY_SLUG
from driftless.web.errors import PageRoute
from driftless.pmbok.methods import METHODS
from driftless.web.techniques import BY_SLUG

Fetch = Callable[[str], tuple[int, str]]

#: The hidden input every form-bearing page carries, and the value that differs between
#: two runs at one anchor.
CSRF_VALUE = re.compile(r'(name="csrf_token" value=")[^"]*"')
PLACEHOLDER = "csrf-token-normalized-for-the-snapshot"
#: The reproducibility receipt's sha256 (``driftless/web/receipt.py``), on a
#: form-bearing page a function of the CSRF token above — it moves for the same
#: reason and is normalized alongside it, never separately from the value it hashes.
RECEIPT_DIGEST = re.compile(r"(sha256 )[0-9a-f]{64}")
DIGEST_PLACEHOLDER = "0" * 64

#: Every kind a page route is parameterized by: ``{project_id}`` is filled from
#: ``/projects``, and so on for the rest.
COLLECTIONS = ("project", "portfolio", "program", "department", "business")
PLURALS = {"business": "businesses"}

#: Dropped into a bundle directory the first time it is written, so a later run can tell
#: a directory this tool owns from one an operator pointed it at by mistake.
MARKER = ".driftless-page-snapshots"
MARKER_TEXT = (
    "Written by bin/driftless-snapshot-pages.py. Every *.html beside this file is\n"
    "regenerated output and is deleted on the next run. Delete the directory, not\n"
    "this file, to hand the name back to something else.\n"
)


def _leaves(route: Any) -> list[Any]:
    """``route`` itself, or the routes an ``include_router`` call nested under it."""
    for holder in (route, getattr(route, "original_router", None)):
        children = getattr(holder, "routes", None)
        if children:
            return [leaf for child in children for leaf in _leaves(child)]
    return [route]


def page_templates(routes: Iterable[Any]) -> list[str]:
    """Every path template the app mounts as a GET HTML page, read off the router."""
    return sorted(
        {
            leaf.path
            for top in routes
            for leaf in _leaves(top)
            if isinstance(leaf, PageRoute) and "GET" in getattr(leaf, "methods", set())
        }
    )


def page_urls(
    templates: Iterable[str], ids: Mapping[str, list[str]], as_of: date
) -> dict[str, list[str]]:
    """Template -> the URLs to capture for it: one per seeded id, as-of pinned on each.

    Unknown query parameters are ignored by FastAPI, so ``as_of`` is safe on every page
    and pins the ones that honour it.
    """
    urls: dict[str, list[str]] = {}
    for template in templates:
        paths = [template]
        if "{" in template:
            name = template[template.index("{") + 1 : template.index("}")]
            if not (values := list(ids.get(name, ()))):
                raise SystemExit(f"{template}: nothing in the demo store fills {{{name}}}")
            paths = [template.replace("{" + name + "}", value) for value in values]
        urls[template] = [f"{path}?as_of={as_of.isoformat()}" for path in paths]
    return urls


def snapshot_name(url: str) -> str:
    """The file a captured URL is written to: its path, flattened; ``/`` is the index.

    A ``?query`` and a ``#fragment`` both name something other than a file -- a
    parameter and an in-page anchor -- so neither survives into the name."""
    path = url.split("?")[0].split("#")[0]
    return (path.strip("/").replace("/", "-") or "index") + ".html"


def normalize(html: str) -> str:
    """Rendered HTML with the per-render CSRF token, and the receipt digest that
    hashes it in, both replaced by fixed placeholders."""
    html = CSRF_VALUE.sub(rf'\g<1>{PLACEHOLDER}"', html)
    return RECEIPT_DIGEST.sub(rf"\g<1>{DIGEST_PLACEHOLDER}", html)


def capture(fetch: Fetch, urls: Iterable[str]) -> dict[str, str]:
    """``{file name: normalized HTML}``; a page that does not render 200 stops the run."""
    pages = {}
    for url in urls:
        status, body = fetch(url)
        if status != 200:
            raise SystemExit(f"{url} -> {status}: a page in the walk did not render")
        pages[snapshot_name(url)] = normalize(body)
    return pages


def write_bundle(out: Path, pages: Mapping[str, str]) -> int:
    """Write the bundle whole, so a route that goes away leaves no stale page behind.

    Whole means the write clears ``*.html`` first, and ``--out`` is free-form operator
    input — so ``--out docs`` would delete hand-written pages this tool never made. It
    therefore only ever clears a directory it created (marked by :data:`MARKER`) or an
    empty one it may safely adopt, and refuses anything else rather than guessing which
    ``index.html`` is a snapshot.
    """
    if out.exists() and not (out / MARKER).exists() and any(out.iterdir()):
        raise SystemExit(
            f"{out}: has files and no {MARKER}, so it is not a bundle this tool wrote — "
            f"refusing to delete *.html it did not write; pass a new or empty --out"
        )
    out.mkdir(parents=True, exist_ok=True)
    (out / MARKER).write_text(MARKER_TEXT, encoding="utf-8")
    for stale in sorted(out.glob("*.html")):
        stale.unlink()
    for name, html in sorted(pages.items()):
        (out / name).write_text(html, encoding="utf-8")
    return len(pages)


def _bundle(client: TestClient, anchor: date) -> dict[str, str]:
    """Seed through the API, discover the pages, and capture every one of them."""

    def post(path: str, body: dict[str, Any]) -> int:
        response = client.post(path, json=body)
        if response.status_code >= 400:
            raise SystemExit(f"seed POST {path} -> {response.status_code}: {response.text[:200]}")
        return int(response.json()["id"])

    def patch(path: str, body: dict[str, Any]) -> None:
        response = client.patch(path, json=body)
        if response.status_code >= 400:
            raise SystemExit(f"seed PATCH {path} -> {response.status_code}: {response.text[:200]}")

    def fetch(url: str) -> tuple[int, str]:
        response = client.get(url)
        return response.status_code, response.text

    seed(post, demo_payload(anchor), patch)
    ids = {
        f"{kind}_id": [
            str(row["id"]) for row in client.get(f"/{PLURALS.get(kind, f'{kind}s')}").json()
        ]
        for kind in COLLECTIONS
    }
    # The PMBOK detail page is keyed by a frozen catalog clause rather than a stored row:
    # all 49 render one template over different reference text, so one stands for them.
    ids["process_id"] = [catalog.PROCESSES[0].id]
    # Same shape for the technique library: its pages are keyed by a slug the frozen
    # registry decides, not by a stored row, and all of them render one template over
    # different reference text — so one stands for them, as above.
    ids["slug"] = [sorted(BY_SLUG)[0]]
    # And for the method profiles: keyed by the frozen registry, one template.
    ids["key"] = [sorted(METHODS)[0]]
    # Same shape again for the artifact catalog: its detail page is keyed by
    # ``{kind_slug}`` rather than ``{slug}`` precisely so it does not collide with the
    # technique library's id above -- two different frozen-registry parameters sharing
    # one name would fill both from the same list.
    ids["kind_slug"] = [sorted(ARTIFACT_BY_SLUG)[0]]
    urls = page_urls(page_templates(app.routes), ids, anchor)
    return capture(fetch, [url for group in urls.values() for url in group])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture every driftless page as rendered HTML.")
    parser.add_argument("--out", type=Path, default=Path("docs/page-snapshots"))
    parser.add_argument("--anchor", type=date.fromisoformat, default=ANCHOR, metavar="YYYY-MM-DD")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = new_engine(f"sqlite:///{Path(tmpdir) / 'snapshot.db'}")
        Base.metadata.create_all(engine)
        factory = new_session_factory(engine)

        def session() -> Iterator[Any]:
            with factory() as db:
                yield db

        app.dependency_overrides[get_session] = session
        try:
            # https, as production serves: over http the Secure CSRF cookie is dropped, so
            # every render would remint and no form-bearing page could repeat itself.
            with (
                temporary_factory(factory),
                TestClient(app, base_url="https://testserver") as client,
            ):
                pages = _bundle(client, args.anchor)
        finally:
            app.dependency_overrides.pop(get_session, None)

    print(f"Captured: {write_bundle(args.out, pages)} pages at {args.anchor} -> {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
