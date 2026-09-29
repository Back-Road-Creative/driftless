"""One shared "Related" block, starting with a Method process page:
``for_process``, built once over the frozen registries already in the tree
(``pmbok.graph.GRAPH``, ``pmbok.definitions.TECHNIQUES``,
``pmbok.artifact_definitions.ARTIFACTS``, ``pmbok.methods.METHODS``,
``pmbok.glossary.GLOSSARY``) rather than a second copy of any of them. Pure
and deterministic — no store, no clock, no request. A group with nothing in
it is omitted.

``for_artifact``, ``for_technique``, ``for_practice`` and ``for_term`` are
adopted on ``/artifacts/{slug}``, ``/techniques/{slug}``, ``/methods/{key}`` and
``/glossary``; ``for_process`` on ``/pmbok/{id}`` and ``for_theory_index`` on
``/pmbok`` — every helper below now backs a page.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from driftless.naming import technique_slug
from driftless.pmbok import catalog
from driftless.pmbok.artifact_definitions import ARTIFACTS
from driftless.pmbok.crosswalk import EQUIVALENCES
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.glossary import GLOSSARY
from driftless.pmbok.graph import GRAPH
from driftless.pmbok.methods import METHODS
from driftless.pmbok.process_definitions import PROCESS_DEFINITIONS
from driftless.web.templating import artifact_slug


@dataclass(frozen=True)
class RelatedLink:
    """One related item: the word a reader sees, and the page it goes to."""

    label: str
    href: str


@dataclass(frozen=True)
class RelatedGroup:
    """One titled group of :class:`RelatedLink`. Never empty."""

    title: str
    links: tuple[RelatedLink, ...]


@dataclass(frozen=True)
class Related:
    """Every non-empty group for one page, in the order its caller built them."""

    groups: tuple[RelatedGroup, ...]


def _group(title: str, items: Iterable[tuple[str, str]]) -> RelatedGroup | None:
    links = tuple(RelatedLink(label, href) for label, href in items)
    return RelatedGroup(title, links) if links else None


def _built(groups: Iterable[RelatedGroup | None]) -> Related:
    return Related(tuple(g for g in groups if g is not None))


def _href(kind: str, key: str) -> str:
    """A process/technique/artifact/method/glossary key as its page's address —
    the one place every kind's URL formula lives for this module."""
    if kind == "process":
        return f"/pmbok/{key}"
    if kind == "technique":
        return f"/techniques/{technique_slug(key)}"
    if kind == "artifact":
        return f"/artifacts/{artifact_slug(key)}"
    if kind == "method":
        return f"/methods/{key}"
    return f"/glossary#{key}"


def _node_link(node_id: str) -> tuple[str, str]:
    """One ``GRAPH`` node id as ``(label, href)``."""
    kind, _, key = node_id.partition(":")
    if kind == "process":
        return catalog.get(key).name, _href(kind, key)
    if kind == "technique":
        return TECHNIQUES[key].display_name, _href(kind, key)
    return ARTIFACTS[key].display_name, _href(kind, key)


def _edge_ids(node_id: str, kind: str, *, outgoing: bool) -> list[str]:
    """Every neighbour id ``node_id`` has a ``kind`` edge to (outgoing) or from."""
    if outgoing:
        return [e.target for e in GRAPH.edges if e.source == node_id and e.kind == kind]
    return [e.source for e in GRAPH.edges if e.target == node_id and e.kind == kind]


def _map_group(node_id: str) -> RelatedGroup:
    return RelatedGroup("Map", (RelatedLink("See it on the map", f"/map?focus={node_id}"),))


def _practices_crosswalking(target: str) -> list[tuple[str, str]]:
    """``(label, href)`` for every method practice whose crosswalk names
    ``target`` — a process id or a technique key."""
    return [
        (f"{method.display_name}: {practice.display_name}", _href("method", method.key))
        for method in METHODS.values()
        for practice in method.practices
        if target in practice.crosswalk
    ]


#: Every ``GLOSSARY`` term, longest first, so a shorter term never claims a
#: match belonging to a longer one containing it — rebuilt here rather than
#: imported from ``driftless.web.templating``'s ``gloss`` filter, which is
#: the same pattern behind a module-private name.
_TERM_PATTERN = (
    re.compile(
        r"\b(?:"
        + "|".join(re.escape(e.term) for e in sorted(GLOSSARY.values(), key=lambda e: -len(e.term)))
        + r")\b",
        re.IGNORECASE,
    )
    if GLOSSARY
    else None
)
_KEY_BY_TERM_LOWER = {e.term.lower(): key for key, e in GLOSSARY.items()}


def _glossary_group(text: str) -> RelatedGroup | None:
    """Every glossary term mentioned in ``text``, first-seen order, as its own
    "Glossary terms" group."""
    if _TERM_PATTERN is None:
        return None
    seen: list[str] = []
    for match in _TERM_PATTERN.finditer(text):
        key = _KEY_BY_TERM_LOWER[match.group(0).lower()]
        if key not in seen:
            seen.append(key)
    return _group("Glossary terms", ((GLOSSARY[k].term, _href("glossary", k)) for k in seen))


def for_process(process_id: str) -> Related:
    """The Related block for ``/pmbok/{process_id}``."""
    definition = PROCESS_DEFINITIONS[process_id]
    process = definition.process
    node_id = f"process:{process_id}"
    text = " ".join(
        [
            process.name,
            definition.plain_summary,
            definition.why_bother,
            definition.done_when,
            definition.first_time_tip,
        ]
    )
    same_area = [p for p in catalog.PROCESSES if p.area == process.area and p.id != process_id]
    same_group = [p for p in catalog.PROCESSES if p.group == process.group and p.id != process_id]
    return _built(
        [
            _group("Feeds", (_node_link(n) for n in _edge_ids(node_id, "feeds", outgoing=True))),
            _group("Fed by", (_node_link(n) for n in _edge_ids(node_id, "feeds", outgoing=False))),
            _group("Same knowledge area", ((p.name, _href("process", p.id)) for p in same_area)),
            _group("Same process group", ((p.name, _href("process", p.id)) for p in same_group)),
            _group(
                "Techniques", (_node_link(n) for n in _edge_ids(node_id, "used_by", outgoing=False))
            ),
            _group(
                "Artifacts produced",
                (_node_link(n) for n in _edge_ids(node_id, "produces", outgoing=True)),
            ),
            _group(
                "Artifacts used",
                (_node_link(n) for n in _edge_ids(node_id, "reads", outgoing=False)),
            ),
            _group("Agile practices", _practices_crosswalking(process_id)),
            _glossary_group(text),
            _map_group(node_id),
        ]
    )


#: Every method practice by its own key, which is unique across the whole
#: registry (``tests/test_methods.py``), paired with the method it belongs to.
_PRACTICE_BY_KEY = {
    practice.key: (method, practice) for method in METHODS.values() for practice in method.practices
}


def _practice_href(method_key: str, practice_key: str) -> str:
    """One practice as its address: the ``<dt id>`` its method page gives it."""
    return f"/methods/{method_key}#{practice_key}"


def _whole_map_group() -> RelatedGroup:
    """The Map group for a page with nothing of its own on the graph — a
    guide-only practice, a term no registry field says — so every page reaches
    the map rather than dropping the group and looking like an omission."""
    return RelatedGroup("Map", (RelatedLink("See the whole map", "/map"),))


def _run(*values: str | tuple[str, ...]) -> str:
    """Registry fields as one text run to search for glossary terms."""
    return " ".join(v if isinstance(v, str) else " ".join(v) for v in values)


def _build_term_index() -> dict[str, list[str]]:
    """Every glossary key -> the ids of the registry entries whose own words say
    it, in registry order. Built ONCE at import over the frozen registries, not
    per request: a term's block is the reverse of the ``gloss`` link every other
    page already writes, and walking five registries for each of 33 terms on
    every render would be the same answer computed again."""
    sources = [
        (
            f"process:{key}",
            _run(
                d.process.name,
                d.plain_summary,
                d.why_bother,
                d.done_when,
                d.first_time_tip,
                d.worked_example,
                d.pitfalls,
            ),
        )
        for key, d in PROCESS_DEFINITIONS.items()
    ]
    sources += [
        (
            f"technique:{key}",
            _run(t.display_name, t.summary, t.when_to_use, t.when_to_avoid, t.steps, t.outputs),
        )
        for key, t in TECHNIQUES.items()
    ]
    sources += [
        (
            f"artifact:{key}",
            _run(a.display_name, a.plain_summary, a.why_it_matters, a.what_it_looks_like_here),
        )
        for key, a in ARTIFACTS.items()
    ]
    sources += [
        (f"practice:{key}", _run(practice.display_name, practice.plain_summary))
        for key, (_, practice) in _PRACTICE_BY_KEY.items()
    ]
    index: dict[str, list[str]] = {key: [] for key in GLOSSARY}
    for node_id, text in sources:
        group = _glossary_group(text)
        for link in group.links if group else ():
            index[link.href.removeprefix("/glossary#")].append(node_id)
    return index


_TERM_INDEX = _build_term_index()


def for_practice(practice_key: str) -> Related:
    """The Related block for one practice on ``/methods/{method}``: what its
    crosswalk names, the techniques and artifacts those processes work with, and
    the method's other practices of the same kind."""
    method, practice = _PRACTICE_BY_KEY[practice_key]
    crosswalked = [
        f"process:{key}" if key in PROCESS_DEFINITIONS else f"technique:{key}"
        for key in practice.crosswalk
    ]
    neighbours: list[str] = []
    for node_id in (n for n in crosswalked if n.startswith("process:")):
        for kind, outgoing in (("used_by", False), ("produces", True), ("reads", False)):
            for neighbour in _edge_ids(node_id, kind, outgoing=outgoing):
                if neighbour not in neighbours and neighbour not in crosswalked:
                    neighbours.append(neighbour)
    siblings = [p for p in method.practices if p.kind is practice.kind and p.key != practice_key]
    return _built(
        [
            _group("Crosswalked to", (_node_link(n) for n in crosswalked)),
            _group(
                "Techniques those processes use",
                (_node_link(n) for n in neighbours if n.startswith("technique:")),
            ),
            _group(
                "Artifacts those processes touch",
                (_node_link(n) for n in neighbours if n.startswith("artifact:")),
            ),
            _group(
                f"Other {method.display_name} practices",
                ((p.display_name, _practice_href(method.key, p.key)) for p in siblings),
            ),
            _glossary_group(f"{practice.display_name} {practice.plain_summary}"),
            _map_group(crosswalked[0]) if crosswalked else _whole_map_group(),
        ]
    )


def for_term(term_key: str) -> Related:
    """The Related block for one glossary term on ``/glossary``: every page whose
    own words use it, read off the reverse index, plus its ``see_also`` entries."""
    mentions = _TERM_INDEX[term_key]
    on_the_graph = next((n for n in mentions if not n.startswith("practice:")), None)
    return _built(
        [
            _group(
                "Processes that use it",
                (_node_link(n) for n in mentions if n.startswith("process:")),
            ),
            _group(
                "Techniques that use it",
                (_node_link(n) for n in mentions if n.startswith("technique:")),
            ),
            _group(
                "Artifacts that use it",
                (_node_link(n) for n in mentions if n.startswith("artifact:")),
            ),
            _group(
                "Practices that use it",
                (
                    (
                        _PRACTICE_BY_KEY[key][1].display_name,
                        _practice_href(_PRACTICE_BY_KEY[key][0].key, key),
                    )
                    for key in (
                        n.removeprefix("practice:") for n in mentions if n.startswith("practice:")
                    )
                ),
            ),
            _group(
                "See also",
                ((GLOSSARY[k].term, _href("glossary", k)) for k in GLOSSARY[term_key].see_also),
            ),
            _map_group(on_the_graph) if on_the_graph else _whole_map_group(),
        ]
    )


def for_technique(key: str) -> Related:
    """The Related block for ``/techniques/{slug}``.

    ``GRAPH.neighbours`` rather than a second walk of the edge list: a technique's
    only edges are the ``used_by`` ones the processes naming it carry, so "who uses
    this" is the neighbourhood itself narrowed to the process kind, never re-derived.
    The artifacts are then those processes' own outputs — what running the technique
    ends up contributing to, one hop out — deduplicated, since two processes using
    one technique commonly produce the same kind.

    Every technique keeps at least its place on the map: an extension no PMBOK-6
    process names (``critical_chain_method`` today) has no neighbour at all, and
    without that floor its page would be the one the shared section silently skipped.
    """
    definition = TECHNIQUES[key]
    node_id = f"technique:{key}"
    processes = [n for n in GRAPH.neighbours(node_id) if n.startswith("process:")]
    artifacts = sorted({a for p in processes for a in _edge_ids(p, "produces", outgoing=True)})
    siblings = [d for d in TECHNIQUES.values() if d.family == definition.family and d.key != key]
    return _built(
        [
            _group("Used by", sorted(_node_link(n) for n in processes)),
            _group(
                "Same family",
                sorted((d.display_name, _href("technique", d.key)) for d in siblings),
            ),
            _group("Artifacts produced", sorted(_node_link(n) for n in artifacts)),
            _group("Agile practices", _practices_crosswalking(key)),
            _map_group(node_id),
        ]
    )


def for_artifact(key: str) -> Related:
    """The Related block for ``/artifacts/{slug}``.

    Everything the closed registries already hold about one artifact kind: the
    processes that make and read it (``GRAPH``'s own ``produces``/``reads``
    edges, never a second walk of the ITTO tables), the bundle it is a named
    part of and the parts of its own (``artifacts.COMPONENT_OF``, drawn there as
    ``part_of``), the agile evidence that can stand in for it
    (``crosswalk.EQUIVALENCES``, whose own text the process page prints
    verbatim), the rest of its family, and the techniques its producing
    processes use. A kind no process names still has its family and the map, so
    every artifact gets a block.
    """
    artifact = ARTIFACTS[key]
    node_id = f"artifact:{key}"
    made_by = _edge_ids(node_id, "produces", outgoing=False)
    techniques = dict.fromkeys(
        technique for p in made_by for technique in _edge_ids(p, "used_by", outgoing=False)
    )
    return _built(
        [
            _group("Made by", (_node_link(n) for n in made_by)),
            _group("Used by", (_node_link(n) for n in _edge_ids(node_id, "reads", outgoing=True))),
            _group(
                "Part of", (_node_link(n) for n in _edge_ids(node_id, "part_of", outgoing=True))
            ),
            _group("Parts", (_node_link(n) for n in _edge_ids(node_id, "part_of", outgoing=False))),
            _group(
                "Same family",
                (
                    (other.display_name, _href("artifact", other.key))
                    for other in ARTIFACTS.values()
                    if other.family is artifact.family and other.key != key
                ),
            ),
            _group("Techniques", (_node_link(n) for n in techniques)),
            _group(
                "Agile equivalence",
                (
                    (f"How {method.display_name} projects satisfy this", _href("method", m_key))
                    for m_key, method in METHODS.items()
                    if key in EQUIVALENCES
                ),
            ),
            _map_group(node_id),
        ]
    )


#: The Method reference's hubs, as (label, address). These are PAGES rather than
#: registry members, so they are named here — in the one module that builds a Related
#: block — instead of being hand-listed on each index that carries the strip, which is
#: exactly the drift ``_related.html`` exists to prevent.
THEORY_HUBS: tuple[tuple[str, str], ...] = (
    ("Technique library", "/techniques"),
    ("Artifacts", "/artifacts"),
    ("Method profiles", "/methods"),
    ("Method map", "/map"),
    ("Process status", "/process-map"),
)


def for_map(project_id: int | None = None, project_name: str | None = None) -> Related:
    """The Related block for ``/map``: the catalogs the graph is drawn from, so
    the picture always points back at the reference it summarises. Carries the
    washed project's own process map too, when the map is drawn with one."""
    hubs = [
        ("Theory index", "/pmbok"),
        ("Technique library", "/techniques"),
        ("Artifacts", "/artifacts"),
        ("Process status", "/process-map"),
    ]
    if project_id is not None:
        hubs.append((f"{project_name}'s process map", f"/projects/{project_id}/process-map"))
    return _built([_group("Elsewhere", hubs)])


def for_theory_index(path: str) -> Related:
    """The Related strip for the Method index at ``path``: every OTHER hub in the
    reference, so a reader who landed on one can reach the rest without going back
    up to the nav. A page never links to itself — its own address is dropped.
    """
    return _built(
        [
            _group(
                "Elsewhere in the method",
                ((label, href) for label, href in THEORY_HUBS if href != path),
            )
        ]
    )
