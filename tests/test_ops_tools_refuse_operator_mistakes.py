"""The operator-run tools in ``bin/`` delete before they write — so what they refuse.

Not one of them is a pure generator: the snapshot tool clears ``*.html`` out of the
``--out`` it is pointed at, the sample-report tool clears the as-of subtree under its
own, and the changelog assembler unlinks every fragment once a release is stamped. All
three take the destination or the stamp from free-form command-line input, so the
interesting cases are not the happy paths but the mistyped ones — ``--out`` naming a
directory a person filled by hand, and a ``--date`` that is not a date. Each must leave
the files it did not make exactly where they were.

``normalize`` is pinned here for a different reason: the bundle tests compare one run
against another, so a ``normalize`` that returned the empty string would keep both of
them green while capturing nothing at all.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(name: str, script: str) -> Any:
    """Import one of the ``bin/`` scripts by path — they are commands, not a package."""
    spec = importlib.util.spec_from_file_location(name, REPO / "bin" / script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


snapshot = _load("driftless_snapshot_pages", "driftless-snapshot-pages.py")
samples = _load("driftless_sample_reports", "driftless-sample-reports.py")
changelog = _load("assemble_changelog", "assemble-changelog.py")


def test_the_sample_reports_refuse_an_out_directory_they_did_not_create(tmp_path: Path) -> None:
    out = tmp_path / "docs"
    out.mkdir()
    hand_written = out / "user-guide.md"
    hand_written.write_text("# written by a person\n", encoding="utf-8")

    with pytest.raises(SystemExit) as refusal:
        samples.claim(out)

    assert "did not write" in str(refusal.value)
    assert hand_written.read_text(encoding="utf-8") == "# written by a person\n"


def test_the_sample_reports_adopt_an_empty_directory_and_then_their_own(tmp_path: Path) -> None:
    out = tmp_path / "samples"
    out.mkdir()  # an operator's `mkdir -p`: empty, so there is nothing to destroy

    samples.claim(out)
    assert (out / samples.MARKER).is_file()
    (out / "2026-07-01").mkdir()  # the bundle a run leaves behind
    samples.claim(out)  # marked and non-empty: its own, so it is taken a second time
    assert (out / samples.MARKER).is_file()


def test_the_snapshot_refuses_an_out_directory_it_did_not_create(tmp_path: Path) -> None:
    out = tmp_path / "docs"
    out.mkdir()
    hand_written = out / "index.html"
    hand_written.write_text("<html>written by a person</html>", encoding="utf-8")

    with pytest.raises(SystemExit) as refusal:
        snapshot.write_bundle(out, {"index.html": "<html>generated</html>"})

    assert "did not write" in str(refusal.value)
    assert hand_written.read_text(encoding="utf-8") == "<html>written by a person</html>"


def test_the_snapshot_adopts_an_empty_directory_and_rewrites_its_own_bundle(
    tmp_path: Path,
) -> None:
    out = tmp_path / "bundle"
    out.mkdir()  # an operator's `mkdir -p`: empty, so there is nothing to destroy

    assert snapshot.write_bundle(out, {"a.html": "<a>", "b.html": "<b>"}) == 2
    assert (out / snapshot.MARKER).is_file()
    assert snapshot.write_bundle(out, {"a.html": "<a2>"}) == 1
    assert sorted(path.name for path in out.glob("*.html")) == ["a.html"]  # stale page cleared


def test_normalize_replaces_the_csrf_token_and_leaves_the_page_alone() -> None:
    html = '<p>before</p><input name="csrf_token" value="minted-this-render"><p>after</p>'

    assert snapshot.normalize(html) == html.replace("minted-this-render", snapshot.PLACEHOLDER)
    assert snapshot.normalize("<p>no form on this page</p>") == "<p>no form on this page</p>"


def _repo(tmp_path: Path) -> Path:
    """A throwaway checkout: one fragment and a changelog with an Unreleased section."""
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "changelog.d" / "27.fixed.md").write_text("- A fix.\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n", encoding="utf-8")
    return tmp_path


def test_a_release_date_that_is_not_a_date_is_refused_before_a_fragment_is_unlinked(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)

    with pytest.raises(SystemExit) as refusal:
        changelog.main(["--release", "9.9.9", "--date", "not-a-date"], root)

    assert refusal.value.code != 0
    assert (root / "changelog.d" / "27.fixed.md").is_file()
    assert "9.9.9" not in (root / "CHANGELOG.md").read_text(encoding="utf-8")


def test_a_changelog_with_no_unreleased_section_is_reported_not_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    (root / "CHANGELOG.md").write_text("# Changelog\n\n## [0.1.0]\n", encoding="utf-8")

    assert changelog.main(["--release", "9.9.9", "--date", "2026-07-27"], root) == 1
    assert "Unreleased" in capsys.readouterr().err
    assert (root / "changelog.d" / "27.fixed.md").is_file()


def test_a_good_release_still_stamps_the_day_and_folds_the_fragments_in(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    assert changelog.main(["--release", "9.9.9", "--date", "2026-07-27"], root) == 0

    assert "## [9.9.9] - 2026-07-27" in (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert not (root / "changelog.d" / "27.fixed.md").exists()
