"""No document hands an operator a command that writes a private key inside the checkout.

A key generated in the repo is one `docker build` away from a permanent image layer and one
`git add` away from history, so the destination — not the operator's care — is what has to be
right. The forbidden shape is not a filename this test knows: it is read out of the repo's own
ignore files, which are where this repo already states which files must never be inside it
(`.gitignore`'s age-key entries today; `.dockerignore` when it exists — absent, it is skipped,
never imported). That is also why `deploy/secrets.enc.env` is fine and needs no exception: no
ignore file names it — it is encrypted, and written on the deployment host rather than carried
by any checkout — so nothing here flags it, and OPERATIONS.md's `cp` and `sops-edit` lines keep
working. Add a secret pattern there and it is guarded here on the next run.

Scope is what an operator can copy and run — fenced blocks in tracked Markdown, comment lines
in tracked YAML (a `.sops.yaml` header being nothing but instructions), and every line of a
tracked shell script, which is more literally a command an operator runs than any fenced block
is. Prose that merely *names* the old path (a changelog entry recording the move, say) is a
description, not an instruction, and does not fail.
"""

from __future__ import annotations

import re
import subprocess
from fnmatch import fnmatch
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
IGNORES = (".gitignore", ".dockerignore")  # .dockerignore lands with the build-context fix
DOCUMENTS = (".md", ".yaml", ".yml", ".sh")
SECRET = re.compile(r"(?:^|[^a-z])(key|secret|credential|pem)s?(?:[^a-z]|$)", re.I)
OUTSIDE = ("~", "$HOME", "/", "..")  # a path rooted here is not in the checkout
TOKEN = re.compile(r"[$~]?[\w.$/-]*[\w.*-]")  # a path-ish run, `$PWD/…` and `~/…` included


def secret_globs() -> set[str]:
    """The basename globs this repo's own ignore files call secrets."""
    globs: set[str] = set()
    for name in IGNORES:
        if not (path := ROOT / name).exists():
            continue  # not on every base; degrade rather than depend on another branch
        for line in path.read_text().splitlines():
            entry = line.split("#")[0].strip().lstrip("!/").rstrip("/")
            if entry and SECRET.search(base := entry.rsplit("/", 1)[-1]):
                globs.add(base)
    return globs


def instructions(text: str, suffix: str) -> list[tuple[int, str]]:
    """Numbered lines an operator would run: a whole script, a fence, or a config comment."""
    numbered = list(enumerate(text.splitlines(), 1))
    if suffix == ".sh":
        return numbered  # a shell script is commands top to bottom; it needs no fence
    if suffix != ".md":
        return [(n, line) for n, line in numbered if line.lstrip().startswith("#")]
    fenced, found = False, []
    for n, line in numbered:
        if line.lstrip().startswith("```"):  # indented fences count: lists carry them
            fenced = not fenced
        elif fenced:
            found.append((n, line))
    return found


def offending(line: str, globs: set[str]) -> list[str]:
    """Every token on the line naming an ignored-as-secret file at a path inside the repo."""
    written = []
    for token in TOKEN.findall(line):
        directory, _, base = token.rpartition("/")
        if any(fnmatch(base, glob) for glob in globs) and not directory.startswith(OUTSIDE):
            written.append(token)
    return written


def tracked_files(root: Path = ROOT) -> list[str]:
    """Every path git tracks here — the scan's scope, so nothing untracked is read."""
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, check=True
    )
    names = [name for name in listed.stdout.split("\0") if name]
    if gone := [name for name in names if not (root / name).is_file()]:
        pytest.fail(
            f"git tracks {gone} but the working tree has no such files — an uncommitted "
            "deletion, not a leak. Commit the deletion or restore the files; a raw "
            "FileNotFoundError mid-scan reads as a content failure and is not one."
        )
    return names


def test_the_scan_reaches_the_shell_scripts_an_operator_runs() -> None:
    scripts = [name for name in tracked_files() if name.endswith(".sh")]
    assert scripts, "no tracked shell script, so this guard's shell scope proves nothing"
    assert all(name.endswith(DOCUMENTS) for name in scripts), (
        f"{scripts} are commands an operator runs verbatim — more literal than any fenced"
        f" block — and DOCUMENTS is {DOCUMENTS}, so nothing reads them"
    )
    assert instructions("age-keygen -o deploy/age-key.txt\n", ".sh") == [
        (1, "age-keygen -o deploy/age-key.txt")
    ], "a shell script is commands top to bottom, not just its comment lines"


def test_no_document_tells_an_operator_to_write_a_key_into_the_checkout() -> None:
    globs = secret_globs()
    assert globs, f"no secret pattern in {IGNORES}: this guard has nothing to enforce"

    tracked = tracked_files()
    assert tracked, "git listed no tracked files, so this guard scanned nothing"

    leaks = [
        f"{name}:{number} writes {token!r} — {globs} are ignored as secrets, so a build or a"
        " commit that picks them up is a leak; generate it outside the checkout"
        for name in tracked
        if name.endswith(DOCUMENTS)
        for number, line in instructions((ROOT / name).read_text(), Path(name).suffix)
        for token in offending(line, globs)
    ]
    found = "\n".join(leaks)
    assert not leaks, f"a documented command puts a private key inside the repo:\n{found}"


def test_an_uncommitted_deletion_fails_as_itself(tmp_path: Path) -> None:
    """A tracked-but-deleted file fails as a deletion, not as whatever read it first."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "doomed.md").write_text("gone\n")
    subprocess.run(["git", "add", "doomed.md"], cwd=tmp_path, check=True)
    (tmp_path / "doomed.md").unlink()
    with pytest.raises(pytest.fail.Exception, match="uncommitted deletion"):
        tracked_files(tmp_path)
