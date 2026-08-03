"""This service checks its own governance contract, and publishes nothing that only
makes sense on the machine that wrote it.

WHY THE README CHECK LIVES HERE. A README states Purpose, Owner, Status and Exit
Condition; that is a property of THIS project, so the check belongs in THIS repo,
where a violation cannot merge. Run from a consumer instead, it checks a copy: a
consumer that mounts this repo as a submodule and does not fetch submodules sees
an empty directory, and a scanner over an empty directory reports green having
read nothing. Handing another project's CI a credential to clone this one buys
nothing that a check running here does not already give.

Only the README sections. No content schema is asserted, because this project
declares none, and a test that invented one would enforce a contract that does
not exist.

The rest of the module keeps the tree fit to publish: no authoring scaffold in a
document a release body is cut from, no repository named but this one, no
absolute path from one machine, no address table for a history that has none.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_docs_no_secrets_in_repo import tracked_files

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CLAUDE = ROOT / "CLAUDE.md"
CHANGELOG = ROOT / "CHANGELOG.md"
FRAGMENTS = ROOT / "changelog.d"
MAILMAP = ROOT / ".mailmap"

REQUIRED_SECTIONS = ("Purpose", "Owner", "Status", "Exit Condition")

ORG = "Back-Road-Creative"
# A closing tag alone on a line: markup in a document that is only ever prose.
SCAFFOLD_TAG = re.compile(r"^\s*</[\w:.-]+>\s*$")
# Somebody's home directory: real on the machine that wrote it, a dead end everywhere
# else. Deliberately NOT /opt, /var or /srv — those name the deployed container's own
# filesystem, which is identical on every machine that runs it, so the Dockerfile and
# the compose files say them correctly and often.
MACHINE_PATH = re.compile(r"/(?:home|Users)/[\w.-]+/[\w./-]*")

# Heading text at # or ##, matched case-insensitively: a top-level section, not a
# sub-heading that happens to share the word.
HEADING_RE = re.compile(r"^#{1,2}\s+(.+)$")
ANY_HEADING_RE = re.compile(r"^#{1,6}\s+")


def _lines() -> list[str]:
    return README.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")


def test_readme_exists_and_is_not_a_stub() -> None:
    assert README.is_file(), "README.md is missing"
    assert len(README.read_text(encoding="utf-8").strip()) > 50, "README.md is a stub"


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_readme_states_its(section: str) -> None:
    headings = [m.group(1).strip().lower() for line in _lines() if (m := HEADING_RE.match(line))]
    assert section.lower() in headings, (
        f"README.md has no '{section}' section. This project's governance contract "
        f"requires {', '.join(REQUIRED_SECTIONS)}."
    )


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_readme_section_has_a_body(section: str) -> None:
    """Four empty headings would satisfy the contract on a technicality."""
    lines = _lines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if (m := HEADING_RE.match(line)) and m.group(1).strip().lower() == section.lower()
        ),
        None,
    )
    if start is None:
        pytest.skip(f"'{section}' is absent — test_readme_states_its covers that")

    body: list[str] = []
    for line in lines[start + 1 :]:
        if ANY_HEADING_RE.match(line):
            break
        body.append(line)

    assert "".join(body).strip(), f"'{section}' is a heading with no body"


def test_the_changelog_carries_no_authoring_scaffold() -> None:
    """A fragment is copied into ``CHANGELOG.md`` and the release body verbatim, so one
    stray line of tool markup publishes in both places at once. ``bin/assemble-changelog.py``
    validates fragment *names*, not their content, which is how two arrived."""
    strays = [
        f"{path.name}:{number}: {line.strip()}"
        for path in (CHANGELOG, *sorted(FRAGMENTS.glob("*.md")))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if SCAFFOLD_TAG.match(line)
    ]
    assert not strays, "markup where a changelog holds only prose:\n" + "\n".join(strays)


def test_the_only_repository_this_tree_names_is_this_one() -> None:
    """Naming a private sibling tells a reader it exists, who owns it and what is in it.
    The *reason* a shape was borrowed from one is worth keeping; the name never is."""
    foreign = re.compile(rf"{ORG}/(?!driftless\b)[\w.-]+")
    tracked = tracked_files()
    assert tracked, "git listed no tracked files, so this scan read nothing to pass on"
    named = [
        f"{name}:{number}: {found.group(0)}"
        for name in tracked
        for number, line in enumerate(
            (ROOT / name).read_bytes().decode("utf-8", "replace").splitlines(), 1
        )
        if (found := foreign.search(line))
    ]
    assert not named, "a repository the reader cannot open is named here:\n" + "\n".join(named)


def test_no_tracked_file_names_a_path_only_one_machine_has() -> None:
    """Every command this repo ships has to work from a fresh clone. A path inside one
    user's home directory works for exactly one reader and tells the rest of them the
    layout of a machine they will never log in to."""
    tracked = tracked_files()
    assert tracked, "git listed no tracked files, so this scan read nothing to pass on"
    local = [
        f"{name}:{number}: {found.group(0)}"
        for name in tracked
        for number, line in enumerate(
            (ROOT / name).read_bytes().decode("utf-8", "replace").splitlines(), 1
        )
        if (found := MACHINE_PATH.search(line))
    ]
    assert not local, "an instruction only its author can follow:\n" + "\n".join(local)


def test_no_mailmap_publishes_addresses_the_commits_do_not() -> None:
    """A ``.mailmap`` folds several committer addresses onto one identity. Ours listed two
    personal addresses to rewrite a name they already carried — every address in the file
    was one the file itself introduced."""
    assert not MAILMAP.is_file(), (
        ".mailmap publishes every address it maps. Rewrite the identity at commit time "
        "(git config user.email) rather than shipping a table of the old ones."
    )
