"""The publishable showcase is a read-only transform of the real page bundle."""

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any, cast

import pytest

from driftless.naming import technique_slug
from driftless.pmbok.graph import GRAPH

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "driftless-showcase.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("driftless_showcase", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: The project-scoped pages exported alongside the read-only method map, catalogs and
#: assistants -- everything except the four already carried before this change.
PROJECT_PAGES = {"flow", "raid", "status", "process-map"}
ASSIST_PAGES = {
    "cost",
    "earned-value",
    "schedule",
    "scope",
    "requirements",
    "risk-responses",
    "quality",
    "team",
    "stakeholders",
    "procurement",
    "decisions",
    "closeout",
}
GLOBAL_PAGES = {
    "map",
    "pmbok",
    "pmbok-proof",
    "methods",
    "artifacts",
    "techniques",
    "glossary",
    "org-heatmap",
}


@pytest.fixture(scope="module")
def transformed_showcase() -> dict[str, str]:
    """One real render + transform, shared by every assertion below."""
    demo = _load()
    snapshot = demo._snapshot_module()
    pages = demo.render_showcase(snapshot, demo.ANCHOR, "Season 4 Rollout")
    return cast(dict[str, str], demo.transform_bundle(pages, demo.ANCHOR.isoformat(), "vtest"))


def test_transform_makes_the_real_pages_portable_and_read_only() -> None:
    pages = {
        "index.html": """<!doctype html><html><head><title>Dashboard</title>
<link rel="stylesheet" href="/static/driftless.css">
<script src="/static/driftless.js" defer></script></head><body>
<nav><a href="/threats?as_of=2026-07-01">Threats</a><a href="/org/heatmap">Capacity</a>
<a href="/login">Sign in</a></nav>
<form method="post" action="/sign-off"><button>Sign off</button></form>
<p>Stable output</p>TRAILING
</body></html>""",
        "threats.html": """<!doctype html><html><head><title>Threats</title></head><body>
<a href="/">Dashboard</a></body></html>""",
        "login.html": "<!doctype html><html><head></head><body>Login</body></html>",
    }
    pages["index.html"] = pages["index.html"].replace("TRAILING", "  ")

    transformed = _load().transform_bundle(pages, anchor="2026-07-01", source="v0.2.0")

    assert set(transformed) == {"index.html", "threats.html"}
    index = transformed["index.html"]
    assert 'href="threats"' in index, "the sibling link must be extensionless"
    assert 'href="/org/heatmap"' not in index and "Capacity" in index
    assert 'href="/login"' not in index
    assert "<form" not in index and "<button" not in index
    assert "<script" not in index
    assert 'href="/static/driftless.css"' not in index
    assert index.count('<link rel="stylesheet" href="driftless.css">') == 1
    real_css = (
        Path(_load().__file__).resolve().parents[1]
        / "driftless"
        / "web"
        / "static"
        / "driftless.css"
    ).read_text(encoding="utf-8")
    real_rule = next(
        line for line in real_css.splitlines() if line and not line.startswith(("/*", " ", "*"))
    )
    assert real_rule not in index, "driftless.css was inlined instead of shipped as a sibling file"
    assert '<meta name="robots" content="noindex, nofollow">' in index
    assert "Fixed fictional demo" in index
    assert "2026-07-01" in index
    assert (
        '<a href="https://headlessmode.com/driftless/">&larr; Back to headlessmode.com/driftless</a>'
        in index
    )
    assert not any(line.endswith((" ", "\t")) for line in index.splitlines())
    assert 'href="./"' in transformed["threats.html"], "the index link must be extensionless"


def test_every_static_stylesheet_is_shipped_once_and_svg_links_stay_svg() -> None:
    """The method map links ``map.css`` beside the shared sheet; both must survive
    as sibling files, not inline copies re-embedded on every page. And an
    unavailable link inside an ``<svg>`` became an HTML ``<span>``, which is not an
    SVG child -- the browser stopped painting around it and the treemap vanished."""
    pages = {
        "map.html": """<html><head><link rel="stylesheet" href="/static/driftless.css">
<link rel="stylesheet" href="/static/map.css"></head><body>
<svg viewBox="0 0 10 10"><a href="/portfolios/1/rollup"><title>P</title><rect/></a></svg>
<div class="map-filters"><input type="checkbox" class="map-filter"><button type="button" id="map-reset">Reset</button></div>
<a href="/portfolios/1/rollup">Rollup</a></body></html>""",
    }
    out = _load().transform_bundle(pages, anchor="2026-07-01", source="v0")["map.html"]
    assert 'class="map-filters"' not in out and "<button" not in out, (
        "dead JS-only controls exported"
    )
    assert "/static/" not in out, "a stylesheet link the static bundle cannot serve"
    assert "fill: #cb764b" not in out, "map.css was inlined instead of shipped as a sibling file"
    assert '<link rel="stylesheet" href="driftless.css">' in out
    assert '<link rel="stylesheet" href="map.css">' in out
    svg = re.search(r"<svg.*?</svg>", out, re.S)
    assert svg is not None and "<span" not in svg.group(0)
    assert '<g class="showcase-unavailable"><title>P</title><rect/></g>' in svg.group(0)
    assert '<span class="showcase-unavailable">Rollup</span>' in out


def test_the_showcase_carries_no_absolute_page_link_except_the_about_link(
    transformed_showcase: dict[str, str],
) -> None:
    """Every ``href="/..."`` in the published bundle is a browser dead end; the one
    way back to the site is an absolute ``https://`` link, not a root-relative one.
    ``src="/..."`` (there should be none left either, but that is a separate
    property) is not what this check is about."""
    stray = re.compile(r'href="/')
    for name, body in transformed_showcase.items():
        assert not stray.search(body), (
            f"{name} carries an absolute page link the static bundle cannot serve"
        )
        assert 'href="/static/' not in body, f"{name} links a stylesheet the bundle lacks"
        for svg in re.findall(r"<svg.*?</svg>", body, re.S):
            assert "<span" not in svg, f"{name} puts an HTML span inside an svg"


def test_write_bundle_is_whole_deterministic_and_refuses_an_unowned_directory(
    tmp_path: Path,
) -> None:
    demo = _load()
    out = tmp_path / "demo"
    out.mkdir()
    (out / "somebody-elses-file.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(SystemExit, match="not a showcase bundle"):
        demo.write_bundle(out, {"index.html": "one"}, "2026-07-01", "v0.2.0")

    clean = tmp_path / "clean"
    assert demo.write_bundle(clean, {"index.html": "one"}, "2026-07-01", "v0.2.0") == 1
    (clean / "stale.html").write_text("old", encoding="utf-8")
    assert demo.write_bundle(clean, {"index.html": "two"}, "2026-07-01", "v0.2.0") == 1
    assert not (clean / "stale.html").exists()
    assert (clean / "index.html").read_text(encoding="utf-8") == "two"
    manifest = json.loads((clean / "manifest.json").read_text(encoding="utf-8"))
    script = demo.SHOWCASE_SCRIPT.read_text(encoding="utf-8")
    stylesheets = demo.css_assets()
    expected_sha256 = {
        "index.html": hashlib.sha256(b"two").hexdigest(),
        "showcase-map.js": hashlib.sha256(script.encode("utf-8")).hexdigest(),
        **{
            name: hashlib.sha256(body.encode("utf-8")).hexdigest()
            for name, body in stylesheets.items()
        },
    }
    assert manifest == {
        "anchor": "2026-07-01",
        "files": sorted(["index.html", "showcase-map.js", *stylesheets]),
        "kind": "driftless-static-showcase",
        "pages": 1,
        "scripts": ["showcase-map.js"],
        "sha256": expected_sha256,
        "source": "v0.2.0",
        "stylesheets": sorted(stylesheets),
    }
    shipped = (clean / "showcase-map.js").read_text(encoding="utf-8")
    assert shipped == script
    for name, body in stylesheets.items():
        assert (clean / name).read_text(encoding="utf-8") == body, name


def test_write_bundle_never_writes_the_legacy_marker_file(tmp_path: Path) -> None:
    demo = _load()
    out = tmp_path / "demo"
    demo.write_bundle(out, {"index.html": "one"}, "2026-07-01", "v0.2.0")
    assert not (out / demo.MARKER).exists()


def test_write_bundle_guard_is_keyed_on_the_manifest_kind_not_the_marker_file(
    tmp_path: Path,
) -> None:
    """The clobber guard reads ``manifest.json``'s ``kind``, not a marker file's
    presence, so a bundle written before the marker was retired is still owned and a
    stray marker with no manifest is not."""
    demo = _load()

    unowned = tmp_path / "unowned"
    unowned.mkdir()
    (unowned / "somebody-elses-file.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(SystemExit, match="not a showcase bundle"):
        demo.write_bundle(unowned, {"index.html": "one"}, "2026-07-01", "v0.2.0")

    stale_marker_only = tmp_path / "stale-marker"
    stale_marker_only.mkdir()
    (stale_marker_only / demo.MARKER).write_text("old", encoding="utf-8")
    with pytest.raises(SystemExit, match="not a showcase bundle"):
        demo.write_bundle(stale_marker_only, {"index.html": "one"}, "2026-07-01", "v0.2.0")

    owned = tmp_path / "owned"
    owned.mkdir()
    (owned / "manifest.json").write_text(json.dumps({"kind": demo.KIND}), encoding="utf-8")
    (owned / demo.MARKER).write_text("old", encoding="utf-8")
    assert demo.write_bundle(owned, {"index.html": "one"}, "2026-07-01", "v0.2.0") == 1
    assert not (owned / demo.MARKER).exists(), "the legacy marker was not cleared as stale"


def test_write_bundle_ships_both_stylesheets_and_lists_them_in_the_manifest(
    tmp_path: Path,
) -> None:
    """The sibling files a rewritten ``<link>`` points at must actually exist, the
    same way ``showcase-map.js`` does for the one re-admitted script."""
    demo = _load()
    out = tmp_path / "demo"
    demo.write_bundle(out, {"index.html": "one"}, "2026-07-01", "v0.2.0")

    stylesheets = demo.css_assets()
    assert set(stylesheets) == {"driftless.css", "map.css", "print.css"}
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    for name, body in stylesheets.items():
        assert (out / name).read_text(encoding="utf-8") == body, name
        assert name in manifest["files"]
        assert manifest["sha256"][name] == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert set(manifest["stylesheets"]) == set(stylesheets)


def test_two_runs_of_write_bundle_are_byte_identical(tmp_path: Path) -> None:
    demo = _load()
    pages = {"index.html": "<html>one</html>\n", "threats.html": "<html>two</html>\n"}
    first = tmp_path / "first"
    second = tmp_path / "second"
    demo.write_bundle(first, pages, "2026-07-01", "v0.2.0")
    demo.write_bundle(second, pages, "2026-07-01", "v0.2.0")

    first_files = {p.name: p.read_bytes() for p in first.iterdir()}
    second_files = {p.name: p.read_bytes() for p in second.iterdir()}
    assert first_files == second_files


def test_the_showcase_carries_the_new_read_only_surfaces(
    transformed_showcase: dict[str, str],
) -> None:
    files = set(transformed_showcase)
    missing_globals = {f"{name}.html" for name in GLOBAL_PAGES} - files
    assert not missing_globals, f"missing global showcase pages: {missing_globals}"

    # ``flow`` is only ever exported for the one project the deep walkthrough tells,
    # unlike ``hub`` below (ships for every project), so it names that project's id.
    project_flow = next(name for name in files if re.fullmatch(r"projects-\d+-flow\.html", name))
    project_id = project_flow.split("-")[1]
    missing_project = {f"projects-{project_id}-{slug}.html" for slug in PROJECT_PAGES} - files
    assert not missing_project, f"missing project pages: {missing_project}"
    missing_assist = {f"projects-{project_id}-assist-{slug}.html" for slug in ASSIST_PAGES} - files
    assert not missing_assist, f"missing assist pages: {missing_assist}"

    # ``hub``/``status``/``wizard`` are the only project pages the dashboard itself
    # links to, so unlike the deep single-project walkthrough above they ship for
    # every project -- the count here is exactly the demo store's project count.
    hub_pages = [name for name in files if re.fullmatch(r"projects-\d+-hub\.html", name)]
    assert len(hub_pages) >= 2, "the dashboard links every project's hub, not just one"

    department_pages = [
        name for name in files if re.fullmatch(r"org-departments-\d+-assist\.html", name)
    ]
    assert len(department_pages) == 1, department_pages


def test_showcase_pages_carry_no_write_controls(transformed_showcase: dict[str, str]) -> None:
    for name, body in transformed_showcase.items():
        assert "<form" not in body, name
        assert 'href="/login' not in body, name


def test_every_internal_link_in_the_showcase_resolves_inside_the_bundle(
    transformed_showcase: dict[str, str],
) -> None:
    demo = _load()
    files = set(transformed_showcase)
    for name, body in transformed_showcase.items():
        for match in demo.HREF.finditer(body):
            href = match.group("url")
            if href.startswith(("http", "#", "/")) or href in demo.CSS_ASSET_NAMES:
                continue
            path, _, fragment = href.partition("#")
            candidate = "index.html" if path in ("", "./") else f"{path}.html"
            assert candidate in files, f"{name} links to {href!r}, missing from the bundle"
            if fragment:
                target = transformed_showcase[candidate]
                assert f'id="{fragment}"' in target, (
                    f"{name} links to {href!r}, but {candidate} has no id={fragment!r}"
                )


#: The three per-kind lists below the drawing (``method_map.html``'s ``kinds`` loop) — the
#: no-JS floor, where every node and every tie is readable with no script running. Named
#: rather than counted: the page may carry other ``<details>`` of its own (the "How to read
#: this page" block does), and a bare total would call that a regression.
NODE_KIND_LISTS = ("Processes", "Techniques", "Artifacts")
#: One ``<details>`` and the summary that opens it, however the export has set ``open``.
DETAILS_SUMMARY = re.compile(r"<details(?: open)?>\s*<summary>([^<]*)</summary>")


def _node_kind_lists(page: str) -> list[str]:
    """The ``NODE_KIND_LISTS`` summaries this page carries, in page order."""
    return [s for s in DETAILS_SUMMARY.findall(page) if s in NODE_KIND_LISTS]


def test_the_map_page_keeps_its_svg_fallback_after_scripts_are_stripped(
    transformed_showcase: dict[str, str],
) -> None:
    map_page = transformed_showcase["map.html"]
    assert "<svg" in map_page
    assert "/static/map.js" not in map_page
    assert _node_kind_lists(map_page) == list(NODE_KIND_LISTS), (
        "the no-JS floor lost a details list"
    )


#: The exported interaction layer is pinned by its bytes, not by its name: the export
#: re-admits exactly one script, so that one file may never quietly grow into something
#: else. Regenerate with `sha256sum bin/showcase-map.js` when the file is edited on
#: purpose, and read the diff before you do.
SHOWCASE_SCRIPT_SHA256 = (  # a content hash of a tracked file, not a credential
    "c6c4ef15ff686eadc8cc432c017693e6cd510597c15b0106791513bf1f83793b"  # pragma: allowlist secret
)

#: Nothing in the re-admitted script may reach the network, keep state, submit, or
#: evaluate a string as code.
FORBIDDEN_IN_SCRIPT = (
    "fetch(",
    "XMLHttpRequest",
    "WebSocket",
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "document.cookie",
    "eval(",
    "new Function",
    "import(",
    "<form",
    ".submit(",
    "window.location",
    "Worker(",
    "sendBeacon",
)


def test_the_export_re_admits_exactly_one_audited_read_only_script(
    transformed_showcase: dict[str, str],
) -> None:
    """Read-only must mean "cannot write", not "cannot interact". The export drops
    every script the app shipped and re-admits one audited file, on the map page
    only -- pinned by its bytes so it cannot silently become something else."""
    demo = _load()
    for name, body in transformed_showcase.items():
        if name in demo.MAP_PAGES:
            continue
        assert "<script" not in body, f"{name} carries a script the export did not audit"

    for name in demo.MAP_PAGES:
        map_page = transformed_showcase[name]
        assert map_page.count("<script") == 1, f"{name}: more than the one audited script survived"
        assert demo.MAP_SCRIPT_TAG in map_page

    source = demo.SHOWCASE_SCRIPT.read_text(encoding="utf-8")
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == SHOWCASE_SCRIPT_SHA256
    # Its own comments name what it may not do, so the scan reads the CODE.
    code = "\n".join(line.split("//")[0] for line in source.splitlines())
    for forbidden in FORBIDDEN_IN_SCRIPT:
        assert forbidden not in code, f"the audited script grew {forbidden!r}"
    assert "no fetch" in source, "the audited script lost the comment stating its limits"
    # It READS the address (the node another page asked it to pin) and never writes one:
    # assigning a location is in FORBIDDEN_IN_SCRIPT above and stays there.
    assert "location.hash" in code, "the audited script no longer opens on the pinned node"


_SVG_OPEN_TAG = re.compile(r"<svg\b[^>]*>", re.S)
_SVG_BLOCK = re.compile(r"<svg\b.*?</svg>", re.S)


def test_every_svg_in_the_bundle_is_labelled_or_hidden(
    transformed_showcase: dict[str, str],
) -> None:
    """Assistive tech may ignore an ``aria-label`` on an element with no ``role`` --
    every ``<svg>`` the showcase ships must either carry a role beside its
    ``aria-label`` or be pruned from the tree entirely (``aria-hidden="true"``).
    Which role depends on what it holds: ``role="img"`` prunes the subtree, so
    an SVG with a link inside (the treemap, the method map) is a named
    ``role="group"`` -- as ``img`` it was one image with interactive controls
    nested inside, which axe refuses (headlessmode #352, 2026-09-05). A chart
    with nothing to click is ``role="img"``."""
    offences = []
    for name, body in transformed_showcase.items():
        for block in _SVG_BLOCK.findall(body):
            tag = _SVG_OPEN_TAG.search(block).group(0)  # type: ignore[union-attr]
            if 'aria-hidden="true"' in tag or 'aria-label="' not in tag:
                continue
            want = "group" if re.search(r"<a\b", block) else "img"
            if f'role="{want}"' not in tag:
                offences.append(f'{name}: {tag[:120]} wants role="{want}"')
    assert not offences, "\n".join(offences)


def test_single_quoted_links_and_stylesheets_are_rewritten_too() -> None:
    """The templates are not pinned to one quote style; a single-quoted attribute is
    as real as a double-quoted one and must not ship untouched."""
    pages = {
        "index.html": """<!doctype html><html><head><title>Dashboard</title>
<link rel='stylesheet' href='/static/driftless.css'></head><body>
<nav><a href='/threats'>Threats</a><a href='/login'>Sign in</a></nav>
<p>Stable</p></body></html>""",
        "threats.html": """<!doctype html><html><head></head><body>
<a href="/">Dashboard</a></body></html>""",
    }
    transformed = _load().transform_bundle(pages, anchor="2026-07-01", source="v0.2.0")
    index = transformed["index.html"]
    assert "href='/login'" not in index and 'href="/login' not in index
    assert "href='/static/driftless.css'" not in index
    assert 'href="driftless.css"' in index
    assert 'href="threats"' in index


def test_a_fragment_link_survives_the_export_pointed_at_its_sibling_page() -> None:
    """``/techniques#family-cost`` is a real, resolvable link once exported: the file
    part must still match a captured page, and the fragment must ride along on the
    rewritten href rather than being folded into a filename that never exists."""
    pages = {
        "index.html": """<!doctype html><html><head></head><body>
<a href="/techniques#family-cost">Cost family</a>
<a href="/nope#missing">Dead family</a>
<a href="#stays-here">Same-page</a></body></html>""",
        "techniques.html": """<!doctype html><html><head></head><body>
<h2 id="family-cost">Cost</h2></body></html>""",
    }
    transformed = _load().transform_bundle(pages, anchor="2026-07-01", source="v0.2.0")
    index = transformed["index.html"]
    assert 'href="techniques#family-cost"' in index
    assert '<span class="showcase-unavailable">Dead family</span>' in index
    assert 'href="#stays-here"' in index


def test_no_template_nests_an_svg_inside_another(tmp_path: Path) -> None:
    """SVG_BLOCK matches non-greedily, so a nested ``<svg>`` would truncate at the
    inner close. Pinning the assumption that no template nests one is cheaper than
    balanced matching, and this test reddens the moment a template violates it."""
    templates = Path(__file__).resolve().parents[1] / "driftless" / "web" / "templates"
    for path in sorted(templates.glob("*.html")):
        depth = 0
        for tag in re.finditer(r"<svg\b|</svg>", path.read_text(encoding="utf-8")):
            depth += 1 if tag.group(0).startswith("<svg") else -1
            assert depth <= 1, f"{path.name} nests an <svg> inside another"


def test_the_zoom_controls_are_stripped(tmp_path) -> None:
    """The map's zoom group is four buttons and no script that answers them.

    ``showcase-map.js`` -- the one script the bundle ships -- carries no ``data-zoom``
    handler, so exported as-is the group is a Fit button that fits nothing, exactly the
    shape ``MAP_FILTERS`` exists to strip. It reached the bundle because the committed
    export predates the zoom controls (PR 450) by several releases; the first regen after
    v0.6.0 surfaced all four at once against headlessmode's inertness contract
    (``scripts/test_driftless_demo.py``: no ``<form`` or ``<button`` on any page).
    """
    pages = {
        "map.html": """<html><body>
<div class="map-zoom" role="group" aria-label="Zoom the map">
<button type="button" class="btn btn-secondary" data-zoom="fit">Fit</button>
<button type="button" class="btn btn-secondary" data-zoom="in" aria-label="Zoom in">+</button>
</div>
<svg viewBox="0 0 10 10"><rect/></svg></body></html>""",
    }
    out = _load().transform_bundle(pages, anchor="2026-07-01", source="v0")["map.html"]
    assert "map-zoom" not in out and "<button" not in out, "dead zoom controls exported"
    assert "data-zoom" not in out


def test_the_map_zoom_block_carries_no_nested_div() -> None:
    """MAP_ZOOM matches non-greedily up to the first ``</div>``, like MAP_FILTERS: it
    only strips the whole group because the group never nests a ``<div>`` itself."""
    template = (
        Path(__file__).resolve().parents[1] / "driftless" / "web" / "templates" / "method_map.html"
    )
    match = re.search(r'<div class="map-zoom"[^>]*>.*?</div>', template.read_text(), re.DOTALL)
    assert match is not None, "the zoom group moved or was renamed; MAP_ZOOM now strips nothing"
    assert "<div" not in match.group(0)[match.group(0).index(">") + 1 :]


def test_the_map_filters_block_carries_no_nested_div() -> None:
    """MAP_FILTERS matches non-greedily up to the first ``</div>``; it only strips the
    whole filter strip because that strip never nests a ``<div>`` itself."""
    template = (
        Path(__file__).resolve().parents[1] / "driftless" / "web" / "templates" / "method_map.html"
    )
    match = re.search(r'<div class="map-filters">.*?</div>', template.read_text(), re.DOTALL)
    assert match is not None
    assert "<div" not in match.group(0)[len('<div class="map-filters">') :]


def test_write_bundle_clears_a_stale_non_html_asset(tmp_path: Path) -> None:
    """A prior run's renamed or dropped asset (not ``*.html``) must not leak forward
    as an orphan file in the published bundle."""
    demo = _load()
    out = tmp_path / "demo"
    assert demo.write_bundle(out, {"index.html": "one"}, "2026-07-01", "v0.2.0") == 1
    (out / "old-asset.js").write_text("stale", encoding="utf-8")
    (out / "old-style.css").write_text("stale", encoding="utf-8")
    assert demo.write_bundle(out, {"index.html": "two"}, "2026-07-01", "v0.2.0") == 1
    assert not (out / "old-asset.js").exists()
    assert not (out / "old-style.css").exists()
    assert (out / "manifest.json").exists()


def test_default_source_uses_the_exact_tag_else_the_short_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    demo = _load()
    repo_root = tmp_path

    monkeypatch.setattr(demo, "_tag_matches_version", lambda root: True)
    assert demo._default_source(repo_root) == f"v{demo.__version__}"

    monkeypatch.setattr(demo, "_tag_matches_version", lambda root: False)
    monkeypatch.setattr(demo, "_short_sha", lambda root: "abc1234")
    assert demo._default_source(repo_root) == "abc1234"


def test_the_map_page_promises_only_what_the_static_bundle_delivers(
    transformed_showcase: dict[str, str],
) -> None:
    """The live page's own copy described filters and per-node pages the export
    strips; the exported copy describes what the exported page actually does."""
    map_page = transformed_showcase["map.html"]
    assert "once a filter narrows the map" not in map_page
    assert "Every shape links to its own page" not in map_page
    assert "Every shape opens its own summary below the map" in map_page
    assert "on hover and on keyboard focus" in map_page
    # Q17: process/technique/artifact detail pages DO ship in the export, so the
    # map's own copy may not claim otherwise.
    assert "no separate page per node" not in map_page
    assert "still links onward too" in map_page
    # A project wash is still a read of the live product, so the one link naming this
    # page's own file is the nav's -- the whole graph and a pinned node are pages now,
    # and name their own files (``map-all``) rather than reloading this one.
    assert map_page.count('href="map"') == 1, "a link that promises another view, reloading"
    assert '<a href="map" aria-current="page">' in map_page, "the honest one is the nav's"
    assert '<a href="map-all">show the whole graph</a>' in map_page, (
        "the whole graph is a page in this bundle now, so the copy must offer it"
    )
    # Was: no "… on the map" link at all, because every one of them flattened to this
    # same file. They now name the whole-graph page and the node they pin, which
    # test_every_on_the_map_link_in_the_bundle_names_the_node_it_pins checks in full.
    assert 'href="map-all#node-' in map_page
    # An "Open <node>" affordance only where the node's page was exported; none were.
    assert '<span class="showcase-unavailable">Open ' not in map_page


def test_the_notice_links_back_to_the_site_with_a_configurable_url() -> None:
    pages = {"index.html": "<html><head></head><body></body></html>"}
    transformed = _load().transform_bundle(pages, anchor="2026-07-01", source="v0")
    index = transformed["index.html"]
    assert (
        '<a href="https://headlessmode.com/driftless/">&larr; Back to headlessmode.com/driftless</a>'
        in index
    )
    assert "&middot; <strong>Fixed fictional demo</strong> &middot; as of 2026-07-01" in index

    custom = _load().transform_bundle(
        pages, anchor="2026-07-01", source="v0", site_url="https://example.test/x/"
    )["index.html"]
    assert 'href="https://example.test/x/"' in custom


def test_index_opens_as_a_landing_page_that_routes_into_the_demo(
    transformed_showcase: dict[str, str],
) -> None:
    """DS15: the front door explains what this fixed demo is -- with its own
    ``<h1>``, a project count read off the bundle itself (never typed), a link
    into the story project, and links into every Method page -- and only THEN
    shows the dashboard as a labelled sample screen, not as the page's subject."""
    demo = _load()
    index = transformed_showcase["index.html"]
    hub_pages = {
        name for name in transformed_showcase if re.fullmatch(r"projects-\d+-hub\.html", name)
    }
    assert f"{len(hub_pages)} seeded project" in index
    project_flow = next(
        name for name in transformed_showcase if re.fullmatch(r"projects-\d+-flow\.html", name)
    )
    project_id = project_flow.split("-")[1]
    hub = transformed_showcase[f"projects-{project_id}-hub.html"]
    story_name = demo.PROJECT_H1.search(hub).group("name")  # type: ignore[union-attr]
    assert story_name in index
    assert f'<a href="projects-{project_id}-hub">' in index, "the story project must be a link"
    assert index.index('<main id="main">') < index.index('<section class="showcase-intro"')
    assert index.index('<section class="showcase-intro"') < index.index(
        '<h2 class="showcase-sample-heading">'
    )
    assert "<h1>About this demo</h1>" in index
    assert "<h1>Dashboard</h1>" not in index, "the demo's own h1 must lead, not the sample's"
    assert '<h2 class="showcase-sample-heading">Dashboard</h2>' in index
    for slug in ("pmbok", "techniques", "methods", "artifacts", "glossary", "map"):
        assert f'<a href="{slug}">' in index, slug


def test_pages_with_an_inert_link_explain_it_once(transformed_showcase: dict[str, str]) -> None:
    """DS12/DS13: a page carrying any ``showcase-unavailable`` span says once why —
    never once per link."""
    for name, body in transformed_showcase.items():
        note_count = body.count('class="showcase-note"')
        if 'class="showcase-unavailable"' in body:
            assert note_count == 1, f"{name}: {note_count} explainer notes"
        else:
            assert note_count == 0, name
    assert "showcase-unavailable" in transformed_showcase["threats.html"]


def test_css_assets_lists_every_stylesheet_a_page_may_link() -> None:
    """Exposed as a module seam, the way ``SHOWCASE_SCRIPT`` is, so whoever writes
    the bundle can ship both files as siblings without this module hard-coding
    the write."""
    demo = _load()
    assets = demo.css_assets()
    assert set(assets) == set(demo.CSS_ASSET_NAMES) == {"driftless.css", "map.css", "print.css"}
    for name, content in assets.items():
        assert content, name
        assert "/*" not in content, f"{name} still carries a comment"


def test_a_fragment_the_collapsed_page_does_not_carry_is_dropped() -> None:
    """``/process-map?process=4.1#listing`` exports as the one ``process-map.html``:
    the per-process listing that carried ``id="listing"`` is not in the bundle, so
    the link lands on the page itself rather than on a fragment that goes nowhere."""
    pages = {
        "index.html": """<!doctype html><html><head></head><body>
<a href="/process-map?as_of=2026-07-01&process=4.1#listing">4.1</a>
<a href="/process-map#top">Top</a></body></html>""",
        "process-map.html": """<!doctype html><html><head></head><body>
<h1 id="top">Process map</h1></body></html>""",
    }
    index = _load().transform_bundle(pages, anchor="2026-07-01", source="v0")["index.html"]
    assert 'href="process-map">4.1</a>' in index
    assert 'href="process-map#top">Top</a>' in index


def test_the_whole_graph_ships_as_its_own_page_with_every_node_anchored(
    transformed_showcase: dict[str, str],
) -> None:
    """DS09/MP24: ``?view=all`` — the one read that draws every node and every tie — is a
    page of this bundle rather than a read of the live product, and every node in it is a
    link target. The anchor sits on that node's own entry in the lists below the drawing,
    the part of the page that needs no script at all; the lists are exported open for the
    same reason, a fragment inside a closed ``<details>`` being a target a reader with no
    JavaScript cannot see."""
    page = transformed_showcase["map-all.html"]
    assert 'data-slice="all"' in page, "map-all.html is not the whole-graph read"
    missing = [node.id for node in GRAPH.nodes if f'id="node-{node.id}"' not in page]
    assert not missing, f"{len(missing)} nodes carry no anchor to land on, e.g. {missing[:3]}"
    opened = [s for s in re.findall(r"<details open>\s*<summary>([^<]*)</summary>", page)]
    assert [s for s in opened if s in NODE_KIND_LISTS] == list(NODE_KIND_LISTS), (
        "a #node- link lands inside a collapsed list"
    )


def test_a_see_it_on_the_map_link_survives_the_export_pinned_on_its_own_node(
    transformed_showcase: dict[str, str],
) -> None:
    """DS17: a process or technique page's "See it on the map" link flattened to the
    overview file — which draws no technique and no artifact at all, and pins nothing —
    so the reader arrived at a map that had forgotten what they asked to see. It now
    names the whole-graph page and the node to open on."""
    process = GRAPH.by_kind("process")[0]
    process_page = transformed_showcase[f"pmbok-{process.id.partition(':')[2]}.html"]
    assert f'href="map-all#node-{process.id}">See it on the map</a>' in process_page

    technique = GRAPH.by_kind("technique")[0]
    slug = technique_slug(technique.id.partition(":")[2])
    technique_page = transformed_showcase[f"techniques-{slug}.html"]
    assert f'href="map-all#node-{technique.id}">See it on the map</a>' in technique_page


def test_every_on_the_map_link_in_the_bundle_names_the_node_it_pins(
    transformed_showcase: dict[str, str],
) -> None:
    """Both map pages carry one per node, twice over (the per-node panel and the list
    entry). Each was stripped on export as a link that reloaded the page it sat on;
    each now opens the whole graph on the node it names."""
    for name in ("map.html", "map-all.html"):
        found = re.findall(r'<a href="([^"]*)">[^<]* on the map</a>', transformed_showcase[name])
        assert found, f"vacuous: {name} carries no 'on the map' link at all"
        strays = sorted({href for href in found if not href.startswith("map-all#node-")})
        assert not strays, f"{name} links {strays}"
