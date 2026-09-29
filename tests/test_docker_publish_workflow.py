"""Contract tests for ``.github/workflows/docker-publish.yml``.

A ``workflow_dispatch`` without ``--ref`` checks out master-at-dispatch and labels
it with whatever tag was typed in — the image and the tag it wears disagree. An
``INPUT_TAG`` with no format check reaches the meta step unvalidated, unlike the
push trigger's glob. And every version ever built was tagged ``:latest`` on top
of ``:version``, so republishing an older tag moved ``latest`` backwards. These
tests run the meta step's shell body the way the runner does, over a fixture git
checkout, and check the workflow text for the parts that are not shell.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "docker-publish.yml"
META_STEP = "Image tags, and whether this run publishes"
INPUT_GATE_STEP = "Refuse a dispatched tag the checkout cannot resolve"


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


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path: Path, tags: list[str]) -> Path:
    """A fixture checkout with the given tags on its single commit."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-q", "-m", "fixture")
    for tag in tags:
        _git(tmp_path, "tag", tag)
    return tmp_path


def _meta(
    tmp_path: Path,
    *,
    event: str,
    tags_on_repo: list[str],
    input_tag: str = "",
    input_push: str = "false",
    repository: str = "Back-Road-Creative/driftless",
    ref_name: str = "",
) -> subprocess.CompletedProcess[str]:
    repo = _repo(tmp_path, tags_on_repo)
    github_output = tmp_path / "github-output.txt"
    github_output.write_text("", encoding="utf-8")
    env = {
        **os.environ,
        "INPUT_TAG": input_tag,
        "INPUT_PUSH": input_push,
        "EVENT": event,
        "REPOSITORY": repository,
        "GITHUB_REF_NAME": ref_name,
        "GITHUB_OUTPUT": str(github_output),
    }
    result = subprocess.run(
        ["bash", "-c", _step_script(META_STEP)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )
    result.stdout = github_output.read_text(encoding="utf-8") if github_output.exists() else ""
    return result


def test_checkout_pins_the_ref_the_dispatch_input_names() -> None:
    """A dispatch without --ref must not silently build master-at-dispatch."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "ref: ${{ inputs.tag || github.ref }}" in text


def test_checkout_fetches_tags_so_the_latest_check_can_see_them() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "fetch-depth: 0" in text or "fetch-tags: true" in text


def test_the_job_skips_the_build_on_archive_tag_pushes() -> None:
    """The archive never pushes, so a tag push there should not build at all."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert (
        "if: github.repository == 'Back-Road-Creative/driftless' "
        "|| github.event_name == 'workflow_dispatch'" in text
    )


def _input_gate(
    input_tag: str, *, event: str = "workflow_dispatch"
) -> subprocess.CompletedProcess[str]:
    """Run the pre-checkout format gate the way the runner does."""
    return subprocess.run(
        ["bash", "-c", _step_script(INPUT_GATE_STEP)],
        env={**os.environ, "INPUT_TAG": input_tag, "EVENT": event},
        capture_output=True,
        text=True,
    )


def test_the_tag_format_gate_runs_BEFORE_the_checkout_that_consumes_it() -> None:
    """A gate downstream of the step it protects is not a gate.

    The format check used to live in the meta step, which runs after `Checkout`
    has already resolved `inputs.tag` as a git ref. A dispatch carrying `0.6.1`
    therefore died at checkout with "A branch or tag with the name '0.6.1' could
    not be found" -- opaque, and the refusal that names the real problem never
    ran (v0.6.1, run 34880468332, 2026-09-14).
    """
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    gate = next(i for i, line in enumerate(lines) if line.strip() == f"- name: {INPUT_GATE_STEP}")
    checkout = next(i for i, line in enumerate(lines) if line.strip() == "- name: Checkout")

    assert gate < checkout, "the format check must refuse before checkout resolves the input"


def test_a_malformed_dispatched_tag_is_refused() -> None:
    done = _input_gate("garbage")

    assert done.returncode != 0, done.stderr
    assert "garbage" in done.stderr, done.stderr


def test_a_dispatched_tag_missing_the_leading_v_is_refused() -> None:
    done = _input_gate("0.2.0")

    assert done.returncode != 0, done.stderr


def test_the_format_gate_leaves_a_tag_push_alone() -> None:
    """A pushed tag was matched by the trigger's glob; there is no input to check."""
    done = _input_gate("", event="push")

    assert done.returncode == 0, done.stderr


def test_a_well_formed_dispatched_tag_passes(tmp_path: Path) -> None:
    done = _meta(
        tmp_path,
        event="workflow_dispatch",
        tags_on_repo=["v1.0.0", "v1.2.0"],
        input_tag="v1.2.0",
    )

    assert done.returncode == 0, done.stderr
    assert "version=1.2.0" in done.stdout, done.stdout


def test_building_a_version_below_the_highest_existing_tag_omits_latest(
    tmp_path: Path,
) -> None:
    done = _meta(
        tmp_path,
        event="workflow_dispatch",
        tags_on_repo=["v1.0.0", "v1.2.0"],
        input_tag="v1.0.0",
    )

    assert done.returncode == 0, done.stderr
    assert "ghcr.io/back-road-creative/driftless:1.0.0" in done.stdout, done.stdout
    assert "ghcr.io/back-road-creative/driftless:latest" not in done.stdout, done.stdout


def test_building_the_highest_existing_tag_includes_latest(tmp_path: Path) -> None:
    done = _meta(
        tmp_path,
        event="workflow_dispatch",
        tags_on_repo=["v1.0.0", "v1.2.0"],
        input_tag="v1.2.0",
    )

    assert done.returncode == 0, done.stderr
    assert "ghcr.io/back-road-creative/driftless:1.2.0" in done.stdout, done.stdout
    assert "ghcr.io/back-road-creative/driftless:latest" in done.stdout, done.stdout


def test_a_tag_push_of_the_newest_tag_includes_latest(tmp_path: Path) -> None:
    done = _meta(
        tmp_path,
        event="push",
        tags_on_repo=["v1.0.0", "v2.0.0"],
        ref_name="v2.0.0",
    )

    assert done.returncode == 0, done.stderr
    assert "push=true" in done.stdout, done.stdout
    assert "ghcr.io/back-road-creative/driftless:latest" in done.stdout, done.stdout


@pytest.mark.parametrize(
    "repository",
    ["Someone-Else/driftless", "someone-else/fork"],
)
def test_a_non_public_repository_never_pushes(tmp_path: Path, repository: str) -> None:
    done = _meta(
        tmp_path,
        event="push",
        tags_on_repo=["v1.0.0"],
        ref_name="v1.0.0",
        repository=repository,
    )

    assert done.returncode == 0, done.stderr
    assert "push=false" in done.stdout, done.stdout
