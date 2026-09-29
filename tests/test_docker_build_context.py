"""No operator secret can enter the container image, and the image still gets what it runs.

``docker compose up --build`` sends this whole directory to the daemon as the build
context, and an image layer is permanent — ``docker save`` recovers a file copied in even
after a later step deletes it. ``Dockerfile`` used to ``COPY deploy ./deploy`` while
``OPERATIONS.md`` had operators generate the deployment's age PRIVATE key at
``deploy/age-key.txt``, so a build on the operator's own machine baked the key that
decrypts ``deploy/secrets.enc.env`` — ``DRIFTLESS_SESSION_SECRET`` (forge any user's
cookie), ``DRIFTLESS_API_TOKEN``, ``POSTGRES_PASSWORD`` — into the image beside the
encrypted overlay. ``.gitignore`` named the key and did nothing: git's ignore rules have
no effect on a build context.

Both locks are checked without building anything — no ``COPY`` takes a whole directory a
secret can sit in, and ``.dockerignore`` excludes every secret pattern regardless — and
those patterns are *derived* from ``.gitignore``'s own secret section, so a new one added
there fails this suite until ``.dockerignore`` learns it too (the shape
``tests/test_deploy_env.py`` uses for the container's environment). A third check reads
the deployment files rather than the image: no tracked compose or CI file may *default* a
secret-bearing mount to a path inside the build context, because a default is the value
nobody typed — it survives every doc that moves the key out of the repository, and points
the deployment back at the one directory a build would bake. The last test runs the other
way: neither lock may take away a path the image needs. CI does build the image now — the
``docker-build`` job in ``.github/workflows/ci.yml`` runs on every pull request — so a
narrowed ``COPY`` no longer ships unnoticed; that job is the proof, and this test is the
faster and more specific report of the same break.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SERVICE = Path(__file__).resolve().parents[1]
GITIGNORE = SERVICE / ".gitignore"
DOCKERIGNORE = SERVICE / ".dockerignore"
DOCKERFILE = SERVICE / "Dockerfile"
COMPOSE = SERVICE / "docker-compose.yml"

# Every tracked file that can name a host path for a container to mount.
DEPLOYMENT_GLOBS = ("docker-compose.yml", "deploy/*.compose.yml", ".github/workflows/*.yml")

# ``${VAR:-value}`` — the fallback used when the operator exports nothing.
INTERPOLATION_DEFAULT = re.compile(r"\$\{[A-Za-z_]\w*:-([^}]*)\}")
# A bind source written out literally; Compose requires a relative one to start with a dot.
LITERAL_PATH = re.compile(r"(?<![\w$])\.{1,2}/[^\s:'\"}]+")

# A .gitignore section whose own comment says any of this hides something an attacker
# wants. Broad on purpose: a false positive costs a line in .dockerignore, a false
# negative costs the deployment's three secrets.
SECRETIVE = re.compile(r"secret|private|credential|password|token|\bkeys?\b|backup", re.I)

Rules = list[tuple[bool, re.Pattern[str]]]


def _sections(text: str) -> list[tuple[str, list[str]]]:
    """Blank-line-separated blocks of an ignore file: its comment, then its patterns."""
    sections = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        comment = " ".join(line.lstrip("#").strip() for line in lines if line.startswith("#"))
        patterns = [line for line in lines if not line.startswith("#")]
        if patterns:
            sections.append((comment, patterns))
    return sections


def secret_patterns() -> list[str]:
    """Every .gitignore pattern whose own section says it is hiding a secret."""
    return [
        pattern
        for comment, patterns in _sections(GITIGNORE.read_text(encoding="utf-8"))
        if SECRETIVE.search(comment)
        for pattern in patterns
    ]


def example_paths(pattern: str) -> list[str]:
    """Concrete build-context paths a .gitignore pattern matches — nested too, because a
    pattern with no internal slash matches at every depth: ``*.key`` must be excluded at
    ``deploy/x.key``, not only at the root."""
    body = pattern.strip().strip("/")
    concrete = body.replace("**/", "").replace("**", "x").replace("*", "x").replace("?", "x")
    if pattern.strip().endswith("/"):
        concrete = f"{concrete}/secret.txt"
    paths = [concrete]
    if "/" not in body:
        paths.append(f"deploy/{concrete}")
    return paths


def _segment(segment: str) -> str:
    return "".join(
        "[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char) for char in segment
    )


def _matcher(pattern: str) -> re.Pattern[str]:
    """An ignore/COPY pattern as a regex over context-relative paths (``**`` spans them)."""
    segments = pattern.strip().strip("/").split("/")
    regex = ""
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == "**":
            regex += "[^/]+(?:/[^/]+)*" if last else "(?:[^/]+/)*"
        else:
            regex += _segment(segment) + ("" if last else "/")
    return re.compile(regex)


def _self_and_parents(path: str) -> list[str]:
    parts = path.split("/")
    return ["/".join(parts[: index + 1]) for index in range(len(parts))]


def dockerignore_rules() -> Rules:
    """``(negated, matcher)`` in file order — the last rule that matches decides."""
    text = DOCKERIGNORE.read_text(encoding="utf-8") if DOCKERIGNORE.exists() else ""
    return [
        (line.startswith("!"), _matcher(line.lstrip("!")))
        for line in (raw.strip() for raw in text.splitlines())
        if line and not line.startswith("#")
    ]


def excluded(path: str, rules: Rules) -> bool:
    """Docker's rule: last match wins, and an excluded directory takes its contents along."""
    verdict = False
    for negated, matcher in rules:
        if any(matcher.fullmatch(candidate) for candidate in _self_and_parents(path)):
            verdict = not negated
    return verdict


def deployment_files() -> list[Path]:
    """Tracked compose and CI files, the ones that can mount a host path into a container."""
    return sorted(
        {path for glob in DEPLOYMENT_GLOBS for path in SERVICE.glob(glob) if path.is_file()}
    )


def mount_sources(text: str) -> list[tuple[int, str]]:
    """``(line number, host path)`` for every mount source a deployment file names."""
    return [
        (number, value)
        for number, line in enumerate(text.splitlines(), 1)
        for value in INTERPOLATION_DEFAULT.findall(line) + LITERAL_PATH.findall(line)
    ]


def inside_the_build_context(value: str) -> str | None:
    """The context-relative path a mount source names, or ``None`` if it points outside it."""
    value = value.strip().strip("\"'")
    if value.startswith(("/", "~", "$", "../")) or "/" not in value:
        return None  # absolute, the operator's home, another variable, above us, or a volume name
    return value[2:] if value.startswith("./") else value


def _instructions() -> list[tuple[str, str]]:
    """``(INSTRUCTION, arguments)`` from the Dockerfile, line continuations joined."""
    text = re.sub(r"\\\n\s*", " ", DOCKERFILE.read_text(encoding="utf-8"))
    lines = (line.strip() for line in text.splitlines())
    return [
        (line.split(maxsplit=1)[0].upper(), line.split(maxsplit=1)[1].strip())
        for line in lines
        if line and not line.startswith("#") and len(line.split(maxsplit=1)) == 2
    ]


def _relative(word: str) -> str:
    return word[2:] if word.startswith("./") else word


def _copies() -> list[tuple[list[str], str]]:
    """``(sources, destination)`` for every COPY/ADD that reads the build context."""
    copies = []
    for head, rest in _instructions():
        if head not in {"COPY", "ADD"} or "--from=" in rest:
            continue  # a stage-to-stage copy never touches the context
        words = [word for word in rest.split() if not word.startswith("--")]
        if len(words) >= 2:
            copies.append(([_relative(word) for word in words[:-1]], words[-1]))
    return copies


def carries(source: str, path: str) -> bool:
    """Would ``COPY <source>`` bring a build-context file at ``path`` into the image?"""
    if source in {".", "", "/"}:
        return True
    matcher = _matcher(source)
    return any(matcher.fullmatch(candidate) for candidate in _self_and_parents(path))


def image_paths() -> dict[str, str]:
    """Absolute path inside the image -> the context path that supplies it."""
    workdir = next((rest for head, rest in _instructions() if head == "WORKDIR"), "/")
    supplied = {}
    for sources, destination in _copies():
        for source in sources:
            target = destination
            if not target.startswith("/"):
                target = f"{workdir.rstrip('/')}/{_relative(target)}"
            if destination.endswith("/") or _relative(destination) in {"", "."}:
                target = f"{target.rstrip('/')}/{Path(source).name}"
            target = re.sub("/+", "/", target)
            supplied[target] = source
            # A copied directory supplies every file under it — how the image used to get
            # deploy/entrypoint.sh, and everything else in deploy/ with it.
            for child in sorted(path for path in (SERVICE / source).rglob("*") if path.is_file()):
                relative = child.relative_to(SERVICE / source).as_posix()
                supplied[f"{target}/{relative}"] = f"{source}/{relative}"
    return supplied


def test_the_secret_patterns_come_from_gitignores_own_secret_section() -> None:
    """A parser that silently found nothing would make every check below vacuous."""
    patterns = secret_patterns()
    assert "deploy/age-key.txt" in patterns, (
        "the .gitignore section holding the age private key is no longer being found, so "
        f"the checks below are testing nothing; parsed: {patterns}"
    )
    assert all(example_paths(pattern) for pattern in patterns)


def test_no_copy_takes_a_whole_directory_a_secret_can_sit_in() -> None:
    """The first lock: name the files, so no .dockerignore is needed to be safe."""
    offenders = [
        f"`COPY {source}` would carry {path} (.gitignore: {pattern})"
        for sources, _ in _copies()
        for source in sources
        for pattern in secret_patterns()
        for path in example_paths(pattern)
        if carries(source, path)
    ]
    assert not offenders, (
        "the Dockerfile copies a directory an operator keeps secrets in, so a build on the "
        "operator's own machine bakes them into a permanent image layer that `docker save` "
        f"recovers: {offenders}. Copy the files the image runs, by name."
    )


def test_every_secret_pattern_in_gitignore_is_excluded_from_the_build_context() -> None:
    """The second lock: whatever git hides because it is a secret, Docker must not see."""
    rules = dockerignore_rules()
    missing = [
        f"{path} (.gitignore: {pattern})"
        for pattern in secret_patterns()
        for path in example_paths(pattern)
        if not excluded(path, rules)
    ]
    assert not missing, (
        ".gitignore hides these because they are secrets, but .dockerignore lets them into "
        "the Docker build context, where any COPY that reaches them puts them in an image "
        f"layer for good: {missing}. Add the pattern to .dockerignore."
    )


def test_no_deployment_file_mounts_a_secret_from_inside_the_build_context() -> None:
    """The third lock: a mount source may not name a path git hides as a secret.

    ``.dockerignore`` keeps such a file out of the image; this keeps the *deployment* from
    asking for one there. Both matter, because a compose default that still reads
    ``./deploy/age-key.txt`` is an instruction to put the key back in the build context —
    where the next `COPY` that widens, or the next machine without the ignore file, bakes
    it in. Secret-bearing is ``.gitignore``'s own judgement, so a new pattern there covers
    the compose file too.
    """
    files = deployment_files()
    assert COMPOSE in files, (
        f"docker-compose.yml is not being scanned, so this tests nothing: {files}"
    )
    rules: Rules = [(False, _matcher(pattern)) for pattern in secret_patterns()]
    offenders = sorted(
        {
            f"{path.relative_to(SERVICE)}:{number} mounts {relative}"
            for path in files
            for number, value in mount_sources(path.read_text(encoding="utf-8"))
            if (relative := inside_the_build_context(value)) and excluded(relative, rules)
        }
    )
    assert not offenders, (
        "a deployment file names a host path that .gitignore hides as a secret and that sits "
        f"inside the Docker build context: {offenders}. Keep the operator's key outside the "
        "repository and require the variable — a default nobody typed points at the one "
        "directory a build would bake it from."
    )


def test_neither_lock_takes_away_a_path_the_image_needs() -> None:
    """Narrowing a COPY or widening an ignore breaks the build. The docker-build job in CI
    catches that too, by failing; this names the file and the rule that took it away."""
    rules, sources = dockerignore_rules(), [s for srcs, _ in _copies() for s in srcs]
    for source in sources:
        assert (SERVICE / source).exists(), f"the Dockerfile copies {source}, which is absent"
        assert not excluded(source, rules), (
            f".dockerignore excludes {source}, which the Dockerfile copies — the build dies "
            "with 'file not found in build context'"
        )
    script = json.loads(next(rest for head, rest in _instructions() if head == "ENTRYPOINT"))[0]
    assert script in image_paths(), (
        f"{script} is the image's ENTRYPOINT but no COPY puts it there, so every container "
        f"exits before uvicorn starts; the Dockerfile copies {sources}"
    )
