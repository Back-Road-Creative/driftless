"""Every verification workflow job needs a local stage, or a local run's
silence hides a real gap.

CI is unavailable for this account indefinitely (a billing failure with no fix
date), so `bin/driftless-gates.sh` is the only verification this repo gets. The
danger this test exists to catch is not hypothetical: `tests/test_migrations.py`
skips its Postgres half whenever `DRIFTLESS_TEST_DB_URL` is unset, so a plain
local run reports passing tests while proving nothing about the one dialect
production actually runs on. If a future CI job repeats that shape — real
locally only through a variable nobody sets — this test is what turns the gap
into a red test instead of a quiet skip.

`pip-audit.yml` is the worked example of the same gap one level up: it is a
whole second workflow, not a `ci.yml` job, so it sat outside this guard
entirely and stopped running — silently — the day Actions did. It is checked
here rather than added to `ci.yml`'s map, so both files are covered by name and
neither can go unrepresented without this test failing.

The parse is job-id based (the stable YAML key under `jobs:`), not the
free-text `name:` a job carries, so a rewording of a job's display name cannot
flip this test green or red for the wrong reason.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CI = REPO / ".github" / "workflows" / "ci.yml"
AUDIT = REPO / ".github" / "workflows" / "pip-audit.yml"
BROWSER = REPO / ".github" / "workflows" / "browser.yml"
GATES = REPO / "bin" / "driftless-gates.sh"

# Every job id, per workflow, that runs verification work maps to the CLI flag
# that selects the matching local stage. A job left out of this map on purpose
# (see EXCLUDED_JOBS) is a job that verifies nothing itself.
JOB_TO_GATE_FLAG = {
    CI: {
        "quality": "--quality",
        "test": "--tests",
        "migrations": "--migrations",
        "docker-build": "--docker-build",
    },
    AUDIT: {
        "audit": "--audit",
    },
    # Registered here the day it was added, for the reason the module docstring
    # gives: a verification workflow outside this map is exactly how pip-audit.yml
    # stopped running unnoticed. That it is opt-in and non-required changes when it
    # runs, not whether a local stage must exist to run it.
    BROWSER: {
        "browser": "--browser",
    },
}

# Jobs that are not verification gates and so need no local stage. Each entry
# names why, so an addition here is a decision, not a silent carve-out.
EXCLUDED_JOBS = {
    CI: {
        "alert": "notifies on a red *scheduled* run; runs no checks of its own",
    },
    AUDIT: {
        "alert": "notifies on a red *scheduled* run; runs no checks of its own",
    },
    BROWSER: {},
}


def _jobs_from_workflow(path: Path) -> list[str]:
    """Job ids declared under the top-level `jobs:` key of a workflow file."""
    text = path.read_text()
    _, _, after_jobs = text.partition("\njobs:\n")
    assert after_jobs, (
        f"no top-level `jobs:` block found in {path.name} — the workflow changed shape"
    )
    jobs = re.findall(r"(?m)^  ([a-zA-Z0-9_-]+):[ \t]*$", after_jobs)
    assert jobs, (
        f"parsed zero jobs out of {path.name} — the parser broke, or the workflow's shape did"
    )
    return jobs


def test_every_verification_job_has_a_mapped_gate_flag() -> None:
    """Every job in each covered workflow is mapped to a gate flag or excluded."""
    for workflow, flag_map in JOB_TO_GATE_FLAG.items():
        jobs = _jobs_from_workflow(workflow)
        excluded = EXCLUDED_JOBS[workflow]
        unaccounted = [j for j in jobs if j not in flag_map and j not in excluded]
        assert not unaccounted, (
            f"{workflow.name} job(s) {unaccounted} have no bin/driftless-gates.sh stage and are "
            "not excluded-with-reason — add a stage (preferred) or an excluded entry"
        )
        # A job that vanished from a workflow but is still mapped here would let
        # the map rot unnoticed in the other direction.
        stale = [j for j in flag_map if j not in jobs]
        assert not stale, f"gate flag(s) mapped for job(s) no longer in {workflow.name}: {stale}"


def test_gates_script_wires_every_mapped_flag() -> None:
    """Each mapped flag is a real, selectable stage in the script's arg parsing."""
    body = GATES.read_text()
    all_flags = [flag for flag_map in JOB_TO_GATE_FLAG.values() for flag in flag_map.values()]
    missing = [flag for flag in all_flags if flag not in body]
    assert not missing, f"bin/driftless-gates.sh has no case arm for: {missing}"
