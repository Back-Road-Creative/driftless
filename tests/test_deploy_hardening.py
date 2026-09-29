"""The deployment surface: response headers, resource ceilings, and a way to be told.

Three ways this service could be up and failing with nothing here to say so. The proxy
passed every response through untouched, so a browser applied no transport pin, no
MIME-sniff brake and no framing rule to pages that render stored user text. Neither
compose file put a ceiling on anything, so one login's 16 MiB scrypt hash times however
many are in flight is a host-wide event. And the only alarm fires on a red nightly CI
run, which says nothing about whether the deployed service answered at 2am. Read by
hand, not parsed, for tests/test_deploy_healthcheck.py's reason: no PyYAML dependency.

The last two guards are about a different surface — publication. This repository is
readable by people who are not the maintainer, so neither its CI nor its prose may hand
a reader the maintainer's own machine.
"""

from __future__ import annotations

import json
import re
import shlex
import tomllib
from pathlib import Path

from test_docs_health_truthfulness import tracked_markdown

ROOT = Path(__file__).resolve().parents[1]
CADDYFILE = ROOT / "deploy" / "Caddyfile"
COMPOSE, PROXY = ROOT / "docker-compose.yml", ROOT / "deploy" / "proxy.compose.yml"
SOPS, AUDIT_IGNORE = ROOT / ".sops.yaml", ROOT / ".pip-audit-ignore"
SECRETS = ROOT / "deploy" / "secrets.enc.env"
WORKFLOWS = ROOT / ".github" / "workflows"
UPTIME = WORKFLOWS / "uptime-check.yml"
TEMPLATES = ROOT / "driftless" / "web" / "templates"
PLACEHOLDER = "age1REPLACE_WITH_THE_DEPLOYMENT_AGE_PUBLIC_KEY"
# An entry's name line, which may end in a comment: `  web:` or `  build:  # why`.
SERVICE = re.compile(r"^  ([^\s#:]+):\s*(?:#.*)?$")
EVENT = re.compile(r"^  ([a-z_]+):")
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\ssrc=)", re.I)
SIZE = re.compile(r"^\d+[mg]$")
# Where this tree is published, and the one shape a `runs-on:` may take to differ by
# repository: a GitHub-hosted label there, a self-hosted label list everywhere else.
PUBLIC_REPOSITORY = "Back-Road-Creative/driftless"
PER_REPOSITORY_RUNNER = re.compile(
    r"^\$\{\{ github\.repository == '(?P<repo>[\w./-]+)' && '(?P<public>[\w.-]+)'"
    r" \|\| fromJSON\('(?P<private>\[[^\]]*\])'\) \}\}$"
)
# The other `runs-on:` shapes the runner guard reads: one label, or a one-line label list.
PLAIN_RUNNER = re.compile(r"^(?:[\w.-]+|\[[^\]\n]*\])$")
# (what a document must not contain, what publishing it hands a reader). Named by shape
# rather than by literal, so the guard does not carry the disclosure it exists to stop.
CONTROL_PLANE = (
    (re.compile(r"sudo\s+\S*merge"), "a privileged local command that merges here"),
    (re.compile(r"/var/log/"), "where that command's audit log sits on the host"),
    (re.compile(r"no branch[- ]protection", re.I), "which repository protections are off"),
    # An escrow example must stay a `<placeholder>`: naming the vault, the folder and the
    # item is target selection for the age key every deployment secret decrypts with.
    (re.compile(r'DRIFTLESS_KEY_ESCROW="(?![^"\n]*<)'), "a real place a private key is kept"),
)


def response_headers() -> dict[str, str]:
    """Header name (lowercased) -> value, out of the site block's ``header`` directive."""
    lines = CADDYFILE.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("{$DRIFTLESS_PUBLIC_HOST}"))
    inside, headers = False, {}
    for line in lines[start + 1 :]:
        text = line.strip()
        if text == "}" and line == text:  # the site block closed, at column zero
            break
        if text.startswith("header") and text.endswith("{"):
            inside = True
        elif inside and text == "}":
            inside = False
        elif inside and text and not text.startswith("#"):
            name, *value = shlex.split(text)
            headers[name.lower()] = " ".join(value)
    return headers


def entries_under(path: Path, key: str) -> dict[str, list[str]]:
    """Each entry's own lines under the top-level ``key:``, keyed by name, by indentation."""
    blocks: dict[str, list[str]] = {}
    current: list[str] | None = None
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line[:1] not in (" ", "", "#"):
            inside, current = line.rstrip() == f"{key}:", None
        elif inside and (match := SERVICE.match(line)):
            current = blocks.setdefault(match.group(1), [])
        elif current is not None:
            current.append(line)
    return blocks


def services(path: Path) -> dict[str, list[str]]:
    """Each service's own lines, keyed by name — by indentation, under ``services:`` only."""
    return entries_under(path, "services")


def runner_in(value: str, repository: str) -> str:
    """What a job's ``runs-on:`` value asks for when the workflow runs in ``repository``,
    in the ``[a, b]`` spelling a literal label list is written in."""
    match = PER_REPOSITORY_RUNNER.match(value)
    if not match:
        return value
    if repository == match["repo"]:
        return match["public"]
    return "[" + ", ".join(json.loads(match["private"])) + "]"


def runner_offences(path: Path) -> list[str]:
    """Jobs that would ask the public repository for a runner it cannot reach, or ask this
    repository for one it is refused. A job-level ``if:`` excluding (or naming only) the
    public repository takes that side out of the question; a step-level one does not."""
    offences = []
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line[:1] not in (" ", "", "#"):
            inside = line.rstrip() == "jobs:"
        elif inside and re.match(r"^  [^\s#]", line) and not SERVICE.match(line):
            # entries_under() would drop this job unseen; the guard refuses it instead.
            offences.append(f"{path.name}: the runner guard cannot read the job line {line!r}")
    for job, lines in entries_under(path, "jobs").items():
        declared = [
            line.split(":", 1)[1].strip() for line in lines if line.startswith("    runs-on:")
        ]
        guards = [line.strip() for line in lines if line.startswith("    if:")]
        if not declared:
            # A reusable-workflow call runs wherever its callee says; the callee is a
            # workflow here and is checked on its own, or is the org's and is hosted.
            if not any(line.startswith("    uses:") for line in lines):
                offences.append(f"{path.name}:{job} declares no runs-on and calls no workflow")
            continue
        value = declared[0]
        if not (PER_REPOSITORY_RUNNER.match(value) or PLAIN_RUNNER.match(value)):
            # A block list, a runner-group mapping, a matrix expression: resolving it here
            # would be a guess, so the job fails until the guard learns the shape.
            offences.append(f"{path.name}:{job} has a runs-on the guard cannot read: {value!r}")
            continue
        public = runner_in(value, PUBLIC_REPOSITORY)
        private = runner_in(value, "a private copy")
        if (
            f"if: github.repository != '{PUBLIC_REPOSITORY}'" not in guards
            and "self-hosted" in public
        ):
            offences.append(f"{path.name}:{job} asks the public repository for {public}")
        if (
            f"if: github.repository == '{PUBLIC_REPOSITORY}'" not in guards
            and "self-hosted" not in private
        ):
            offences.append(f"{path.name}:{job} asks this repository for {private}")
    return offences


def runs_on(path: Path) -> list[str]:
    """Every ``runs-on:`` value a workflow declares, in file order."""
    return [
        line.split(":", 1)[1].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("runs-on:")
    ]


def triggers(path: Path) -> set[str]:
    """The event names under a workflow's own ``on:`` block, by indentation."""
    events: set[str] = set()
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line[:1] not in (" ", "", "#"):
            inside = line.rstrip() == "on:"
        elif inside and (match := EVENT.match(line)):
            events.add(match.group(1))
    return events


def test_the_site_block_sets_the_headers_a_browser_needs_to_be_told() -> None:
    """Caddy adds none itself; the policy is pinned to what the templates load, since
    one the app violates gets switched off."""
    headers = response_headers()
    hsts = headers.get("strict-transport-security", "")
    assert int(re.sub(r"\D", "", hsts.split(";")[0]) or 0) >= 31536000, (
        f"no year-long HSTS, so the first request of every visit is still http: {headers}"
    )
    assert headers.get("x-content-type-options") == "nosniff", headers
    assert headers.get("x-frame-options") == "DENY", headers
    policy = headers.get("content-security-policy", "")
    assert "default-src 'self'" in policy and "frame-ancestors 'none'" in policy, (
        f"without a policy, text an operator stored has the run of the origin: {policy!r}"
    )
    assert "style-src 'self' 'unsafe-inline'" in policy, (
        f"base.html holds the palette in <style> and templates use style=: {policy!r}"
    )
    inline = [p.name for p in TEMPLATES.glob("*.html") if INLINE_SCRIPT.search(p.read_text())]
    assert not inline, (
        f"{inline} carry an inline <script> this policy blocks: the page would lose its "
        f"behaviour in a browser and nowhere else — put it under static/ instead"
    )


def test_every_service_declares_a_memory_ceiling() -> None:
    """One runaway container must not take the host, and everything else running on it."""
    for path in (COMPOSE, PROXY):
        blocks = services(path)
        assert blocks, f"{path.name}: no services parsed, so this guard checked nothing"
        for name, body in blocks.items():
            limits = [line.split(":", 1)[1].strip() for line in body if "mem_limit:" in line]
            assert limits, f"{path.name}: {name} has no mem_limit; its worst minute is the host's"
            assert SIZE.match(limits[0]), f"{path.name}: {name} mem_limit {limits[0]!r}"


def test_the_placeholder_recipient_is_a_gate_not_a_default() -> None:
    """An unreplaced age recipient must be impossible to deploy past, and must say so."""
    text = SOPS.read_text(encoding="utf-8")
    if PLACEHOLDER not in text:
        return  # a real recipient is in place: the step this guards has been done
    assert not SECRETS.exists(), (
        "deploy/secrets.enc.env exists while .sops.yaml still names the placeholder "
        "recipient — sops cannot have encrypted to it, so that file is plaintext"
    )
    comments = "\n".join(line for line in text.splitlines() if line.lstrip().startswith("#"))
    assert "REQUIRED" in comments, (
        "the placeholder reads like a default: say in the file that replacing it is "
        "required before the first deployment"
    )


def test_the_deployment_config_describes_this_service_and_its_dependencies() -> None:
    """Pre-rename copy is stale copy: it dates the file and mis-states what is here."""
    for path in (SOPS, AUDIT_IGNORE):
        assert "pmhub" not in path.read_text(encoding="utf-8").lower(), (
            f"{path.name} still names svc-pmhub, the name this service was renamed from"
        )
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = declared["project"]["dependencies"]
    assert dependencies, "pyproject declares nothing, so this guard has nothing to compare"
    assert "no runtime dependencies" not in AUDIT_IGNORE.read_text(encoding="utf-8"), (
        f"the ignore list still says this project declares no runtime dependencies while "
        f"pyproject declares {len(dependencies)}; a reader takes its advice on trust"
    )


def test_a_service_that_stops_answering_pages_someone() -> None:
    """Docker's `unhealthy` restarts nothing and tells nobody; CI only watches CI."""
    assert UPTIME.exists(), (
        "no out-of-band uptime check: the only alarm here fires on a red nightly CI run, "
        "so a 2am outage of the deployed service reaches nobody until someone visits it"
    )
    text = UPTIME.read_text(encoding="utf-8")
    assert "schedule:" in text and "cron:" in text, "an uptime check nobody runs is a script"
    assert "/health" in text, "probe /health: it asks the database, so an outage fails it"
    assert "scheduled-failure-alert.yml" in text and "if: failure()" in text, (
        "a red run with no reader is a log line, not an alarm: call the alert workflow"
    )
    # A probe off the service's box was the ideal; this org buys no GitHub-hosted
    # minutes, so a hosted probe was refused in seconds on every run since
    # 2026-08-28 and paged nobody. The pool is the only runner there is: require
    # it, and require the workflow to say out loud what that cannot cover. The
    # `quick` label keeps a one-request probe off the runners that also carry the
    # heavy test lanes, where a bare `self-hosted` could land it behind a suite.
    runners = runs_on(UPTIME)
    assert runners == ["[self-hosted, quick]"], (
        f"the probe must run on the self-hosted quick pool — a hosted job never starts "
        f"here, and a bare self-hosted one can queue behind a heavy suite: {runners}"
    )
    assert "both dead is the case only an outside probe can cover" in text, (
        "a self-hosted probe shares its fate with the service's box; the workflow must record "
        "that limitation where the next reader will see it"
    )


def test_a_secret_bearing_trigger_never_reaches_a_machine_we_own() -> None:
    """``pull_request_target`` on a self-hosted runner is a code-execution path in ANY
    repository, and that is what this still forbids.

    This guard used to ban self-hosted runners for plain ``pull_request`` too, reasoning
    that "a pull request is somebody else's code, and anyone may open one." That is correct
    wherever anyone can open one. It does not bind here: this repository is private and
    single-maintainer, with no outside collaborators, so no untrusted party can start a
    workflow at all. A sibling private repository in the same organization already runs its
    CI on those same self-hosted runners on that reasoning.

    ``pull_request_target`` is a different animal and keeps the ban. It runs in the BASE
    repository's context with access to its secrets while checking out the pull request's
    code, so a self-hosted runner there hands a fork's code both the maintainer's machine and
    the repository's credentials. Nothing about being private or single-maintainer changes
    that — the day a collaborator is added, that trigger is immediately a live path.

    **The precondition, which is the reason this was narrowed rather than deleted.** If this
    repository ever gains an outside collaborator or becomes public, plain ``pull_request`` on
    a self-hosted runner becomes exactly the code-execution path the old absolute described,
    and this decision has to be revisited. That condition cannot be read from the source tree
    — repository visibility and collaborator lists live in GitHub's API, not in this
    checkout — so it is recorded here rather than asserted. A deleted test would have carried
    neither the rule nor the tripwire.

    This tree IS published, to a public repository, and there the precondition holds. That
    side is asserted, not recorded: test_the_public_repository_never_asks_for_a_runner_it_
    cannot_reach below fails any job that would run on a self-hosted runner there.
    """
    checked = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        if "pull_request_target" not in triggers(path):
            continue
        runners = runs_on(path)
        assert runners, f"{path.name}: no runs-on parsed, so this guard checked nothing"
        assert not [name for name in runners if "self-hosted" in name], (
            f"{path.name} runs {runners} on pull_request_target, which carries this "
            f"repository's secrets while checking out a fork's code. Use a GitHub-hosted "
            f"runner, or drop the trigger."
        )
        checked.append(path.name)
    # No workflow uses pull_request_target today, so `checked` is legitimately empty and this
    # test is a tripwire for the trigger being introduced, not a check on current files. The
    # scan itself is proven by test_the_secret_bearing_trigger_guard_can_fail below, which
    # runs it against a constructed workflow — without that, an empty sweep here would be
    # indistinguishable from a broken one.
    assert not checked or all(isinstance(name, str) for name in checked)


def test_the_secret_bearing_trigger_guard_can_fail(tmp_path: Path) -> None:
    """The guard above passes vacuously while no workflow uses ``pull_request_target``, so
    prove the scan actually rejects the thing it exists to reject. Builds the offending
    workflow in a temp directory and runs the same two parsers over it."""
    offender = tmp_path / "attack.yml"
    offender.write_text(
        "on:\n  pull_request_target:\n\njobs:\n  build:\n    runs-on: self-hosted\n",
        encoding="utf-8",
    )
    assert "pull_request_target" in triggers(offender), "the trigger parser missed it"
    assert [name for name in runs_on(offender) if "self-hosted" in name], (
        "the runner parser missed a self-hosted runner, so the guard above could not fail"
    )


def test_the_public_repository_never_asks_for_a_runner_it_cannot_reach() -> None:
    """This tree is published to a public repository, where anyone may open a pull request
    and no org runner group admits the repository. A self-hosted job there is a stranger's
    code on the maintainer's machine if it ever ran, and until then a check that never
    starts: the release pull request there would wait on queued jobs forever. So every job
    either resolves to a GitHub-hosted runner there (free for a public repository) or does
    not run there. Here the org buys no hosted minutes and a hosted job is refused in
    seconds, so every job that runs here asks for the self-hosted pool."""
    offences: list[str] = []
    checked: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        offences += runner_offences(path)
        checked += [f"{path.name}:{job}" for job in entries_under(path, "jobs")]
    assert "ci.yml:test" in checked, f"the job parser found no ci.yml test job: {checked}"
    assert not offences, "\n".join(offences)


def test_the_runner_guard_can_fail(tmp_path: Path) -> None:
    """The guard above is only as good as its parsers, so each offence it exists to catch is
    built here and must be caught, and the one sanctioned shape must pass."""
    per_repository = (
        "${{ github.repository == 'Back-Road-Creative/driftless' && 'ubuntu-latest'"
        ' || fromJSON(\'["self-hosted", "heavy"]\') }}'
    )
    skip_public = "    if: github.repository != 'Back-Road-Creative/driftless'\n"
    only_public = "    if: github.repository == 'Back-Road-Creative/driftless'\n"
    build = "  build:\n"
    cases = {
        "bare pool": (f"{build}    runs-on: [self-hosted, heavy]\n", ["public"]),
        "hosted everywhere": (f"{build}    runs-on: ubuntu-latest\n", ["this repository"]),
        "step-level skip": (
            f"{build}    runs-on: [self-hosted, heavy]\n    steps:\n      - run: true\n"
            "        if: github.repository != 'Back-Road-Creative/driftless'\n",
            ["public"],
        ),
        "no runner at all": (f"{build}    steps:\n      - run: true\n", ["no runs-on"]),
        "per-repository": (f"{build}    runs-on: {per_repository}\n", []),
        "pool, skipped there": (f"{build}    runs-on: [self-hosted, heavy]\n{skip_public}", []),
        # A line the parsers cannot read fails the guard; it never drops out of it.
        "commented job name": (
            "  build:  # the build\n    runs-on: [self-hosted, heavy]\n",
            ["public"],
        ),
        "flow-mapping job": ("  build: {runs-on: [self-hosted, heavy]}\n", ["cannot read"]),
        "block-list runner": (
            f"{build}    runs-on:\n      - self-hosted\n      - heavy\n",
            ["cannot read"],
        ),
        "block list, public only": (
            f"{build}{only_public}    runs-on:\n      - self-hosted\n",
            ["cannot read"],
        ),
        "runner group": (f"{build}    runs-on:\n      group: Default\n", ["cannot read"]),
        "matrix runner": (f"{build}    runs-on: ${{{{ matrix.os }}}}\n", ["cannot read"]),
    }
    for name, (jobs, expected) in cases.items():
        workflow = tmp_path / f"{name.replace(' ', '-').replace(',', '')}.yml"
        workflow.write_text(f"on:\n  pull_request:\n\njobs:\n{jobs}", encoding="utf-8")
        found = runner_offences(workflow)
        assert len(found) == len(expected), (name, found)
        for offence, words in zip(found, expected, strict=True):
            assert words in offence, (name, offence)


def test_no_published_document_describes_the_maintainers_control_plane() -> None:
    """The engineering content is for whoever reads this repository. How the maintainer's
    own machine is driven is not: the privileged command that lands a merge, where its
    audit log sits, and which repository protections are switched off together describe
    the controls rather than the code. Say a pull request merges on green; say it once."""
    documents = tracked_markdown()
    assert documents, "git listed no tracked markdown, so this guard scanned nothing"
    leaked: list[str] = []
    for name in documents:
        text = (ROOT / name).read_text(encoding="utf-8")
        for pattern, what in CONTROL_PLANE:
            if found := pattern.search(text):
                leaked.append(f"{name}:{text[: found.start()].count(chr(10)) + 1} publishes {what}")
    assert not leaked, "operator-only detail in a document anyone can read:\n" + "\n".join(leaked)
