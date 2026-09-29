"""Contract tests for the three places the public-repo leak scan runs.

The scanner and its rule set live once, in the org's public shared-config
repository, and are fetched at a pinned commit by each caller below. These tests
check the shape of the CALLS this repo makes into it, and that the local
allowlist (``.github/leak-scan-allowlist.json``) is both well-formed by the
scanner's own contract and live — an allowlist entry nothing in the tree still
matches is the exemption-list rot the guard exists to avoid.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
LEAK_SCAN_YML = WORKFLOWS / "leak-scan.yml"
CI_YML = WORKFLOWS / "ci.yml"
RELEASE_YML = WORKFLOWS / "release.yml"
ALLOWLIST = ROOT / ".github" / "leak-scan-allowlist.json"
SCAN_STEP = "Leak-scan the snapshot before it is published"
MIRROR_STEP = "Mirror the snapshot, release and asset to the public repository"
# The trailing comment is the detect-secrets pragma: a 40-hex commit id reads as a secret.
PINNED_REF = re.compile(r"^\s*LEAK_SCAN_REF: '([0-9a-f]{40})'(?:\s+#.*)?$", re.M)

# The scanner's own rule ids (build_rules() in the org's leak_scan.py), named here so an
# allowlist entry can be checked against a real rule without a network fetch or a second
# copy of the scanner tracked in this repo.
SCANNER_RULE_IDS = {
    "foreign-repo",
    "client-name",
    "machine-path",
    "private-project",
    "workspace-convention",
}


def _step_block(workflow: Path, step_name: str) -> str:
    """Everything from ``- name: step_name`` up to the next step of the same job."""
    lines = workflow.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == f"- name: {step_name}")
    dash = len(lines[start]) - len(lines[start].lstrip())
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if lines[i].strip()
            and len(lines[i]) - len(lines[i].lstrip()) <= dash
            and not lines[i].lstrip().startswith("#")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _step_script(workflow: Path, step_name: str) -> str:
    lines = _step_block(workflow, step_name).splitlines()
    run = next(i for i, line in enumerate(lines) if line.strip() == "run: |")
    indent = len(lines[run + 1]) - len(lines[run + 1].lstrip())
    return "\n".join(line[indent:] for line in lines[run + 1 :])


def _invocation(script: str) -> str:
    """The scanner command line, joined across its ``\\`` continuations."""
    lines = script.splitlines()
    start = next(i for i, line in enumerate(lines) if "leak_scan.py" in line)
    end = start
    while lines[end].rstrip().endswith("\\"):
        end += 1
    return "\n".join(lines[start : end + 1])


def test_leak_scan_workflow_calls_the_reusable_scanner() -> None:
    text = LEAK_SCAN_YML.read_text(encoding="utf-8")
    assert "uses: Back-Road-Creative/.github/.github/workflows/leak-scan.yml@main" in text


def test_leak_scan_triggers_on_pull_request_and_every_branch_push() -> None:
    text = LEAK_SCAN_YML.read_text(encoding="utf-8")
    assert re.search(r"^on:\n(  pull_request:\n  push:|  push:\n  pull_request:)", text, re.M), text
    # No `branches:` filter under `push:`: a branch pushed straight to the public
    # repository with no pull request is exactly what a master-only filter skips.
    push_block = text[text.index("  push:") : text.index("jobs:")]
    assert "branches:" not in push_block, push_block


def test_leak_scan_job_is_guarded_to_the_public_repository() -> None:
    text = LEAK_SCAN_YML.read_text(encoding="utf-8")
    assert "if: github.repository == 'Back-Road-Creative/driftless'" in text


def test_quality_job_scans_this_checkout_under_the_public_name() -> None:
    script = _step_script(CI_YML, "Leak scan as the public repository")
    assert (
        'fetch -q --depth 1 https://github.com/Back-Road-Creative/.github.git "$LEAK_SCAN_REF"'
        in script
    )
    invocation = _invocation(script)
    assert "--repo-root ." in invocation
    assert "--self-name Back-Road-Creative/driftless" in invocation
    assert "rm -rf" in script, "a reused self-hosted RUNNER_TEMP must not see a stale clone"


def test_both_workflows_run_the_scanner_at_one_pinned_commit() -> None:
    """The release job holds a push token for the public repository, so the code it runs
    is a reviewed commit, never whatever the shared repo's `main` holds that minute."""
    ci_pins = PINNED_REF.findall(CI_YML.read_text(encoding="utf-8"))
    scan_pins = PINNED_REF.findall(_step_block(RELEASE_YML, SCAN_STEP))
    assert len(ci_pins) == 1 and len(scan_pins) == 1, (ci_pins, scan_pins)
    assert ci_pins == scan_pins, "ci.yml and release.yml must scan with the same scanner"

    for workflow in WORKFLOWS.glob("*.yml"):
        text = workflow.read_text(encoding="utf-8")
        assert not re.search(r"git clone\b.*Back-Road-Creative/\.github\.git", text), (
            f"{workflow.name}: an unpinned clone of the scanner's repository"
        )


def test_release_scans_in_its_own_step_before_the_mirror_under_the_same_guard() -> None:
    text = RELEASE_YML.read_text(encoding="utf-8")
    assert text.index(f"- name: {SCAN_STEP}") < text.index(f"- name: {MIRROR_STEP}")

    guard = "if: env.HAS_PUBLIC_TOKEN == 'true'"
    assert guard in _step_block(RELEASE_YML, SCAN_STEP)
    assert guard in _step_block(RELEASE_YML, MIRROR_STEP)
    # A finding fails the scan step, and a failed step skips every later step that has
    # no `if: always()`/`failure()` of its own -- so the mirror never starts.
    assert "always()" not in _step_block(RELEASE_YML, MIRROR_STEP)
    assert "failure()" not in _step_block(RELEASE_YML, MIRROR_STEP)
    assert "leak_scan.py" not in _step_script(RELEASE_YML, MIRROR_STEP)


def test_the_scan_step_never_sees_the_public_push_token() -> None:
    block = _step_block(RELEASE_YML, SCAN_STEP)
    assert "secrets." not in block, "no secret belongs in the step that runs the scanner"
    assert "DRIFTLESS_PUBLIC_TOKEN" not in block

    invocation = _invocation(_step_script(RELEASE_YML, SCAN_STEP))
    assert invocation.startswith("env -u GH_TOKEN python3 "), (
        "the scanner runs with no token at all; the workflow shell reads the public list"
    )
    assert '--public-repos "$PUBLIC_REPOS"' in invocation
    assert '--repo-root "$SNAP"' in invocation
    assert "--self-name Back-Road-Creative/driftless" in invocation


def test_the_scan_step_scans_the_tree_the_mirror_commits() -> None:
    archive = 'git -C "$GITHUB_WORKSPACE" archive "$TAG"'
    scan = _step_script(RELEASE_YML, SCAN_STEP)
    mirror = _step_script(RELEASE_YML, MIRROR_STEP)

    assert f'{archive} | tar -x -C "$SNAP"' in scan
    assert 'git -C "$SNAP" add -A' in scan
    assert f'{archive} | tar -x -C "$PUBLIC"' in mirror
    # The mirror's own pre-commit check is what makes "the same tree" true: any
    # difference between what it stages and the tag's archive stops it.
    assert f"diff <({archive} | tar -tf -" in mirror


def _allowlist_entries() -> list[dict]:
    data = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    entries = data["allow"]
    assert isinstance(entries, list) and entries
    return entries


def test_allowlist_is_valid_json_with_the_scanners_required_fields() -> None:
    for entry in _allowlist_entries():
        for key in ("rule", "path", "match", "reason"):
            assert str(entry.get(key, "")).strip(), f"entry missing '{key}': {entry}"
        assert len(entry["reason"]) >= 20, entry
        assert entry["rule"] in SCANNER_RULE_IDS, entry


@pytest.mark.parametrize("entry", _allowlist_entries(), ids=lambda e: f"{e['path']}:{e['rule']}")
def test_every_allowlist_entry_is_live(entry: dict) -> None:
    """An entry nothing in the tree matches is silently guarding nothing -- the moment
    the line it was written for is deleted or reworded, the entry should go with it.
    Each `match` is the whole flagged text, not a short fragment of it, so an entry
    exempts that one line and never a new one that merely shares a word."""
    target = ROOT / entry["path"]
    assert target.is_file(), f"{entry['path']} is not a tracked file this scan would read"
    text = target.read_bytes().decode("utf-8", "replace")
    assert entry["match"] in text, (
        f"{entry['path']}: allowlisted match {entry['match']!r} is not in the file any more"
    )
    assert len(entry["match"]) >= 15, f"{entry['match']!r} is too short to name one line"
