"""Every mortal number in the prose is read back from the thing that decides it.

``docs/pmbok-mapping.md`` is already checked this way — its citations must name the symbol
they claim, its counts must be the catalog's own. The numbers in ``README.md``,
``docs/user-guide.md``, ``CLAUDE.md`` and ``requirements.lock``'s header had no such
grounding, and drifted exactly as an ungrounded number does: the performance floor claimed
counts several times the ceilings CI enforces, and ``CLAUDE.md`` cited a coverage floor at a
line that had moved. Each fact below is BUILT from the live constant and then looked for in
the prose, so moving the constant fails here, naming the sentence to fix, instead of leaving
a plausible wrong number in front of a reader.

A number nothing decides — how many files a snapshot run writes, how many tests pass — is
not restated in prose at all; that one is deleted rather than pinned, because no test can
keep it honest and every merge moves it.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import get_origin

import test_perf_commercial_volume as volume
from fastapi.routing import APIRoute

from driftless.api.app import LIST_LIMIT, LIST_LIMIT_MAX, app
from driftless.api.search import PER_KIND
from driftless.assess.feed import LOW_COMPLETENESS_THRESHOLD, STALE_AFTER_DAYS
from driftless.demo.data import demo_payload
from driftless.pmbok import catalog
from driftless.web.heatmap import HORIZON_WEEKS, MAX_HORIZON_WEEKS
from driftless.web.login import LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW, SESSION_TTL
from driftless.web.pages import THREATS_PER_PAGE

ROOT = Path(__file__).resolve().parents[1]
README, CLAUDE = ROOT / "README.md", ROOT / "CLAUDE.md"
GUIDE, AGENTS = ROOT / "docs" / "user-guide.md", ROOT / "docs" / "agent-guide.md"
LOCK, PYPROJECT = ROOT / "requirements.lock", ROOT / "pyproject.toml"

TASKS = volume.SMALL_TASKS_PER * volume.VOLUME * volume.N_PROJ
RISKS = volume.SMALL_RISKS_PER * volume.VOLUME * volume.N_PROJ
HOURS = int(SESSION_TTL.total_seconds() // 3600)
MINUTES = int(LOGIN_WINDOW.total_seconds() // 60)
BUSINESSES = demo_payload()["businesses"]
PROJECTS = [p for b in BUSINESSES for pf in b["portfolios"] for p in pf["projects"]]


def _flat(path: Path) -> str:
    """``path``'s prose on one line, so a phrase survives a re-wrap."""
    return " ".join(path.read_text().split())


# (document, the phrase the live values spell) — every number here is computed above.
FACTS = (
    # The performance floor states the ceilings it enforces, never a measurement: a
    # measured count moves with any honest read that lands, a ceiling is a decision.
    (
        README,
        f"`/` {volume.MAX_HOME_STMTS}, `/process-map` {volume.MAX_BUSINESS_MAP_STMTS}, "
        f"`/threats` {volume.MAX_THREATS_STMTS}",
    ),
    (README, f"({volume.N_PORTF} portfolios, {volume.N_PROJ} projects, {TASKS} tasks"),
    (README, f"{TASKS} baseline lines, {RISKS} risks)"),
    (README, f"({len(BUSINESSES)} businesses, a program, {len(PROJECTS)} projects"),
    (GUIDE, f"signed in for {HOURS} hours"),
    (GUIDE, f"{LOGIN_MAX_ATTEMPTS} failures in {MINUTES} minutes"),
    (GUIDE, f"{THREATS_PER_PAGE} cards a page"),
    (GUIDE, f"last status over {STALE_AFTER_DAYS} days old"),
    (GUIDE, f"completeness under {LOW_COMPLETENESS_THRESHOLD:.0%}"),
    (GUIDE, f"anything over {STALE_AFTER_DAYS} days old"),
    (GUIDE, f"{HORIZON_WEEKS} weeks by default, 1 to {MAX_HORIZON_WEEKS}"),
    (GUIDE, f"{PER_KIND} hits per kind"),
    (GUIDE, f"the {len(catalog.PROCESSES)} PMBOK processes"),
    (GUIDE, f"at most {LIST_LIMIT} rows"),
    (GUIDE, f"a `?limit=` above {LIST_LIMIT_MAX}"),
    # The agent guide states the same window. It is the machine-facing contract, so its copy is
    # derived from the same constants rather than retyped — a moved limit fails both guides.
    (AGENTS, f"at most {LIST_LIMIT} rows"),
    (AGENTS, f"a `?limit=` above {LIST_LIMIT_MAX}"),
)


def test_every_number_the_prose_states_is_the_live_one() -> None:
    stale = [
        f"{path.name} no longer states {phrase!r}"
        for path, phrase in FACTS
        if phrase not in _flat(path)
    ]
    assert not stale, "the code moved and the prose did not:\n" + "\n".join(stale)


def test_the_coverage_floor_is_cited_where_it_is_set_and_never_restated() -> None:
    """``CLAUDE.md`` and ``README.md`` send the reader to the setting instead of copying it.
    A floor copied into prose reads as a green suite that is not — both carried a number the
    setting had already left behind, one of them at a line reference that had moved too."""
    addopts = tomllib.loads(PYPROJECT.read_text())["tool"]["pytest"]["ini_options"]["addopts"]
    assert "--cov-fail-under=" in addopts, (
        "the floor left pyproject's addopts — CLAUDE.md and README.md cite it there"
    )
    for doc in (CLAUDE, README):
        cites = [line for line in doc.read_text().splitlines() if "cov-fail-under" in line]
        assert cites, f"{doc.name} stopped saying where the coverage floor lives"
        restated = [line for line in cites if re.search(r"\d", line)]
        assert not restated, f"{doc.name} restates the floor instead of citing it: {restated}"


def test_the_lock_header_agrees_with_pyproject_about_what_is_declared() -> None:
    """``requirements.lock``'s header explains WHY it pins packages pyproject does not
    declare. It named psycopg among them, and then named the ``dev`` extra; psycopg is a
    RUNTIME dependency, so which of the two it is has to be read, never remembered."""
    project = tomllib.loads(PYPROJECT.read_text())["project"]
    extras: list[str] = [d for group in project["optional-dependencies"].values() for d in group]

    def _names(reqs: list[str]) -> set[str]:
        return {re.split(r"[\[><=!~ ]", name)[0] for name in reqs}

    runtime, optional = _names(project["dependencies"]), _names(extras)
    assert "psycopg" in runtime, (
        f"psycopg left [project.dependencies] — the lock header says it lives there: {runtime}"
    )
    assert not {"uvicorn"} & (runtime | optional), "pyproject declares uvicorn now; say so"
    header = " ".join(
        line.lstrip("#").strip() for line in LOCK.read_text().splitlines() if line.startswith("#")
    )
    assert "uvicorn is pinned here although nothing declares it" in " ".join(header.split())
    assert "psycopg needs no such note: `[project.dependencies]`" in " ".join(header.split())


def test_every_query_a_list_endpoint_answers_is_named_in_a_guide() -> None:
    """The guides' query vocabulary is a claim about the router, so read it off the router
    rather than off an allowlist here — an allowlist is one more number to keep honest.
    ``?limit``/``?offset`` reached the API without a line in either guide, and a window no
    reader knows about returns a truncated list that looks like the whole of one.

    The **agent** guide has to carry every one of them. It is the API contract a machine reads,
    and a machine has no other page to fall back to; satisfying this from the user guide alone
    left ``?limit``/``?offset``/``?q`` undocumented for exactly the reader most likely to page
    through a list and least able to notice it was truncated. The user guide's own copy of the
    window is pinned separately, by the FACTS table above."""
    routes = [
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and "GET" in route.methods
        and get_origin(getattr(route, "response_model", None)) is list
    ]
    assert len(routes) >= 20, f"only {len(routes)} list routes found — the walk stopped seeing them"
    prose = _flat(AGENTS)
    taken = {param.name for route in routes for param in route.dependant.query_params}
    assert not (undocumented := sorted(n for n in taken if f"?{n}" not in prose)), (
        f"a list endpoint takes {undocumented} and the agent guide does not name it — document "
        "it in docs/agent-guide.md section 4 in the same change."
    )
