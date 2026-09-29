"""Contract tests for ``bin/assemble-changelog.py`` — the changelog-fragment folder.

The last test is the live gate the ``changelog.d/README.md`` promises: a fragment
with a malformed name or an unknown type turns the suite red, so it cannot
silently vanish at release time.
"""

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "assemble_changelog", _REPO / "bin" / "assemble-changelog.py"
)
assert _SPEC is not None and _SPEC.loader is not None
ac = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ac)

CHANGELOG = (
    "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- Old unreleased line.\n"
    "\n## [0.1.0]\n\n- The first release.\n"
)


def _fragment(name: str, body: str, tmp_path: Path) -> object:
    sort_key, fragment_type = ac.parse_fragment_name(name)
    return ac.Fragment(sort_key, fragment_type, body, tmp_path / name)


def test_fragment_names_parse_and_unknown_types_are_refused() -> None:
    assert ac.parse_fragment_name("27.fixed.md") == ((0, 27), "fixed")
    assert ac.parse_fragment_name("my-slug.docs.md") == ((1, "my-slug"), "docs")
    with pytest.raises(ValueError, match="unknown type"):
        ac.parse_fragment_name("28.typo.md")
    with pytest.raises(ValueError, match="expected <id>"):
        ac.parse_fragment_name("notes.md")


def test_fragments_fold_under_their_headings_and_history_survives(tmp_path: Path) -> None:
    fragments = [
        _fragment("30.fixed.md", "- A fix.", tmp_path),
        _fragment("29.added.md", "- A feature.", tmp_path),
    ]
    out = ac.assemble_unreleased(CHANGELOG, sorted(fragments, key=lambda f: f.sort_key))

    added = out.index("### Added\n- Old unreleased line.\n- A feature.")
    fixed = out.index("### Fixed\n- A fix.")
    assert added < fixed  # section order is Keep-a-Changelog order, appends keep existing lines
    assert out.endswith("## [0.1.0]\n\n- The first release.\n")  # released history untouched


def test_release_stamps_the_version_and_reopens_unreleased(tmp_path: Path) -> None:
    out = ac.render_release(
        CHANGELOG, [_fragment("31.security.md", "- A patch.", tmp_path)], "0.2.0", "2026-07-27"
    )

    assert "## [Unreleased]\n\n## [0.2.0] - 2026-07-27\n" in out
    assert "### Security\n- A patch." in out


def test_every_live_fragment_in_changelog_d_is_well_formed() -> None:
    fragments = ac.read_fragments(_REPO / "changelog.d")  # raises on a malformed name
    for fragment in fragments:
        assert fragment.body.startswith("- "), f"{fragment.path.name}: body must be a list item"


# (what the body contains, why it is prose and not markup) — every one of these has to
# survive, or the check costs more than the tags it refuses.
PROSE = (
    ("- A bullet with `<content>` in a code span.", "a tag quoted as an example"),
    ("- The release publishes `sops-v<version>.checksums.txt`.", "a placeholder in code"),
    ("- Read <https://example.com/spec> for the shape.", "an autolinked URL"),
    ("- Mail <nobody@example.com> about it.", "an autolinked address"),
    ("- A [linked page](https://example.com) and *emphasis*.", "ordinary markdown"),
    ("- Refused when `limit` > 100 and offset < 0.", "comparisons, not a tag"),
)


@pytest.mark.parametrize(("body", "why"), PROSE)
def test_a_fragment_of_ordinary_markdown_is_accepted(body: str, why: str) -> None:
    ac.check_fragment_body(body, "40.fixed.md")  # raises if it disagrees; that is the test


@pytest.mark.parametrize(
    "body",
    [
        "- A real bullet.\n</content>\n</invoke>",  # the exact pair that reached v0.1.0
        "- A bullet.\n<function_calls>",
        "- A bullet with <!-- an html comment -->.",
        "- A bullet <b>shouting</b> in markup.",
    ],
)
def test_a_fragment_carrying_markup_is_refused(body: str) -> None:
    with pytest.raises(ValueError, match="markup"):
        ac.check_fragment_body(body, "41.fixed.md")


def test_the_folder_refuses_the_fragment_rather_than_folding_it(tmp_path: Path) -> None:
    """The refusal has to happen where every caller passes — preview, ``--check`` and
    ``--release`` all read fragments — so no path folds markup into CHANGELOG.md."""
    (tmp_path / "42.fixed.md").write_text("- A bullet.\n</content>\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"42\.fixed\.md.*markup"):
        ac.read_fragments(tmp_path)


def test_release_refuses_a_section_over_githubs_release_body_limit(tmp_path: Path) -> None:
    huge = _fragment("50.added.md", "- " + ("x" * 130_000), tmp_path)
    with pytest.raises(ValueError, match=r"130,0\d\d bytes"):
        ac.render_release(CHANGELOG, [huge], "0.3.0", "2026-07-28")


def test_release_allow_oversize_bypasses_the_size_check(tmp_path: Path) -> None:
    huge = _fragment("50.added.md", "- " + ("x" * 130_000), tmp_path)
    out = ac.render_release(CHANGELOG, [huge], "0.3.0", "2026-07-28", allow_oversize=True)
    assert "## [0.3.0] - 2026-07-28" in out


def test_release_flag_warns_and_exits_nonzero_when_oversize(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "changelog.d" / "50.added.md").write_text("- " + ("x" * 130_000), encoding="utf-8")
    assert ac.main(["--release", "0.3.0", "--date", "2026-07-28"], root=tmp_path) == 1
    err = capsys.readouterr().err
    assert "bytes" in err and "0.3.0" in err
    assert (tmp_path / "changelog.d" / "50.added.md").exists()  # nothing unlinked on refusal
    assert "0.3.0" not in (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")


def test_release_flag_allow_oversize_succeeds(tmp_path: Path) -> None:
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "changelog.d" / "50.added.md").write_text("- " + ("x" * 130_000), encoding="utf-8")
    assert (
        ac.main(["--release", "0.3.0", "--date", "2026-07-28", "--allow-oversize"], root=tmp_path)
        == 0
    )
    assert "## [0.3.0] - 2026-07-28" in (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")


def test_check_reports_the_offending_fragment_and_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--check`` is what CI and a contributor run; it names the file and the tag."""
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "changelog.d" / "43.fixed.md").write_text("- A bullet.\n</invoke>\n")
    assert ac.main(["--check"], root=tmp_path) == 1
    assert "</invoke>" in capsys.readouterr().err
