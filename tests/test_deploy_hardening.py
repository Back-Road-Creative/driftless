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
SERVICE = re.compile(r"^  (\S+):$")
EVENT = re.compile(r"^  ([a-z_]+):")
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\ssrc=)", re.I)
SIZE = re.compile(r"^\d+[mg]$")
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


def services(path: Path) -> dict[str, list[str]]:
    """Each service's own lines, keyed by name — by indentation, under ``services:`` only."""
    blocks: dict[str, list[str]] = {}
    current: list[str] | None = None
    in_services = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line[:1] not in (" ", "", "#"):
            in_services, current = line.rstrip() == "services:", None
        elif in_services and (match := SERVICE.match(line)):
            current = blocks.setdefault(match.group(1), [])
        elif current is not None:
            current.append(line)
    return blocks


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
    runners = runs_on(UPTIME)
    assert runners and "self-hosted" not in runners, (
        f"a probe sharing a box with the service goes quiet in the outage it reports: {runners}"
    )


def test_an_untrusted_pull_request_never_reaches_a_machine_we_own() -> None:
    """A pull request is somebody else's code, and anyone may open one. On a self-hosted
    runner it executes on a box the maintainer owns — GitHub's fork-approval default only
    holds until a contributor's first merge, so that is a code-execution path, not a
    theory. ``workflow_call`` counts too: a reusable workflow runs on whatever event
    started its caller, and both callers here are pull-request triggered."""
    untrusted = {"pull_request", "pull_request_target", "workflow_call"}
    checked = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        if not triggers(path) & untrusted:
            continue
        runners = runs_on(path)
        assert runners, f"{path.name}: no runs-on parsed, so this guard checked nothing"
        assert not [name for name in runners if "self-hosted" in name], (
            f"{path.name} runs {runners} on an event anyone can start. Use a GitHub-hosted "
            f"runner; self-hosted is only for work no untrusted event reaches."
        )
        checked.append(path.name)
    assert len(checked) >= 2, f"only {checked} parsed as untrusted-triggered — the scan slipped"


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
