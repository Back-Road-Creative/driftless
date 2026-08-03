"""The shipped image installs the version set CI and the audit actually scanned.

``requirements.lock`` says in its own header that it keeps "the Tests job, the audit, and
the Docker image on one set of versions instead of three independent 'latest at run time'
resolutions". Two of those three were true: ``.github/workflows/ci.yml`` and
``.github/workflows/pip-audit.yml`` install with ``--constraint requirements.lock``. The
Dockerfile did not, and never copied the file into the build at all — so with every
dependency in ``pyproject.toml`` declared ``>=``, a green audit was a statement about
whatever pip resolved on the audit runner that morning, not about the artefact an operator
runs. Nothing in the suite noticed, because nothing in the suite read the lock.

A pin closed half of that. It decides which release to ask for and says nothing about what
the index returned, so the image now installs from ``requirements-runtime.txt`` under
``--require-hashes``: a committed sha256 per distribution, and a build that fails rather than
accepting a substitute. The project itself cannot join that install — pip refuses to hash a
directory — so it arrives on a second line with ``--no-deps``, which is load-bearing rather
than tidy: without it that line would re-resolve every dependency from the index, unhashed,
and undo the first. ``requirements-runtime.txt`` is compiled under ``-c requirements.lock``,
which is what keeps one version set across the image, the Tests job and the audit; the tests
below fail if the two files drift apart, if a pin loses its digest, or if the name list the
hashed file is compiled from stops matching ``[project.dependencies]`` plus uvicorn.

These read the shipped files rather than a container: no daemon is assumed and no
image is built. The requirements file must be in the image for the install to name, and
the image may not install the ``[dev]``
extra — pytest, xdist, coverage and httpx are CVE surface a server never executes. The
base image is pinned by digest for the same reason the packages are: ``python:3.12-slim``
is a moving tag, so two builds of one commit are two different images. The last test is
the deployment half of the login throttle: behind ``deploy/proxy.compose.yml``'s Caddy,
uvicorn sees the proxy's address as ``request.client.host`` for every request unless it is
told which hop to trust, and a per-address throttle keyed on one shared address locks out
every user at once.

The `sops` tests are the same argument about a program rather than a package. The build
fetched the release binary over the network and ``chmod``ed it unread, and that binary is
what ``deploy/entrypoint.sh`` runs to decrypt ``DRIFTLESS_SESSION_SECRET``,
``DRIFTLESS_API_TOKEN`` and ``POSTGRES_PASSWORD`` at start — so whatever the download
returned became the program holding the deployment's secrets. The digest is checked
*before* ``chmod``, not after: a binary that is made executable and then inspected has
already been trusted for one step.
"""

from __future__ import annotations

import ipaddress
import json
import re
import shlex
import tomllib
from pathlib import Path

from test_docker_build_context import _instructions, image_paths

SERVICE = Path(__file__).resolve().parents[1]
LOCK = SERVICE / "requirements.lock"
RUNTIME_IN = SERVICE / "requirements-runtime.in"
RUNTIME_TXT = SERVICE / "requirements-runtime.txt"

# `name==version`, extras and environment markers tolerated, so a `>=` line is a mismatch
# rather than an unparsed line the test silently skips.
REQUIREMENT = re.compile(r"^(?P<name>[\w.-]+)(?:\[[^\]]+\])?(?P<op>[=<>!~]+)(?P<version>\S+)$")
TAKES_A_VALUE = {"-c", "--constraint", "-r", "--requirement", "--index-url", "--extra-index-url"}
# The release the image fetches sops from, and a sha256 as `sha256sum -c` and the project's
# published `sops-v<version>.checksums.txt` both spell it.
SOPS_RELEASE = "getsops/sops/releases"
DIGEST = re.compile(r"\b[0-9a-f]{64}\b")


def canonical(name: str) -> str:
    """PEP 503 normalisation: `psycopg[binary]` and `Psycopg_Binary` are comparable."""
    return re.sub(r"[-_.]+", "-", name.split("[")[0]).lower()


def requirement_name(spec: str) -> str:
    """The package a requirement string names, extras, specifier and marker discarded.

    `pyproject.toml` writes `psycopg[binary]>=3.1` and `requirements-runtime.in` writes
    `psycopg[binary]`; comparing those as written makes a list that matches read as a list
    that has drifted, which is the way this kind of test gets deleted instead of fixed.
    """
    return canonical(re.split(r"[\[<>=!~;\s]", spec, maxsplit=1)[0])


def workdir() -> str:
    return next((rest for head, rest in _instructions() if head == "WORKDIR"), "/").rstrip("/")


def pip_installs() -> list[list[str]]:
    """Every `pip install` the Dockerfile runs, as argv with continuations already joined."""
    commands = []
    for head, rest in _instructions():
        if head != "RUN":
            continue
        for part in re.split(r"&&|\|\||;", rest):
            words = shlex.split(part)
            if words[:2] == ["pip", "install"] or words[1:4] == ["-m", "pip", "install"]:
                commands.append(words)
    return commands


def required_by(argv: list[str]) -> list[str]:
    """Each requirements file an install names, whichever spelling of the flag it uses."""
    paths = [word.split("=", 1)[1] for word in argv if word.startswith("--requirement=")]
    paths += [
        argv[index + 1] for index, word in enumerate(argv[:-1]) if word in {"-r", "--requirement"}
    ]
    return paths


def hashed_runtime() -> dict[str, tuple[str, list[str]]]:
    """``requirements-runtime.txt`` as {package: (version, digests)}.

    uv writes one logical requirement across several physical lines — the pin, then a
    backslash-continued ``--hash`` per distribution — so the continuations are joined before
    anything is parsed. A pin whose hashes were dropped has to read as *no digests*, not as
    an unparsed line the loop skips: that is the failure this file exists to catch.
    """
    text = RUNTIME_TXT.read_text(encoding="utf-8").replace("\\\n", " ")
    pins: dict[str, tuple[str, list[str]]] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        head, *rest = line.split()
        match = REQUIREMENT.fullmatch(head)
        assert match and match["op"] == "==", (
            f"requirements-runtime.txt has {head!r}, which is not an exact `==` pin — a range "
            "cannot be hash-verified, because the hash belongs to one distribution"
        )
        pins[canonical(match["name"])] = (
            match["version"],
            [word for word in rest if word.startswith("--hash=")],
        )
    return pins


def installed(argv: list[str]) -> list[str]:
    """The requirement arguments of an install — its flags and their values removed."""
    names, skip = [], False
    for word in argv[2:]:
        if skip:
            skip = False
        elif word.startswith("-"):
            skip = word in TAKES_A_VALUE
        else:
            names.append(word)
    return names


def lock_pins() -> dict[str, str]:
    pins = {}
    for number, raw in enumerate(LOCK.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = REQUIREMENT.fullmatch(line)
        assert match and match["op"] == "==", (
            f"requirements.lock:{number} is {line!r}, not an exact `==` pin — a range in a "
            "constraint file lets the image, CI and the audit resolve three different builds"
        )
        pins[canonical(match["name"])] = match["version"]
    return pins


def test_every_image_install_is_hash_verified_or_resolves_nothing() -> None:
    """A version pin says which release to fetch, never what the index returned.

    Two shapes are legitimate here and no third is. An install that names a requirements
    file must pass ``--require-hashes``, and that file must be COPYed or the build fails at
    ``pip install``. An install of the checkout itself must pass ``--no-deps``: pip refuses
    a directory under ``--require-hashes``, so the project is installed separately, and
    without ``--no-deps`` that second line would resolve the whole dependency set again —
    from the index, unhashed — and quietly undo the first.
    """
    installs = pip_installs()
    assert installs, "no `pip install` was parsed out of the Dockerfile, so this tests nothing"
    supplied, base = image_paths(), workdir()
    for argv in installs:
        paths = required_by(argv)
        if paths:
            assert "--require-hashes" in argv, (
                f"`{shlex.join(argv)}` installs from {paths} without --require-hashes, so pip "
                "accepts whatever the index serves for those pins and the committed digests "
                "gate nothing"
            )
            for path in paths:
                absolute = path if path.startswith("/") else f"{base}/{path}"
                assert absolute in supplied, (
                    f"the install passes -r {path}, which no COPY puts in the image: the build "
                    "fails at `pip install`. Copy it by name, as pyproject.toml is."
                )
        else:
            assert installed(argv) == ["."] and "--no-deps" in argv, (
                f"`{shlex.join(argv)}` installs {installed(argv)} with neither -r nor "
                "--no-deps, so it resolves dependencies from the index at build time and the "
                "hashed set above stops being what the container has"
            )


def test_the_hashed_file_carries_a_digest_for_every_distribution_it_pins() -> None:
    """One unhashed line disables nothing loudly — pip only checks what is written down."""
    unhashed = [name for name, (_, digests) in hashed_runtime().items() if not digests]
    assert not unhashed, (
        f"requirements-runtime.txt pins {unhashed} with no --hash, so --require-hashes fails "
        "the build. Recompile with --generate-hashes rather than hand-editing a pin in."
    )


def test_the_hashed_runtime_set_and_requirements_lock_name_one_version() -> None:
    """pip-audit installs under requirements.lock and reports on what it got. If the image
    installs a different version of anything, the audit's green tick describes a container
    nobody ships — the exact failure the lock was introduced to end, one file further on."""
    pins, runtime = lock_pins(), hashed_runtime()
    disagree = {
        name: (pins[name], version)
        for name, (version, _) in runtime.items()
        if name in pins and pins[name] != version
    }
    assert not disagree, (
        f"requirements-runtime.txt and requirements.lock disagree (lock, runtime): {disagree}. "
        "Recompile the runtime file with `-c requirements.lock` — the constraint is what keeps "
        "the image, the Tests job and the audit on one resolution."
    )
    missing = sorted(set(runtime) - set(pins))
    assert not missing, (
        f"the image installs {missing}, which requirements.lock does not pin, so pip-audit "
        "never scans the version the container actually runs"
    )


def test_the_runtime_input_is_pyprojects_runtime_set_plus_uvicorn() -> None:
    """The hashed file is compiled from a list of names, and a list of names goes stale in
    silence: a dependency added to pyproject.toml and forgotten here vanishes from the image
    (``--no-deps`` installs the project without it) and surfaces as an ImportError at start."""
    declared = tomllib.loads((SERVICE / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    expected = {requirement_name(spec) for spec in declared["dependencies"]} | {"uvicorn"}
    listed = {
        requirement_name(line)
        for raw in RUNTIME_IN.read_text(encoding="utf-8").splitlines()
        if (line := raw.split("#", 1)[0].strip())
    }
    assert listed == expected, (
        f"requirements-runtime.in lists {sorted(listed)}; pyproject.toml's runtime set plus "
        f"uvicorn is {sorted(expected)}. Reconcile the two and recompile the hashed file — "
        "uvicorn is here because the image runs it and pyproject deliberately does not declare it."
    )


def test_the_image_installs_no_test_tooling() -> None:
    """`.[dev]` shipped pytest, pytest-xdist, coverage and httpx into production."""
    offenders = [
        f"`{shlex.join(argv)}` requests {name}"
        for argv in pip_installs()
        for name in installed(argv)
        if "dev" in re.findall(r"\[([^\]]*)\]", name)
    ]
    assert not offenders, (
        f"the image installs the dev extra: {offenders}. A test runner in a production image "
        "is CVE surface with nothing running it — install the runtime set, and name any "
        "runtime dependency the extra was carrying (psycopg) explicitly."
    )


def test_the_lock_still_pins_the_server_the_image_runs() -> None:
    """uvicorn is in no ``[project.dependencies]``, so only the lock keeps the audit on it."""
    pins = lock_pins()
    assert "uvicorn" in pins, f"requirements.lock parsed to {sorted(pins)} — it lost uvicorn"


def sops_steps() -> list[str]:
    """The `&&`-separated steps of the RUN that fetches sops, continuations already joined."""
    runs = [rest for head, rest in _instructions() if head == "RUN" and SOPS_RELEASE in rest]
    assert len(runs) == 1, (
        f"{len(runs)} RUN instructions fetch sops; this reads the one that does, so a second "
        "download would go unchecked"
    )
    return [step.strip() for step in runs[0].split("&&") if step.strip()]


def step_index(steps: list[str], *needles: str) -> int:
    return next((i for i, step in enumerate(steps) if all(n in step for n in needles)), -1)


def test_the_sops_binary_is_checksum_verified_before_it_is_made_executable() -> None:
    """An unverified download became the program that decrypts every deployment secret."""
    steps = sops_steps()
    download, verify = step_index(steps, "curl", SOPS_RELEASE), step_index(steps, "sha256sum")
    executable = step_index(steps, "chmod", "sops")
    assert verify != -1, (
        "the build curls the sops binary and never checks what it got. deploy/entrypoint.sh "
        "runs that binary to decrypt DRIFTLESS_SESSION_SECRET, DRIFTLESS_API_TOKEN and "
        "POSTGRES_PASSWORD, so a swapped release asset replaces the program that handles "
        "them. Pin the digest the release publishes and `sha256sum -c` it."
    )
    assert -1 < download < verify < executable, (
        f"the sops steps run in the order {steps}. The checksum has to be checked after the "
        "download and BEFORE chmod — verifying a binary that is already executable trusts it "
        "for one step first, and the RUN must fail on mismatch rather than ship it."
    )


def test_the_pinned_sops_digest_is_a_real_one() -> None:
    """A guessed or placeholder digest is a gate that reports on nothing."""
    steps = sops_steps()
    digests = {digest for step in steps for digest in DIGEST.findall(step)}
    assert len(digests) == 1, (
        f"the sops fetch names {sorted(digests)} — exactly one sha256 belongs here, the "
        "linux.amd64 line of the release's own sops-v<version>.checksums.txt"
    )
    digest = digests.pop()
    assert len(set(digest)) > 4, (
        f"{digest} is a placeholder, not a digest. A checksum nobody read off the release "
        "fails every build or, worse, is quietly weakened later to make one pass."
    )
    assert "/latest/" not in " ".join(steps), (
        "a digest can only pin a download that is itself pinned; /latest/download/ moves to "
        "the next release and breaks the build the day it ships"
    )


def test_the_base_image_is_pinned_by_digest() -> None:
    """`python:3.12-slim` is a tag that moves; a digest is the image a commit was tested on."""
    bases = [rest for head, rest in _instructions() if head == "FROM"]
    assert bases, "no FROM was parsed out of the Dockerfile"
    for base in bases:
        assert re.search(r"@sha256:[0-9a-f]{64}\b", base), (
            f"FROM {base} names a floating tag, so rebuilding one commit produces a different "
            "image and the interpreter, OpenSSL and system libraries the audit assumed are "
            "not the ones that ship. Pin `<tag>@sha256:<digest>`."
        )


def test_the_container_trusts_only_private_hops_for_forwarded_headers() -> None:
    """Behind the shipped Caddy, every request otherwise arrives from the proxy's address."""
    cmd = json.loads(next(rest for head, rest in _instructions() if head == "CMD"))
    assert "--proxy-headers" in cmd, (
        "the CMD ignores X-Forwarded-For, so behind deploy/proxy.compose.yml every request "
        "carries the proxy's container address: the login throttle in driftless/web/login.py "
        "is keyed on that one address and locks out every user at once"
    )
    flags = [word for word in cmd if word.startswith("--forwarded-allow-ips")]
    assert flags, (
        "--proxy-headers without --forwarded-allow-ips trusts 127.0.0.1 only, which the "
        "proxy container never is, so the forwarded address is silently discarded"
    )
    value = flags[0].partition("=")[2] or cmd[cmd.index(flags[0]) + 1]
    assert value != "*", (
        "--forwarded-allow-ips=* believes X-Forwarded-For from anyone, so any client can "
        "spend another user's throttle budget or hide its own address from the request log"
    )
    hops = [ipaddress.ip_network(entry.strip(), strict=False) for entry in value.split(",")]
    assert hops and all(hop.is_private for hop in hops), (
        f"--forwarded-allow-ips={value} trusts a public range; only the compose network's "
        "own addresses can be a legitimate hop in front of a loopback-published API"
    )
