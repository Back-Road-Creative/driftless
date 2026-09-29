"""The committed-sample drift gate in ``.github/workflows/ci.yml``, run as the runner runs it.

The gate reads its scope off the tracked tree rather than off a list written down
anywhere, so the per-project sample sets still to land are covered the moment they are
committed. A scope read off the tree can also SHRINK, and only the loud half of that was
refused: an empty scope fails, because a gate whose file list can go to zero passes
vacuously. ``git rm`` of SOME samples did not fail. It is the likelier move, too —
deleting the file is one way to make a confusing drift failure go away, and it left the
step green over a narrower bundle than the one the reviewer thought they were reading.

What tells a deletion from a document the report engine legitimately stopped emitting is
the rerun the step already performs: if the generator still writes the file, it was
deleted. No count is written down here or in the workflow — the base commit says what was
committed and the generator says what still exists, and both move on their own.

The step body is read out of the YAML and executed the way the runner executes it
(``bash -e``), against a throwaway git repository and a stub generator, so what these
assert is the gate's own decision rather than a paraphrase of it.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DRIFT_STEP = "Committed sample reports have not drifted"

#: Committed samples, in the shape the real bundle has: business documents at the as-of
#: root, project ones under a slugified subdirectory.
BUNDLE = (
    "docs/samples/2026-07-01/business-rollup.md",
    "docs/samples/2026-07-01/department.md",
    "docs/samples/2026-07-01/season-4-rollout/cost-evm.md",
    "docs/samples/2026-07-01/season-4-rollout/weekly-status.md",
)

#: Stands in for ``bin/driftless-sample-reports.py``: the gate only cares what lands
#: under ``--out``, and running the real generator here would need the whole app.
STUB = """#!/bin/sh
out=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--out" ]; then out="$2"; fi
  shift
done
mkdir -p "$out"
cp -R "$GENERATED"/. "$out"/
"""


def _step_script(step_name: str) -> str:
    """The dedented shell body of the ``run:`` block belonging to ``step_name``.

    A near-twin of the reader in ``tests/test_release_workflow.py``. Kept separate
    rather than shared because that one is bound to ``release.yml``, and a helper
    reaching across two workflow contracts is a shared edit on every change to either.
    """
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


def _job(name: str) -> str:
    """The YAML block belonging to one job — job keys are the only ones at this indent."""
    text = WORKFLOW.read_text(encoding="utf-8")
    rest = text[text.index(f"\n  {name}:\n") + 1 :]
    following = re.search(r"\n  \w[\w-]*:\n", rest)
    return rest if following is None else rest[: following.start()]


def _write(root: Path, paths: tuple[str, ...], body: str = "a rendered sample\n") -> None:
    for name in paths:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(body, encoding="utf-8")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        },
    )


def _gate(
    tmp_path: Path,
    committed: tuple[str, ...],
    head: tuple[str, ...],
    generated: tuple[str, ...],
    drifted: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    """Run the step over a checkout whose parent commit tracked ``committed`` and whose
    HEAD tracks ``head``, with a generator that writes ``generated``.

    ``HEAD^1`` is what the step compares against, which on a pull request is the base
    branch the merge commit was built from.
    """
    repo, out = tmp_path / "checkout", tmp_path / "generated"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    _write(repo, committed)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    for name in set(committed) - set(head):
        _git(repo, "rm", "-q", "--", name)
    _git(repo, "commit", "-qm", "head", "--allow-empty")

    _write(out, tuple(name.removeprefix("docs/samples/") for name in generated))
    _write(out, tuple(name.removeprefix("docs/samples/") for name in drifted), "regenerated\n")
    stub = repo / ".venv" / "bin" / "python"
    stub.parent.mkdir(parents=True)
    stub.write_text(STUB, encoding="utf-8")
    stub.chmod(0o755)

    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    return subprocess.run(
        # `bash -e` is the runner's default shell for a `run:` block, and this body
        # relies on it: nothing in it sets `set -e` itself.
        ["bash", "-e", "-c", _step_script(DRIFT_STEP)],
        cwd=repo,
        env={**os.environ, "RUNNER_TEMP": str(runner_temp), "GENERATED": str(out)},
        capture_output=True,
        text=True,
    )


def test_a_bundle_that_still_matches_the_generator_passes(tmp_path: Path) -> None:
    done = _gate(tmp_path, BUNDLE, BUNDLE, BUNDLE)

    assert done.returncode == 0, done.stdout + done.stderr
    assert "regenerate byte-identically" in done.stdout


def test_deleting_some_of_the_samples_no_longer_leaves_the_gate_green(tmp_path: Path) -> None:
    """The narrowing this gate could not see: fewer files, all of them matching, exit 0."""
    kept = BUNDLE[:-1]
    done = _gate(tmp_path, BUNDLE, kept, BUNDLE)

    assert done.returncode != 0, done.stdout + done.stderr
    assert BUNDLE[-1] in done.stdout + done.stderr


def test_a_document_the_report_engine_stopped_emitting_may_leave(tmp_path: Path) -> None:
    """The other side of it: the generator no longer writes the file, so it may go."""
    kept = BUNDLE[:-1]
    done = _gate(tmp_path, BUNDLE, kept, kept)

    assert done.returncode == 0, done.stdout + done.stderr


def test_an_empty_scope_still_fails(tmp_path: Path) -> None:
    """The loud half, which was already refused: a file list that can reach zero."""
    done = _gate(tmp_path, BUNDLE, (), BUNDLE)

    assert done.returncode != 0
    assert "proves nothing" in done.stdout + done.stderr


def test_a_sample_whose_bytes_moved_still_fails(tmp_path: Path) -> None:
    """The question the step was built to ask, unchanged by the checks around it."""
    done = _gate(tmp_path, BUNDLE, BUNDLE, BUNDLE[:-1], drifted=BUNDLE[-1:])

    assert done.returncode != 0
    assert "no longer matches" in done.stdout + done.stderr


def test_the_checkout_fetches_the_commit_the_step_compares_against() -> None:
    """Without the parent commit the step cannot see a removal, so it says so and fails
    rather than passing over a comparison it could not make — but the depth is what keeps
    that from being every run."""
    assert "fetch-depth: 2" in _job("test"), "the drift step reads HEAD^1 out of this checkout"
