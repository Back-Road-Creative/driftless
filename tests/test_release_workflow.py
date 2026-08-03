"""Contract tests for ``.github/workflows/release.yml`` — the tag → release path.

``v0.1.0`` was tagged on 2026-07-31 and no GitHub release object ever appeared:
every workflow here answered a pull request, a schedule or a dispatch, so a
pushed tag started nothing and publishing stayed a human step nobody did. The
notes CHANGELOG.md already held reached no reader.

These tests run the workflow's extraction step the way the runner does — the
shell body is read out of the YAML and executed against a fixture checkout —
including the case that MUST fail: a tag whose version has no dated section. A
release published with no notes looks answered, which is worse than one that is
visibly missing, so that failure is the property under test.
"""

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
NOTES_STEP = "Release notes for this tag from CHANGELOG.md"
PUBLISH_STEP = "Publish the GitHub release"
NOTES_FILE = '"$RUNNER_TEMP/release-notes.md"'
DATED_VERSION = re.compile(r"^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$", re.M)

FIXTURE = (
    "# Changelog\n\n"
    "## [Unreleased]\n\n### Added\n\n- Still in flight.\n\n"
    "## [9.9.9] - 2026-08-02\n\n### Security\n\n- The section this tag ships.\n\n"
    "## [9.9.8] - 2026-01-01\n\n- The release before it.\n"
)
EMPTY_SECTION = "# Changelog\n\n## [9.9.9] - 2026-08-02\n\n## [9.9.8] - 2026-01-01\n\n- Older.\n"


def _step_script(step_name: str) -> str:
    """The dedented shell body of the ``run:`` block belonging to ``step_name``."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == f"- name: {step_name}")
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    indent = len(lines[run + 1]) - len(lines[run + 1].lstrip())
    body: list[str] = []
    for line in lines[run + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) < indent:
            break
        body.append(line[indent:])
    return "\n".join(body)


def _extract(tmp_path: Path, tag: str, changelog: str) -> subprocess.CompletedProcess[str]:
    """Run the notes step as the runner runs it, over a checkout holding ``changelog``."""
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir(exist_ok=True)
    return subprocess.run(
        ["bash", "-c", _step_script(NOTES_STEP)],
        cwd=tmp_path,
        env={**os.environ, "TAG": tag, "RUNNER_TEMP": str(runner_temp)},
        capture_output=True,
        text=True,
    )


def test_a_pushed_version_tag_starts_it_and_it_asks_for_the_one_write_it_needs() -> None:
    """Tag-push trigger, read-only by default, one job-scoped write, no added secret."""
    assert WORKFLOW.exists(), "a tag that publishes nothing is how v0.1.0 got no release"
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "on:\n  push:\n    tags:\n" in text, "a pushed tag is the trigger, not a dispatch"
    assert "- 'v[0-9]+.[0-9]+.[0-9]+'" in text, "the repo's tag shape is v0.1.0"
    assert "permissions:\n  contents: read\n" in text, "the token starts read-only, as elsewhere"
    assert "      contents: write\n" in text, "creating a release is the one write, job-scoped"

    secrets = set(re.findall(r"secrets\.(\w+)", text))
    assert secrets <= {"GITHUB_TOKEN"}, f"no secret is added; the workflow's own token: {secrets}"
    uses = re.findall(r"uses: (\S+)", text)
    assert uses and all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", u) for u in uses), (
        f"actions are pinned to a commit SHA here, never a movable tag: {uses}"
    )


def test_the_notes_are_the_changelog_section_the_tag_names(tmp_path: Path) -> None:
    """The dated section for that version, and nothing above or below it."""
    done = _extract(tmp_path, "v9.9.9", FIXTURE)

    assert done.returncode == 0, done.stderr
    notes = (tmp_path / "runner-temp" / "release-notes.md").read_text(encoding="utf-8")
    assert "- The section this tag ships." in notes
    assert "Still in flight" not in notes, "Unreleased is not shipped"
    assert "The release before it" not in notes, "the section stops at the next heading"


def test_a_tag_with_no_section_fails_instead_of_publishing_an_empty_release(
    tmp_path: Path,
) -> None:
    """The failure that matters: no notes means no release, loudly."""
    done = _extract(tmp_path, "v9.9.7", FIXTURE)

    assert done.returncode != 0, "an unstamped version must not reach `gh release create`"
    assert "9.9.7" in done.stderr, done.stderr
    assert not (tmp_path / "runner-temp" / "release-notes.md").exists(), (
        "no notes file at all, so a later step cannot publish an empty one"
    )


def test_a_stamped_but_empty_section_fails_too(tmp_path: Path) -> None:
    """A heading with nothing under it is the same empty release by another route."""
    done = _extract(tmp_path, "v9.9.9", EMPTY_SECTION)

    assert done.returncode != 0 and "9.9.9" in done.stderr, done.stderr
    assert not (tmp_path / "runner-temp" / "release-notes.md").exists()


def test_the_shipped_changelog_extracts_for_its_newest_release(tmp_path: Path) -> None:
    """Run against the real CHANGELOG.md: the file the workflow reads is the file we ship."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    newest = DATED_VERSION.search(changelog)
    assert newest is not None, "CHANGELOG.md has no dated version section to release from"

    done = _extract(tmp_path, f"v{newest.group(1)}", changelog)

    assert done.returncode == 0, done.stderr
    assert (tmp_path / "runner-temp" / "release-notes.md").read_text(encoding="utf-8").strip()


def test_the_release_is_created_from_the_file_the_extraction_wrote() -> None:
    """Both steps name the same path, and the tag must already exist on the remote."""
    assert NOTES_FILE in _step_script(NOTES_STEP)
    publish = _step_script(PUBLISH_STEP)
    assert "gh release create" in publish, "the release object is what a tag reader looks for"
    assert f"--notes-file {NOTES_FILE}" in publish, "publish the extracted notes, not a summary"
    assert "--verify-tag" in publish, "refuse to invent a tag the remote does not have"
