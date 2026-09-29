"""`bin/driftless-gates.sh` runs CI's gates, and runs them at CI's versions.

The gate that matters here is not "does the script exist" — it is that the
script cannot name a tool version of its own. A local command that pins
`ruff==0.15.22` in its own text is correct on the day it is written and silently
wrong on the day CI bumps: the developer's run goes green against a linter the
merge will never use. So the script reads every pin out of the workflow files,
and these tests prove the reading, not a copy of the answer.

The failure mode they exist to catch is the parser going stale — CI changes how
it declares a version, the script's extraction quietly yields nothing, and the
gates run at whatever happens to be installed.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATES = REPO / "bin" / "driftless-gates.sh"
CI = REPO / ".github" / "workflows" / "ci.yml"
AUDIT = REPO / ".github" / "workflows" / "pip-audit.yml"


def _pins_from_workflows() -> dict[str, str]:
    """Read the pins the way a reader would, independently of the script."""
    ci = CI.read_text()
    audit = AUDIT.read_text()

    def one(pattern: str, text: str) -> str:
        found = re.findall(pattern, text)
        assert found, f"no match for {pattern!r} — the workflow changed shape"
        assert len(set(found)) == 1, f"conflicting pins for {pattern!r}: {found}"
        return found[0]

    return {
        "ruff": one(r"RUFF_VERSION:\s*'([^']+)'", ci),
        "detect-secrets": one(r"DETECT_SECRETS_VERSION:\s*'([^']+)'", ci),
        "mypy": one(r"mypy==([0-9][^\s\"']*)", ci),
        "pip-audit": one(r"PIP_AUDIT_VERSION:\s*'([^']+)'", audit),
        "python": one(r"python-version:\s*'([^']+)'", ci),
    }


def test_gates_script_is_executable() -> None:
    assert GATES.is_file(), f"{GATES} is missing"
    assert os.access(GATES, os.X_OK), f"{GATES} is not executable"


def test_gates_script_states_no_version_of_its_own() -> None:
    """A pin written here is a pin that can disagree with CI. Read, never restate."""
    body = GATES.read_text()
    offenders = re.findall(r"(?:ruff|detect-secrets|mypy|pip-audit)==[0-9][^\s\"']*", body)
    assert not offenders, f"{GATES.name} hardcodes tool versions: {offenders}"
    assert "--cov-fail-under" not in body, (
        "the coverage floor lives in pyproject.toml addopts; restating it here lets a "
        "stale number read as a green suite"
    )


def test_gates_script_reports_the_pins_ci_declares() -> None:
    """`--print-pins` is the extraction, exercised. If it goes stale, this goes red."""
    result = subprocess.run(
        ["bash", str(GATES), "--print-pins"],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    reported = dict(line.split("=", 1) for line in result.stdout.split() if "=" in line)
    assert reported == _pins_from_workflows()
