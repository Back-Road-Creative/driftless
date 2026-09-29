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
from test_web_routes_not_shadowed import _included, _leaves, _shape

from driftless.api.app import app
from driftless.api.crud import LIST_LIMIT, LIST_LIMIT_MAX
from driftless.api.search import PER_KIND
from driftless.assess.feed import LOW_COMPLETENESS_THRESHOLD, STALE_AFTER_DAYS
from driftless.demo.data import demo_payload
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok import catalog
from driftless.web.heatmap import HORIZON_WEEKS, MAX_HORIZON_WEEKS
from driftless.web.login import LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW, SESSION_TTL
from driftless.web.threat_board import THREATS_PER_PAGE

ROOT = Path(__file__).resolve().parents[1]
README, CLAUDE = ROOT / "README.md", ROOT / "CLAUDE.md"
GUIDE, AGENTS = ROOT / "docs" / "user-guide.md", ROOT / "docs" / "agent-guide.md"
GATES = ROOT / "docs" / "testing-and-quality-gates.md"
ARCH = ROOT / "docs" / "architecture.md"
LOCK, PYPROJECT = ROOT / "requirements.lock", ROOT / "pyproject.toml"
GATES_SH = ROOT / "bin" / "driftless-gates.sh"
BASE_HTML = ROOT / "driftless" / "web" / "templates" / "base.html"
HOME_HTML = ROOT / "driftless" / "web" / "templates" / "home.html"

#: The prose spells small counts as words. Spelling them here from the live value keeps
#: the derivation one-way — the constant decides, the word follows — rather than adding a
#: second place a reader could change a number without the code moving.
WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")

#: What the technique pages may promise a reader, and the hedge that keeps it true
#: while any technique in the registry carries no clause.
CLAUSE_PROMISE = "the PMBOK-6 clause it comes from"
CLAUSE_HEDGE = "where the edition defines one"

TASKS = volume.SMALL_TASKS_PER * volume.VOLUME * volume.N_PROJ
RISKS = volume.SMALL_RISKS_PER * volume.VOLUME * volume.N_PROJ
HOURS = int(SESSION_TTL.total_seconds() // 3600)
MINUTES = int(LOGIN_WINDOW.total_seconds() // 60)
BUSINESSES = demo_payload()["businesses"]
PROJECTS = [p for b in BUSINESSES for pf in b["portfolios"] for p in pf["projects"]]
PROCESSES = len(catalog.PROCESSES)
#: The home page's KPI row, counted off the template that renders it.
TILES = HOME_HTML.read_text(encoding="utf-8").count("tiles.tile(")


def _flat(path: Path) -> str:
    """``path``'s prose on one line, so a phrase survives a re-wrap."""
    return " ".join(path.read_text().split())


# (document, the phrase the live values spell) — every number here is computed above.
FACTS = (
    # The performance floor states the ceilings it enforces, never a measurement: a
    # measured count moves with any honest read that lands, a ceiling is a decision.
    (
        GATES,
        f"`/` {volume.MAX_HOME_STMTS}, `/process-map` {volume.MAX_BUSINESS_MAP_STMTS}, "
        f"`/threats` {volume.MAX_THREATS_STMTS}",
    ),
    (GATES, f"({volume.N_PORTF} portfolios, {volume.N_PROJ} projects, {TASKS} tasks"),
    (GATES, f"{TASKS} baseline lines, {RISKS} risks)"),
    # Followed the prose out of README.md into docs/architecture.md, which is the whole
    # point of the check below: the claim is pinned to wherever the sentence lives now.
    (ARCH, f"({len(BUSINESSES)} businesses, a program, {len(PROJECTS)} projects"),
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
    # docs/architecture.md restated measured numbers with nothing reading any of
    # them back, while the IDENTICAL sentences in the user guide were pinned here. The
    # mechanism was not missing, it was simply never applied to this file; a document
    # that describes what each part guarantees is the last place a wrong number should
    # be able to sit. Each phrase below is long enough to name ONE sentence, so a moved
    # constant fails pointing at the line to edit rather than at the file.
    (
        ARCH,
        f"the {PROCESSES} processes as a stateless knowledge-area × process-group grid. "
        "**Primary nav.**",
    ),
    (
        ARCH,
        f"the {PROCESSES} processes as a stateless knowledge-area × process-group grid "
        "straight from the frozen catalog",
    ),
    (ARCH, f"the {PROCESSES}-process grid with each process's computed"),
    (ARCH, f"reference model of all {PROCESSES} PMBOK-6"),
    (ARCH, f"on each of the {PROCESSES} processes from those artifacts"),
    (ARCH, f"one statement and {PER_KIND} hits per kind"),
    (ARCH, f"stale status past {STALE_AFTER_DAYS} days"),
    # The heatmap's horizon, spelled as the prose spells it: the default, the count of
    # columns after the as-of's own week, the ceiling, and the first value past it that
    # the page refuses.
    (ARCH, f"own week and the {WORDS[HORIZON_WEEKS - 1]} after it"),
    (ARCH, f"{WORDS[HORIZON_WEEKS].capitalize()} stays the answer"),
    (ARCH, f"**{MAX_HORIZON_WEEKS} is the ceiling**"),
    (ARCH, f"quietly serving {WORDS[HORIZON_WEEKS]} instead"),
    (ARCH, f"0, {MAX_HORIZON_WEEKS + 1} or 5000 answer the designed 404 page"),
    # The user guide counts the home page's KPI tiles; home.html decides how many there
    # are. A tile added or dropped fails here rather than leaving the count behind.
    (GUIDE, f"{WORDS[TILES].capitalize()} tiles:"),
)


def test_every_number_the_prose_states_is_the_live_one() -> None:
    stale = [
        f"{path.name} no longer states {phrase!r}"
        for path, phrase in FACTS
        if phrase not in _flat(path)
    ]
    assert not stale, "the code moved and the prose did not:\n" + "\n".join(stale)


def test_the_coverage_floor_is_cited_where_it_is_set_and_never_restated() -> None:
    """Every doc that mentions the floor sends the reader to the setting instead of copying it.
    A floor copied into prose reads as a green suite that is not — two of these carried a number
    the setting had already left behind, one of them at a line reference that had moved too.

    ``docs/testing-and-quality-gates.md`` joined the list when the CI narrative moved there out
    of ``README.md``: the guard has to follow the prose, or relocating a section is enough to
    leave the restated-floor defect ungated in its new home while the old home still passes.
    """
    addopts = tomllib.loads(PYPROJECT.read_text())["tool"]["pytest"]["ini_options"]["addopts"]
    assert "--cov-fail-under=" in addopts, (
        "the floor left pyproject's addopts — CLAUDE.md, README.md and the gates doc cite it there"
    )
    for doc in (CLAUDE, README, GATES):
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


PAGE_BULLET = re.compile(r"^- `GET (\S+)`")  # a page line opens with the address it serves
NAV_LINK = re.compile(r'nav_link\("([^"]+)"')  # the macro's own definition names no path
NAV_MARK = "**Primary nav.**"


def _registered_pages() -> set[str]:
    """Every GET path the included page routers put on the live app, as parameter
    *shapes* (``/projects/{}/hub``) — the same normalisation
    ``tests/test_web_routes_not_shadowed.py`` applies, so the doc is free to name a
    parameter whatever reads best (``{id}``, ``{slug}``)."""
    registered = {
        _shape(str(getattr(leaf, "path", "")))
        for route in app.routes
        for child in _included(route) or ()
        for leaf in _leaves(child)
        if "GET" in (getattr(leaf, "methods", None) or ())
    }
    assert len(registered) >= 20, f"only {len(registered)} page routes walked — the walk broke"
    return registered


def _page_inventory() -> dict[str, str]:
    """``docs/architecture.md``'s ``## Pages`` list, read as {path shape: its bullet}.

    Scoped to that section's own ``- ``-prefixed lines, and to the code span each one
    OPENS with, never to code spans anywhere else. The rest of the file is prose about
    modules, symbols, API endpoints and CLI invocations, all written in backticks; a
    check that harvested those as addresses could only be made to pass by an ignore
    list, which rots exactly like the restated numbers this module exists to prevent.
    A bullet that opens ``- `GET /path` `` is instead a shape only a page line has, so
    the address set is unambiguous and nothing else in the document can join or leave
    it by accident.
    """
    text = ARCH.read_text(encoding="utf-8")
    _, _, rest = text.partition("\n## Pages\n")
    # Named rather than indexed, so a renamed heading reports what it is -- the list
    # this test exists to read is gone -- rather than an IndexError somewhere below.
    assert rest, (
        "docs/architecture.md has no '## Pages' heading — the inventory moved or was renamed"
    )
    section = rest.split("\n## ")[0]
    listed: dict[str, str] = {}
    current = ""
    for line in section.splitlines():
        if line.startswith("- "):
            match = PAGE_BULLET.match(line)
            assert match, f"a ## Pages bullet does not open with a `GET /path` span: {line!r}"
            current = _shape(match.group(1).split("?")[0])
            listed[current] = line
        elif current and line.startswith("  "):
            # A bullet is free to wrap; its whole text is one entry, so a mark on the
            # second line counts exactly as it reads.
            listed[current] += " " + line.strip()
        else:
            current = ""
    assert listed, "the ## Pages inventory names no page at all — vacuous, not passing"
    return listed


def test_every_page_the_app_registers_is_named_in_the_architecture_inventory() -> None:
    """``docs/architecture.md``'s ``## Pages`` list claims to be the inventory of every
    page, so read the inventory off the router instead of trusting the claim. The technique
    library shipped two routes and a primary-nav entry with no line in it, and so had five
    other pages before them — a page nobody wrote down is a page nobody reviews.
    """
    assert not (unlisted := sorted(_registered_pages() - set(_page_inventory()))), (
        f"architecture.md's ## Pages inventory names no page at {unlisted} — add it there in "
        "the same change that mounts it, marking it Primary nav if the nav links it."
    )


def test_every_page_the_architecture_inventory_names_is_actually_served() -> None:
    """The other direction, which nothing checked while the first one shipped: an
    inventory that may name a page no route serves is an inventory a reader cannot
    trust either way. A mutation audit proved both halves of that were live — adding
    ``/ghost-page`` to the document, and un-mounting the real ``/techniques`` while the
    document still named it, each left the suite green. A phantom address is worse than
    a missing one: a missing page is invisible, a phantom is a promise that 404s.
    """
    registered = _registered_pages()
    assert not (phantom := sorted(set(_page_inventory()) - registered)), (
        f"architecture.md's ## Pages inventory names {phantom}, which no route serves — "
        "a reader following that address gets a 404. Remove the line, or mount the page."
    )


def test_the_inventory_marks_exactly_the_pages_the_primary_nav_links() -> None:
    """Each bullet's nav status is a second copy of a fact ``base.html`` already holds, so
    it is walked rather than argued: every path the nav macro links carries the mark, and
    every marked path is one the nav links. A nav entry added or dropped fails here."""
    linked = set(NAV_LINK.findall(BASE_HTML.read_text(encoding="utf-8")))
    assert linked, "no nav_link call found in base.html — the nav moved, the walk is vacuous"
    marked = {path for path, bullet in _page_inventory().items() if NAV_MARK in bullet}
    assert marked == linked, (
        f"the ## Pages inventory marks {sorted(marked)} as primary nav and base.html links "
        f"{sorted(linked)} — say {NAV_MARK!r} on exactly the pages the nav links."
    )


def test_no_doc_promises_a_clause_that_every_technique_does_not_carry() -> None:
    """Some techniques carry no ``further_reading``: PMBOK-6 defines them in narrative or as
    an umbrella group with no numbered clause, some are Driftless extensions the edition
    never names at all, and some carry a clause nobody could confirm
    (``tests/test_technique_totality.py:UNCITED_EXEMPTIONS`` holds the reason for each,
    and how many there are).  Blanking a citation nobody could confirm is the decision; prose that
    promises a reader a clause on every technique page quietly reverses it.

    The check runs both ways off the live registry, so neither wording can outlive its
    fact: while any technique is uncited the promise must be hedged, and once every one of
    them is cited the hedge must come out.
    """
    uncited = sorted(
        key for key, definition in TECHNIQUES.items() if not definition.further_reading
    )
    docs = (
        sorted((ROOT / "docs").glob("*.md"))
        + sorted((ROOT / "changelog.d").glob("*.md"))
        # The router module says the same sentence to the next reader of the code, and
        # said it unhedged until this guard reached it. Prose is prose wherever it lives.
        + [ROOT / "driftless" / "web" / "techniques.py"]
    )
    promising = [doc for doc in docs if CLAUSE_PROMISE in _flat(doc)]
    hedged = [doc for doc in docs if CLAUSE_HEDGE in _flat(doc)]
    if uncited:
        assert not (bare := sorted(d.name for d in promising if d not in hedged)), (
            f"{bare} promise {CLAUSE_PROMISE!r} on every technique page, and {len(uncited)} "
            f"carry no clause ({uncited}) — say {CLAUSE_HEDGE!r} instead of overclaiming."
        )
    else:
        assert not hedged, (
            f"every technique is cited now, so {[d.name for d in hedged]} may drop "
            f"{CLAUSE_HEDGE!r} and promise the clause outright."
        )


#: The gate runner's own argument parser, read as the set of flags it accepts. A ``case``
#: arm may hold several patterns (``-h|--help``), so each arm is split before it counts.
FLAG_ARM = re.compile(r"^\s*(-[-\w|]+)\)", re.MULTILINE)
#: How the README inventories a flag: one runnable invocation line per flag, in the
#: fenced block under ``## Development``. A flag mentioned only in the prose around that
#: block does not count — the block is the list a reader copies from.
README_FLAG = re.compile(r"^bin/driftless-gates\.sh\s+(--[\w-]+)", re.MULTILINE)


def _accepted_flags() -> set[str]:
    """Every long flag ``bin/driftless-gates.sh`` accepts, off its own ``case`` block."""
    body = GATES_SH.read_text(encoding="utf-8")
    _, _, rest = body.partition('for arg in "$@"; do')
    assert rest, "driftless-gates.sh no longer parses arguments in a for/case block"
    arms = rest.split("\ndone")[0]
    flags = {
        flag for arm in FLAG_ARM.findall(arms) for flag in arm.split("|") if flag.startswith("--")
    }
    assert len(flags) >= 5, f"only {sorted(flags)} parsed — the case block changed shape"
    return flags


def test_the_readme_names_every_flag_the_gate_runner_accepts() -> None:
    """The README's Development section is a second copy of that ``case`` block, and it
    fell behind it: ``--migrations``, ``--docker-build`` and ``--no-audit`` were live
    flags no line of the README mentioned, while the sentence that did mention
    ``--migrations`` called it opt-in and told the reader to point an environment
    variable the script never reads at a database it starts itself.

    So the copy is walked instead of argued. Both directions: a flag the script gains is
    undocumented until the README names it, and a flag the README shows is a flag the
    script must still accept — a documented flag that has been removed exits 1 on
    ``unknown argument`` for whoever copies the line.
    """
    accepted = _accepted_flags()
    prose = README.read_text(encoding="utf-8")
    named = set(README_FLAG.findall(prose))
    assert not (undocumented := sorted(accepted - named)), (
        f"bin/driftless-gates.sh accepts {undocumented} and the README names none of them "
        "— document each in the same change that adds it."
    )
    assert not (phantom := sorted(named - accepted)), (
        f"the README shows {phantom}, which the script rejects as an unknown argument "
        "— it was renamed or removed; fix the README line."
    )
