"""A bind mount whose source no checkout carries, and what .gitignore says about it.

Docker does not refuse a bind mount with a missing source — it creates an empty
**directory** there. ``docker-compose.yml`` named the SOPS overlay as a plain relative
path, and no checkout has that file: it is written on the deployment host by
``sops-edit``. So the first ``docker compose up`` in a fresh clone made a directory
where the encrypted overlay belongs, and OPERATIONS.md's next step,
``cp deploy/secrets.env.example deploy/…``, then dropped the **plaintext** template
*inside* that directory instead of failing. The fix is the shape the age key already
uses one line below: a required variable, so Compose refuses to interpolate, says which
variable is missing, and starts nothing.

Every check reads the repository instead of pinning a string. "A file a fresh checkout
carries" is `git ls-files` and "a variable Compose requires" is read off the compose files
themselves, so each guard re-derives its claim rather than restating it —
which is also why the second one catches the comment that told readers an encrypted
secrets file was committed here while `git ls-files deploy/` listed only the plaintext
example. Read by hand, not parsed, for tests/test_deploy_healthcheck.py's reason: no
PyYAML dependency.
"""

from __future__ import annotations

import re
import subprocess
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GITIGNORE = ROOT / ".gitignore"
OPERATIONS = ROOT / "OPERATIONS.md"
COMPOSES = ("docker-compose.yml", "deploy/proxy.compose.yml")
REQUIRED = re.compile(r"^\$\{[A-Za-z_]\w*:\?")  # ${VAR:?why} — Compose stops when unset
NAMED = re.compile(r"\$\{([A-Za-z_]\w*):\?")  # the same shape anywhere in the file, captured
EXPORTED = re.compile(r"\s*export\s+([A-Za-z_]\w*)=")
DEFAULTED = re.compile(r"^\$\{[A-Za-z_]\w*:-([^}]*)\}$")
PATHISH = re.compile(r"[\w-]{3,}(?:\.[A-Za-z]\w*)+")  # a bare name carrying a suffix
OUTSIDE = ("/", "~", "$", "../")  # rooted elsewhere: not this repository's tree


def tracked() -> set[str]:
    """Every path git tracks — what a fresh clone, and only a fresh clone, contains."""
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return {name for name in listed.stdout.split("\0") if name}


def carried(path: str, files: set[str]) -> bool:
    """Is ``path`` a tracked file, or a directory holding one?"""
    return path in files or any(name.startswith(f"{path}/") for name in files)


def volume_entries(path: Path) -> list[tuple[int, str]]:
    """``(line number, entry)`` under a *service's* ``volumes:`` — the top-level key of
    that name declares named volumes and mounts nothing, so only an indented one counts."""
    entries, indent = [], None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text, depth = line.strip(), len(line) - len(line.lstrip())
        if indent is not None and text and not text.startswith("#"):
            if depth <= indent:
                indent = None
            elif text.startswith("- "):
                entries.append((number, text[2:].strip()))
        if text == "volumes:" and depth > 0:
            indent = depth
    return entries


def host_side(entry: str) -> str:
    """``source`` out of ``source:target[:mode]`` — a colon inside ``${…}`` is the message's."""
    depth = 0
    for index, char in enumerate(entry):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == ":" and depth == 0:
            return entry[:index]
    return entry


def comment_paths(line: str) -> list[str]:
    """Path-ish words in a comment: anything with a directory, or a name with a suffix."""
    found = []
    for word in line.split():
        token = word.lstrip("`'\"([").removesuffix("'s").rstrip("`'\").,;:]")
        if token and not token.startswith(OUTSIDE) and ("/" in token or PATHISH.fullmatch(token)):
            found.append(token)
    return found


def exported(path: Path) -> set[str]:
    """Variables a document tells an operator to export, inside a block they can run."""
    names, fenced = set(), False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif fenced and (match := EXPORTED.match(line)):
            names.add(match.group(1))
    return names


def ignored(path: str, patterns: list[str]) -> bool:
    """Does one of .gitignore's own patterns already hide this path?"""
    base = path.rsplit("/", 1)[-1]
    return any(
        fnmatch(path, rule) or fnmatch(base, rule) or path.startswith(f"{rule}/")
        for rule in (pattern.strip("/") for pattern in patterns)
    )


def test_a_mount_source_no_checkout_carries_is_a_required_variable() -> None:
    """Anything else hands Docker a missing path, and Docker makes a directory of it."""
    files = tracked()
    entries = [
        (name, number, host_side(entry))
        for name in COMPOSES
        for number, entry in volume_entries(ROOT / name)
    ]
    assert entries, f"no volume entry parsed out of {COMPOSES}, so this guard checked nothing"
    assert any(REQUIRED.match(source) for _, _, source in entries), (
        f"no required-variable mount source parsed, so the shape this asks for is unreachable "
        f"and the parser is what is broken: {entries}"
    )
    offenders = []
    for name, number, source in entries:
        if REQUIRED.match(source):
            continue
        literal = (match.group(1) if (match := DEFAULTED.match(source)) else source).strip("\"'")
        relative = literal[2:] if literal.startswith("./") else literal
        if "/" not in literal or literal.startswith(OUTSIDE) or carried(relative, files):
            continue  # a named volume, a path outside the checkout, or a file git carries
        offenders.append(f"{name}:{number} mounts {literal!r}")
    assert not offenders, (
        f"a bind mount names a source no checkout has: {offenders}. Docker does not refuse "
        "one — it creates an empty directory at the missing path, and the plaintext template "
        "an operator copies next lands inside it. Write the source as ${VAR:?why}, the shape "
        "the age key uses: Compose then names the variable and starts nothing."
    )


def test_every_variable_compose_requires_is_one_operations_md_hands_the_operator() -> None:
    """A `${VAR:?}` starts nothing until it is exported, so a document has to say to."""
    names = {
        name
        for compose in COMPOSES
        for name in NAMED.findall((ROOT / compose).read_text(encoding="utf-8"))
    }
    assert names, f"no ${{VAR:?}} parsed out of {COMPOSES}, so this guard checked nothing"
    unsaid = sorted(names - exported(OPERATIONS))
    assert not unsaid, (
        f"Compose refuses to start until {unsaid} are set, and OPERATIONS.md never tells an "
        "operator to export them — leaving Compose's message as the whole of the instructions. "
        "Add the export to the fenced block that brings the stack up."
    )


def test_gitignore_claims_nothing_about_a_file_this_repository_does_not_have() -> None:
    """Its comments described a committed encrypted overlay; git tracked no such file."""
    lines = GITIGNORE.read_text(encoding="utf-8").splitlines()
    patterns = [entry for line in lines if (entry := line.split("#")[0].strip())]
    assert patterns, ".gitignore parsed as no patterns at all, so this guard read nothing"
    files = tracked()
    ghosts = [
        f".gitignore:{number} names {path!r}"
        for number, line in enumerate(lines, 1)
        if line.lstrip().startswith("#")
        for path in comment_paths(line)
        if not carried(path, files) and not ignored(path, patterns)
    ]
    assert not ghosts, (
        f"a .gitignore comment describes a file this repository neither tracks nor ignores, "
        f"so the comment has drifted from the tree it explains: {ghosts}. Check `git ls-files` "
        "before restating what is committed here."
    )
