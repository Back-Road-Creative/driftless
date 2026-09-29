"""Every page route the app mounts is decided on purpose: exported by the showcase,
or named in ``EXCLUDED_ROUTES`` with a reason. A hand-written page list is what let
``/search``, ``/gantt``, ``/board`` and ``/org/heatmap`` escape a router probe for
months (see ``bin/driftless-snapshot-pages.py``'s own docstring); this is the same
guarantee applied to the showcase's own page walk."""

import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "driftless-showcase.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("driftless_showcase_route_coverage", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expected_pattern(template: str) -> re.Pattern[str]:
    """The showcase's flattened file name for ``template``, with each ``{param}``
    open to whatever id or slug filled it -- matching :func:`snapshot_name`."""
    flattened = template.strip("/").replace("/", "-") or "index"
    return re.compile(rf"^{re.sub(r'\{[^}}]+\}', '.+', flattened)}\.html$")


def test_excluded_routes_name_only_routes_the_router_still_mounts() -> None:
    """A stale ``EXCLUDED_ROUTES`` entry is dead documentation nobody re-checks."""
    demo = _load()
    snapshot = demo._snapshot_module()
    templates = set(snapshot.page_templates(snapshot.app.routes))
    stale = set(demo.EXCLUDED_ROUTES) - templates
    assert not stale, f"EXCLUDED_ROUTES names a route the router no longer mounts: {stale}"
    for template, reason in demo.EXCLUDED_ROUTES.items():
        assert reason.strip(), f"{template}: excluded with no reason"


@pytest.fixture(scope="module")
def route_coverage_bundle() -> dict[str, str]:
    """One real render + transform, shared by the tests below."""
    demo = _load()
    snapshot = demo._snapshot_module()
    pages = demo.render_showcase(snapshot, demo.ANCHOR, "Season 4 Rollout")
    result: dict[str, str] = demo.transform_bundle(pages, demo.ANCHOR.isoformat(), "vtest")
    return result


def test_every_mounted_get_page_is_exported_or_excluded_with_a_reason(
    route_coverage_bundle: dict[str, str],
) -> None:
    demo = _load()
    snapshot = demo._snapshot_module()
    files = set(route_coverage_bundle)
    for template in snapshot.page_templates(snapshot.app.routes):
        if template in demo.EXCLUDED_ROUTES:
            continue
        pattern = _expected_pattern(template)
        assert any(pattern.match(name) for name in files), (
            f"{template}: mounted by the router but not in the showcase bundle, "
            f"and not named in EXCLUDED_ROUTES"
        )


def test_the_written_index_page_links_to_nothing_the_bundle_lacks(
    tmp_path: Path, route_coverage_bundle: dict[str, str]
) -> None:
    """A link whose target IS exported must never be marked unavailable -- the
    showcase's whole promise is that the dashboard a reader lands on actually works."""
    demo = _load()
    out = tmp_path / "showcase"
    demo.write_bundle(out, route_coverage_bundle, demo.ANCHOR.isoformat(), "vtest")
    index = (out / "index.html").read_text(encoding="utf-8")
    # The class definition in the export's own <style> block is not a dead link; only
    # a span or SVG group actually wearing the class marks one.
    dead = re.findall(r'<(?:span|g) class="showcase-unavailable">', index)
    assert not dead, f"the dashboard carries {len(dead)} dead link(s)"
