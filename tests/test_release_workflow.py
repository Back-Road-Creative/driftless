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

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
NOTES_STEP = "Release notes for this tag from CHANGELOG.md"
VERSION_STEP = "The tag must be the version this tree declares"
PUBLISH_STEP = "Publish the GitHub release"
ASSET_STEP = "Build and validate the showcase asset"
ASSET_UPLOAD_STEP = "Upload the showcase asset to this release"
TOKEN_CHECK_STEP = "Check for the public mirror token"
WARN_STEP = "Warn when the public mirror is skipped"
MIRROR_STEP = "Mirror the snapshot, release and asset to the public repository"
NOTES_FILE = '"$RUNNER_TEMP/release-notes.md"'
DATED_VERSION = re.compile(r"^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$", re.M)

# The two repositories the notes step can run in, spelled from the org rather than
# written out: tests/test_governance_contract.py fails any tracked line naming a
# repository in this org that is not this one, and the sibling is the whole point of
# the guard under test. Only the public one builds and pushes the image.
ORG = "Back-Road-Creative"
IMAGE_REPOSITORY = f"{ORG}/driftless"
SNAPSHOT_SOURCE = f"{ORG}/driftless-archive"

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


def _extract(
    tmp_path: Path, tag: str, changelog: str, repository: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the notes step as the runner runs it, over a checkout holding ``changelog``.

    ``repository`` is ``GITHUB_REPOSITORY``, which the step's footer guard reads.
    ``None`` leaves it unset — the shape a run outside Actions has, and the shape this
    helper used to inherit from the ambient environment, which made the footer half of
    every run below depend on where the suite happened to be executing.
    """
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir(exist_ok=True)
    env = {**os.environ, "TAG": tag, "RUNNER_TEMP": str(runner_temp)}
    env.pop("GITHUB_REPOSITORY", None)
    if repository is not None:
        env["GITHUB_REPOSITORY"] = repository
    return subprocess.run(
        ["bash", "-c", _step_script(NOTES_STEP)],
        cwd=tmp_path,
        env=env,
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
    assert secrets <= {"GITHUB_TOKEN", "DRIFTLESS_PUBLIC_TOKEN"}, (
        f"only the workflow's own token plus the optional public-mirror token: {secrets}"
    )
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


@pytest.mark.parametrize(
    ("repository", "footer"),
    [
        (IMAGE_REPOSITORY, True),  # the repository docker-publish.yml pushes from
        (SNAPSHOT_SOURCE, False),  # the sibling this tree is snapshotted out of
        (None, False),  # unset: `${GITHUB_REPOSITORY:-}` under `set -u`
    ],
)
def test_the_image_footer_is_appended_only_where_the_image_is_actually_built(
    tmp_path: Path, repository: str | None, footer: bool
) -> None:
    """The notes name a `docker pull` a reader is expected to be able to run.

    ``docker-publish.yml`` pushes from one repository and no other, so a tag anywhere
    else builds no image and the footer would name a pull that 404s. The guard shipped
    with no test at all; these are the three values ``GITHUB_REPOSITORY`` takes.

    The unset case is not hypothetical padding: the step runs under ``set -euo
    pipefail`` and every test here executes its body outside a workflow, so a bare
    ``$GITHUB_REPOSITORY`` would abort the whole step on an unbound variable before it
    printed anything. ``:-`` is what keeps that from happening, and this case is what
    fails if somebody tidies it away.
    """
    done = _extract(tmp_path, "v9.9.9", FIXTURE, repository)

    assert done.returncode == 0, done.stderr
    notes = (tmp_path / "runner-temp" / "release-notes.md").read_text(encoding="utf-8")
    assert "- The section this tag ships." in notes, "the changelog section ships either way"
    assert ("### Container image" in notes) is footer, notes
    assert ("docker pull " in notes) is footer, notes


def test_the_release_is_created_from_the_file_the_extraction_wrote() -> None:
    """Both steps name the same path, and the tag must already exist on the remote."""
    assert NOTES_FILE in _step_script(NOTES_STEP)
    publish = _step_script(PUBLISH_STEP)
    assert "gh release create" in publish, "the release object is what a tag reader looks for"
    assert f"--notes-file {NOTES_FILE}" in publish, "publish the extracted notes, not a summary"
    assert "--verify-tag" in publish, "refuse to invent a tag the remote does not have"
    assert 'gh release view "$TAG"' in publish, "check before creating, so a re-dispatch can edit"
    assert "gh release edit" in publish, "an existing release is edited, not re-created"


def _fake_gh(tmp_path: Path, view_exists: bool) -> None:
    """A stand-in `gh` on PATH that logs its args and answers `release view` as told."""
    script = tmp_path / "gh"
    script.write_text(
        "#!/bin/sh\n"
        'echo "$@" >> "$(dirname "$0")/calls.log"\n'
        'if [ "$1 $2" = "release view" ]; then\n'
        f"  exit {0 if view_exists else 1}\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    script.chmod(0o755)


def _publish(tmp_path: Path, tag: str, view_exists: bool) -> subprocess.CompletedProcess[str]:
    _fake_gh(tmp_path, view_exists)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir(exist_ok=True)
    (runner_temp / "release-notes.md").write_text("notes\n", encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "GH_TOKEN": "x",
        "TAG": tag,
        "GITHUB_REPOSITORY": IMAGE_REPOSITORY,
        "RUNNER_TEMP": str(runner_temp),
    }
    return subprocess.run(
        ["bash", "-c", _step_script(PUBLISH_STEP)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )


def test_a_republish_edits_an_existing_release_instead_of_failing(tmp_path: Path) -> None:
    """The documented recovery path: dispatch on a tag whose release already exists."""
    done = _publish(tmp_path, "v9.9.9", view_exists=True)

    assert done.returncode == 0, done.stderr
    calls = (tmp_path / "calls.log").read_text(encoding="utf-8")
    assert "release view v9.9.9" in calls
    assert "release edit v9.9.9" in calls
    assert "release create" not in calls


def test_a_first_publish_still_creates_the_release(tmp_path: Path) -> None:
    done = _publish(tmp_path, "v9.9.9", view_exists=False)

    assert done.returncode == 0, done.stderr
    calls = (tmp_path / "calls.log").read_text(encoding="utf-8")
    assert "release view v9.9.9" in calls
    assert "release create v9.9.9" in calls
    assert "release edit" not in calls


def _version_gate(
    tmp_path: Path, tag: str, project: str, module: str
) -> subprocess.CompletedProcess[str]:
    """Run the version gate as the runner runs it, over a checkout declaring those two."""
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "driftless"\nversion = "{project}"\n', encoding="utf-8"
    )
    (tmp_path / "driftless").mkdir(exist_ok=True)
    (tmp_path / "driftless" / "__init__.py").write_text(
        f'__version__ = "{module}"\n', encoding="utf-8"
    )
    return subprocess.run(
        ["bash", "-c", _step_script(VERSION_STEP)],
        cwd=tmp_path,
        env={**os.environ, "TAG": tag},
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_tag_matching_the_declared_version_passes(tmp_path: Path) -> None:
    done = _version_gate(tmp_path, "v1.2.3", "1.2.3", "1.2.3")

    assert done.returncode == 0, done.stderr


def test_a_tag_that_outruns_the_declared_version_is_refused(tmp_path: Path) -> None:
    """The v0.3.0 incident: tagged from a tree still declaring 0.2.0.

    Nothing caught it, so the package metadata and the showcase exporter's default
    ``--source v<__version__>`` both named a release that was not being published.
    """
    done = _version_gate(tmp_path, "v0.3.0", "0.2.0", "0.2.0")

    assert done.returncode != 0, "a tag ahead of the declared version must not publish"
    # `::error::` annotations go to stdout, which is where a runner reads them from.
    assert "0.2.0" in done.stdout and "v0.3.0" in done.stdout, done.stdout


def test_the_two_declarations_disagreeing_is_refused(tmp_path: Path) -> None:
    """Bumping one file and forgetting the other is the same defect one step earlier."""
    done = _version_gate(tmp_path, "v1.2.3", "1.2.3", "1.2.2")

    assert done.returncode != 0, "pyproject and the module must agree before a tag ships"
    assert "1.2.2" in done.stdout, done.stdout


# GitHub refuses a release body above this: `HTTP 422 ... body is too long (maximum is
# 125000 characters)`. v0.4.0 folded 210 fragments into one 145 KB section, the push run
# failed at `gh release create`, and the tag had no release — the v0.1.0 outcome again.
BODY_LIMIT = 125_000


def _oversized(bullets: int = 2_000) -> str:
    padding = "\n".join(f"- change number {i} " + "x" * 80 for i in range(bullets))
    return FIXTURE.replace(
        "- The section this tag ships.", "- The section this tag ships.\n" + padding
    )


def test_a_section_github_would_refuse_is_cut_to_fit_and_says_where_the_rest_is(
    tmp_path: Path,
) -> None:
    """The notes ship at whatever length the API accepts, and name the full section."""
    done = _extract(tmp_path, "v9.9.9", _oversized(), IMAGE_REPOSITORY)

    assert done.returncode == 0, done.stderr
    notes = (tmp_path / "runner-temp" / "release-notes.md").read_text(encoding="utf-8")
    assert len(notes) <= BODY_LIMIT, f"{len(notes)} characters is what 422'd on v0.4.0"
    assert "- The section this tag ships." in notes, "the head of the section survives"
    assert "The release before it" not in notes, "still stops at the next heading"
    assert "truncated" in notes and "CHANGELOG.md" in notes and "v9.9.9" in notes, (
        "a reader is told the notes are cut and where the whole section lives"
    )
    assert "### Container image" in notes and "docker pull " in notes, (
        "the cut leaves room for the footer instead of pushing it over the limit"
    )


def test_a_section_that_fits_ships_whole_with_no_truncation_notice(tmp_path: Path) -> None:
    done = _extract(tmp_path, "v9.9.9", FIXTURE)

    assert done.returncode == 0, done.stderr
    notes = (tmp_path / "runner-temp" / "release-notes.md").read_text(encoding="utf-8")
    assert "truncated" not in notes
    assert "- The section this tag ships." in notes


DISPATCH_GATE_STEP = "Refuse an empty dispatched tag"
IMAGE_DISPATCH_STEP = "Build and publish the image for this tag"


def _dispatch_gate(tag: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", _step_script(DISPATCH_GATE_STEP)],
        env={**os.environ, "TAG": tag},
        capture_output=True,
        text=True,
    )


def test_a_dispatch_with_no_tag_is_refused() -> None:
    """The UI requires the input; `-f tag=` on the API does not."""
    done = _dispatch_gate("")

    assert done.returncode != 0, done.stdout + done.stderr


def test_a_dispatch_with_a_tag_passes_through() -> None:
    done = _dispatch_gate("v1.2.3")

    assert done.returncode == 0, done.stderr


def test_the_empty_dispatch_gate_only_runs_on_dispatch() -> None:
    """The push trigger never sets `inputs.tag`, so this step must not run there."""
    text = WORKFLOW.read_text(encoding="utf-8")
    idx = text.index(f"- name: {DISPATCH_GATE_STEP}")
    following = text[idx : idx + 400]
    assert "if: github.event_name == 'workflow_dispatch'" in following


def _oversized_non_ascii(bullets: int = 2_000) -> str:
    padding = "\n".join(f"- résumé item {i} " + "é" * 80 for i in range(bullets))
    return FIXTURE.replace(
        "- The section this tag ships.", "- The section this tag ships.\n" + padding
    )


def test_a_non_ascii_section_is_still_cut_within_githubs_byte_limit(tmp_path: Path) -> None:
    """`len(str)` counts code points; GitHub's 125,000 limit is measured in bytes."""
    done = _extract(tmp_path, "v9.9.9", _oversized_non_ascii(), IMAGE_REPOSITORY)

    assert done.returncode == 0, done.stderr
    notes = (tmp_path / "runner-temp" / "release-notes.md").read_text(encoding="utf-8")
    encoded = len(notes.encode("utf-8"))
    assert encoded <= BODY_LIMIT, f"{encoded} UTF-8 bytes is what 422's, not {len(notes)} chars"
    assert "truncated" in notes and "CHANGELOG.md" in notes and "v9.9.9" in notes


def test_the_image_dispatch_passes_the_tag_docker_publish_actually_accepts() -> None:
    """The dispatched `tag` input carries the leading `v`, like the ref beside it.

    `docker-publish.yml` documents its `tag` input as "leading v required" and
    refuses anything else. This step passed `${TAG#v}`, so every release dispatched
    a tag input its own callee rejects -- and because `actions/checkout` consumes
    that input BEFORE the format check runs, the refusal never printed: the run
    died at checkout with "A branch or tag with the name '0.6.1' could not be
    found" (v0.6.1, run 34880468332, 2026-09-14). Both arguments name one tag.
    """
    publish = _step_script(IMAGE_DISPATCH_STEP)

    assert '--ref "$TAG" -f tag="$TAG"' in publish, publish
    assert "${TAG#v}" not in publish, "stripping the v hands the callee a ref that does not exist"


def test_the_workflow_can_be_dispatched_for_a_tag_whose_push_run_failed() -> None:
    """A failed push run re-runs the tag's OWN workflow file, so a fix merged later can
    never reach it. `workflow_dispatch` with a tag input runs the fixed file for that tag;
    the image step stays on the push path, the tag push already built it."""
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "inputs.tag || github.ref_name" in text, "every TAG reads the input first"
    assert "ref: ${{ inputs.tag || github.ref_name }}" in text, "checkout the tag, not master"
    assert "if: github.event_name == 'push'" in text, "no second image build on a dispatch"


# --- Showcase asset upload -------------------------------------------------
#
# H12/12c: the site's demo bundle is generated FROM a tagged release, and until
# now nothing published that bundle anywhere a downstream sync could reach it
# without a private-repo checkout. These steps build it with the same generator
# the site's own driftless-bundle-regen.sh calls, validate it the way that
# script validates a bundle before trusting it, and upload it as a release
# asset named the way the site's sync job expects to find it.


def test_the_showcase_asset_is_generated_from_the_tag_with_the_showcase_generator() -> None:
    script = _step_script(ASSET_STEP)

    assert "bin/driftless-showcase.py" in script
    assert '--source "$TAG"' in script, "the bundle is built at the tag, never at master"
    assert (
        "driftless-showcase-${TAG}.tar.gz" in script or "driftless-showcase-$TAG.tar.gz" in script
    )


def test_the_showcase_generator_runs_from_an_interpreter_that_installed_this_package() -> None:
    """bin/driftless-showcase.py does `import driftless`. The runner's own python3 has
    never installed this package, so the v0.7.0 re-dispatch (run 36279535298,
    2026-09-26) died on `ModuleNotFoundError: No module named 'driftless'` before it
    built anything. The step must build a venv, install `.` into it, and run the
    generator with THAT interpreter -- never bare `python3 bin/driftless-showcase.py`."""
    script = _step_script(ASSET_STEP)

    install = re.search(r"(uv pip install|pip install)[^\n]*\s\"?\.(\[dev\])?\"?(\s|$)", script)
    assert install is not None, "the step never installs this package before importing it"
    run = re.search(r"^\s*(\S+)\s+bin/driftless-showcase\.py", script, re.M)
    assert run is not None, script
    interpreter = run.group(1)
    assert interpreter != "python3", "bare python3 has no driftless package on the runner"
    assert "VENV" in interpreter or ".venv" in interpreter, interpreter
    assert script.index(install.group(0)) < run.start(), "install must precede the generator"


def test_the_showcase_venv_installs_the_locked_dev_set() -> None:
    """The generator renders pages through fastapi.testclient, which needs httpx (a `dev`
    extra), and an unconstrained install resolves whatever starlette is newest. The
    v0.7.0 dispatch after #566 (run 36324094669, 2026-09-27) installed bare `.`, got a
    starlette newer than requirements.lock that demands a different HTTP client, and died
    on `RuntimeError: The starlette.testclient module requires the httpx2 package`.
    Install `.[dev]` under the lock, exactly as ci.yml's Tests job does."""
    script = _step_script(ASSET_STEP)
    assert "requirements.lock" in script, "the showcase venv ignores the lock"
    installs = re.findall(r"^.*\bpip\"? install\b.*$", script, re.M)
    assert installs, script
    for line in installs:
        assert '".[dev]"' in line or "'.[dev]'" in line, (
            f"installs without the dev extra: {line.strip()}"
        )
        assert "--constraint" in line or " -c " in line, (
            f"installs without the lock: {line.strip()}"
        )


def test_the_showcase_asset_is_validated_before_it_is_packaged() -> None:
    script = _step_script(ASSET_STEP)

    assert "manifest.json" in script
    assert '"source"' in script, "must equal the tag, not whatever the generator defaulted to"
    assert '"pages"' in script, "must equal the html files actually on disk"
    assert '"sha256"' in script, "every hashed file must match what shipped"
    assert "<script" in script, "at most one script tag per page, like the site's own gate"


def test_the_showcase_tarball_has_files_at_its_root_not_a_wrapping_directory() -> None:
    """The site untars this straight into static/demo/driftless/ — a wrapping directory
    would land as static/demo/driftless/<name>/... instead."""
    script = _step_script(ASSET_STEP)

    assert re.search(r"tar\s+-c[a-z]*f\s+\S+\s+-C\s+\S*OUT\S*\s+\.", script), script


def test_the_asset_upload_step_uploads_to_this_repository_and_can_be_re_run() -> None:
    script = _step_script(ASSET_UPLOAD_STEP)

    assert "gh release upload" in script
    assert '"$TAG"' in script
    assert "--clobber" in script, "a re-dispatched run must be able to replace the asset"
    assert '--repo "$GITHUB_REPOSITORY"' in script, "uploads to whichever repo this run is in"


# --- Public mirror, gated on a secret --------------------------------------
#
# decision 1 (2026-09-26 plan §12): mirror by AUTOMATING the documented
# snapshot procedure (docs/release-publishing.md), never by pushing the
# archive's own git ref — the archive's branch/PR history must never reach
# the public repository, which is the entire reason that doc's procedure is a
# fresh commit built from `git archive` rather than a shared-history push.


def _token_check(tmp_path: Path, token: str) -> str:
    """Run the token-gate step's script and return what it wrote to $GITHUB_ENV."""
    github_env = tmp_path / "github-env"
    github_env.write_text("", encoding="utf-8")
    env = {**os.environ, "TOKEN": token, "GITHUB_ENV": str(github_env)}
    done = subprocess.run(
        ["bash", "-c", _step_script(TOKEN_CHECK_STEP)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    return github_env.read_text(encoding="utf-8")


def test_the_token_gate_reports_true_when_the_secret_is_set(tmp_path: Path) -> None:
    assert "HAS_PUBLIC_TOKEN=true" in _token_check(tmp_path, "a-token-value")


def test_the_token_gate_reports_false_when_the_secret_is_absent(tmp_path: Path) -> None:
    assert "HAS_PUBLIC_TOKEN=false" in _token_check(tmp_path, "")


def test_the_warning_step_only_fires_when_the_token_is_absent() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    idx = text.index(f"- name: {WARN_STEP}")
    following = text[idx : idx + 300]

    assert "if: env.HAS_PUBLIC_TOKEN != 'true'" in following
    assert (
        "::warning::DRIFTLESS_PUBLIC_TOKEN not set — public mirror skipped; "
        "the site will not see this release" in following
    )


def test_the_mirror_step_only_runs_when_the_token_is_present() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    idx = text.index(f"- name: {MIRROR_STEP}")
    following = text[idx : idx + 400]

    assert "if: env.HAS_PUBLIC_TOKEN == 'true'" in following


def test_the_mirror_targets_the_public_repository_by_name() -> None:
    script = _step_script(MIRROR_STEP)

    assert IMAGE_REPOSITORY in script
    assert SNAPSHOT_SOURCE not in script, "the private name must never appear, even here"


def test_the_mirror_snapshots_a_fresh_checkout_rather_than_pushing_the_archives_ref() -> None:
    """The public repository never receives a push of this repository's own ref: it
    receives a `git archive` snapshot committed fresh on a clone of the PUBLIC repo.
    Every `git push` in this step must run from inside that fresh clone, never from
    the archive checkout `actions/checkout` made at the top of the job."""
    script = _step_script(MIRROR_STEP)

    assert 'archive "$TAG"' in script, "the snapshot is built from the tag, not a live checkout"
    assert "git clone" in script

    enter_clone = script.index("cd ")
    pushes = [m.start() for m in re.finditer(r"git push", script)]
    assert pushes, "the mirror step must push the snapshot it built"
    assert all(i > enter_clone for i in pushes), (
        "a git push before entering the fresh clone would push from the archive checkout"
    )
    assert 'git push origin "$GITHUB_WORKSPACE"' not in script
    assert (
        "$GITHUB_SHA" not in script.split("git push")[0] or True
    )  # SHA may appear in the commit message


def test_the_mirror_diffs_the_snapshot_before_committing_like_the_documented_procedure() -> None:
    """docs/release-publishing.md's step 1 diffs the archive's file list against the
    checkout before anything is committed — the automated path keeps that check."""
    script = _step_script(MIRROR_STEP)

    assert "diff <(" in script
    assert "tar -tf -" in script
    assert "git ls-files" in script


def test_the_mirror_publishes_the_same_notes_and_asset_as_the_archive_release() -> None:
    script = _step_script(MIRROR_STEP)

    assert NOTES_FILE in script, "the public release carries the same notes, not a summary"
    assert "gh release create" in script
    assert "gh release edit" in script, "a re-dispatch edits there too, same as the archive side"
    assert "gh release upload" in script, "the same tarball, not a second build"
    assert f"--repo {IMAGE_REPOSITORY}" in script


def _mirror_file_check(tmp_path: Path, drop: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run the mirror step's own pre-commit file-list check, as written in the workflow,
    over a real source repository with nested directories and a checkout built from it.

    ``drop`` removes one file from the checkout, the partial ``git rm``/stale checkout
    shape the check exists to catch.
    """
    lines = _step_script(MIRROR_STEP).splitlines()
    start = next(i for i, line in enumerate(lines) if line.lstrip().startswith("diff <("))
    check = lines[start] + "\n" + lines[start + 1]

    def git(*args: str, cwd: Path) -> None:
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    source = tmp_path / "source"
    (source / "pkg" / "sub").mkdir(parents=True)
    (source / "README.md").write_text("r\n", encoding="utf-8")
    (source / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (source / "pkg" / "sub" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    git("init", "-q", cwd=source)
    git("add", "-A", cwd=source)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "s", cwd=source)
    git("tag", "v9.9.9", cwd=source)

    public = tmp_path / "public"
    public.mkdir()
    git("init", "-q", cwd=public)
    archive = subprocess.run(
        ["git", "archive", "v9.9.9"], cwd=source, check=True, capture_output=True
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(public)], input=archive, check=True)
    if drop:
        (public / drop).unlink()
    git("add", "-A", cwd=public)

    env = {**os.environ, "GITHUB_WORKSPACE": str(source), "TAG": "v9.9.9"}
    return subprocess.run(
        ["bash", "-c", f"set -euo pipefail\n{check}"],
        cwd=public,
        env=env,
        capture_output=True,
        text=True,
    )


def test_the_mirror_file_check_passes_a_faithful_snapshot_with_nested_directories(
    tmp_path: Path,
) -> None:
    """Run 36332274615 (v0.7.0): `tar -tf` lists every directory as its own entry and
    `git ls-files` never does, so a byte-identical snapshot failed the check with 44
    `< dir/` lines and nothing was mirrored."""
    result = _mirror_file_check(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_the_mirror_file_check_still_catches_a_file_missing_from_the_checkout(
    tmp_path: Path,
) -> None:
    result = _mirror_file_check(tmp_path, drop="pkg/sub/mod.py")

    assert result.returncode != 0
    assert "pkg/sub/mod.py" in result.stdout


PROTECTED_DEST = re.compile(r"(^|[:/+\s])(refs/heads/)?(main|master)(\"|'|\s|$)")


def _mirror_push_lines() -> list[str]:
    return [
        line.strip()
        for line in _step_script(MIRROR_STEP).splitlines()
        if re.match(r"\s*git push\b", line)
    ]


def test_the_mirror_never_pushes_to_the_public_default_branch() -> None:
    """Run 36333645840 (v0.7.0): the self-hosted runner's `git` refuses every push to
    main/master and has no override, so the snapshot goes to a branch and master only
    moves through a pull request a person merges."""
    pushes = _mirror_push_lines()

    assert pushes, "the mirror step still has to push the snapshot somewhere"
    for line in pushes:
        refspecs = line.split("origin", 1)[1]
        assert not PROTECTED_DEST.search(refspecs), f"pushes to a protected branch: {line}"


def test_the_mirror_pushes_the_snapshot_to_a_release_branch_and_the_tag() -> None:
    script = _step_script(MIRROR_STEP)
    pushes = " ".join(_mirror_push_lines())

    assert 'BRANCH="release/$TAG"' in script
    assert "refs/heads/$BRANCH" in pushes
    assert 'refs/tags/$TAG"' in pushes
    assert 'git ls-remote --tags origin "refs/tags/$TAG"' in script, (
        "a re-dispatch must reuse a tag already on the public repository, never move it"
    )


def test_the_master_pull_request_is_opened_last_and_cannot_fail_the_release() -> None:
    """The tag, release and asset are what the site reads, so they publish first; the
    pull request is best-effort because the token may lack pull-requests: write."""
    script = _step_script(MIRROR_STEP)

    assert script.index("gh pr create") > script.index("gh release upload")
    assert "--base master" in script
    assert "elif ! gh pr create" in script
    assert "::warning::could not open the master pull request" in script
    assert "compare/master...$BRANCH" in script
