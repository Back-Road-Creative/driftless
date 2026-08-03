"""The page-snapshot bundle: every page the app serves, captured byte-identically.

Two properties, and between them they are the whole tool. **Coverage** is read off the
app's own router — the same walk the generator uses, never a list written here — so a
page mounted tomorrow is required in the bundle without anyone remembering to add it,
which is how ``/search``, ``/gantt``, ``/board`` and ``/org/heatmap`` escaped the route
probe while it carried a hand-written list. **Determinism** is checked the only way it
honestly can be: generate the whole bundle twice at one anchor and compare bytes, so the
per-render CSRF token (or anything else that moves) fails here rather than as noise in a
reviewer's diff.
"""

import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest

from driftless.api.app import app

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "driftless-snapshot-pages.py"
ANCHOR = "2026-07-01"

Bundle = dict[str, bytes]


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("driftless_snapshot_pages", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _generate(out: Path) -> Bundle:
    """One full run of the generator, as an operator runs it, read back as bytes."""
    assert _load().main(["--out", str(out), "--anchor", ANCHOR]) == 0
    return {path.name: path.read_bytes() for path in out.glob("*.html")}


@pytest.fixture(scope="module")
def bundles(tmp_path_factory: pytest.TempPathFactory) -> tuple[Bundle, Bundle]:
    """Two runs at the same anchor — the pair both properties below read."""
    root = tmp_path_factory.mktemp("page-snapshots")
    return _generate(root / "first"), _generate(root / "second")


def _shape(template: str) -> re.Pattern[str]:
    """The file name a route template's snapshot must take, with real ids in place."""
    flat = re.sub(r"\{[^}]+\}", "#", template.strip("/").replace("/", "-")) or "index"
    return re.compile(re.escape(flat).replace("\\#", r"[\w.-]+") + r"\.html")


def test_the_bundle_covers_every_page_route_the_app_mounts(bundles: tuple[Bundle, Bundle]) -> None:
    templates = _load().page_templates(app.routes)
    assert len(templates) > 10, (
        f"the walk found next to nothing, so this proves nothing: {templates}"
    )
    missing = [t for t in templates if not any(_shape(t).fullmatch(name) for name in bundles[0])]
    assert not missing, (
        f"the app serves these pages and the bundle does not carry them: {missing}. A design "
        f"audit reads the bundle, so a page missing from it is a page nobody looks at."
    )


def test_two_runs_at_the_same_anchor_are_byte_identical(bundles: tuple[Bundle, Bundle]) -> None:
    first, second = bundles
    assert sorted(first) == sorted(second), "the two runs captured different pages"
    moved = sorted(name for name, html in first.items() if second[name] != html)
    assert not moved, (
        f"these pages re-rendered differently at the same as-of: {moved}. The bundle is only "
        f"worth diffing if a design change is the only thing that can change it."
    )
