"""A ``further_reading`` citation names a clause, but nothing before this file
checked *whose* clause: a citation copied onto the wrong technique passes
every shape and collision check in ``tests/test_technique_totality.py`` as
long as it merely looks like a well-formed PMBOK-6 reference. This test adds
the one check those don't: a citation's ``<area>.<process>`` prefix must name
a real process in the catalog, and that process's ``tools_techniques`` must
actually list the technique carrying the citation.
"""

from __future__ import annotations

import re

from driftless.pmbok import catalog
from driftless.pmbok.definitions import TECHNIQUES

#: A PMBOK-6 clause reference, capturing the area and process numbers a
#: citation's prefix names — the same shape
#: ``tests/test_technique_totality.py``'s ``CLAUSE_REFERENCE`` pins, with the
#: leading ``<area>.<process>`` pulled out rather than just matched.
CLAUSE_PREFIX = re.compile(
    r"^PMBOK-6 §(?P<area>[1-9]|1[0-3])\.(?P<process>\d{1,2})(?:\.\d{1,2}){0,2}$"
)

#: Every process id in the catalog, mapped to the technique keys it names as
#: tools and techniques.
_PROCESS_TOOLS: dict[str, tuple[str, ...]] = {
    process.id: process.tools_techniques for process in catalog.PROCESSES
}


def test_every_citation_names_a_real_process() -> None:
    unknown: list[str] = []
    for key, definition in sorted(TECHNIQUES.items()):
        for citation in definition.further_reading:
            match = CLAUSE_PREFIX.fullmatch(citation)
            if match is None:
                continue
            process_id = f"{match['area']}.{match['process']}"
            if process_id not in _PROCESS_TOOLS:
                unknown.append(f"{key}: {citation} (no process {process_id})")
    assert not unknown, (
        "a citation's <area>.<process> prefix must name a real catalog process:\n"
        + "\n".join(unknown)
    )


def test_every_citation_s_process_actually_uses_the_technique() -> None:
    mismatched: list[str] = []
    for key, definition in sorted(TECHNIQUES.items()):
        for citation in definition.further_reading:
            match = CLAUSE_PREFIX.fullmatch(citation)
            if match is None:
                continue
            process_id = f"{match['area']}.{match['process']}"
            tools = _PROCESS_TOOLS.get(process_id)
            if tools is not None and key not in tools:
                mismatched.append(f"{key}: {citation} (process {process_id} tools: {tools})")
    assert not mismatched, (
        "a citation's process must actually list the technique among its "
        "tools_techniques in driftless/pmbok/areas/*.py:\n" + "\n".join(mismatched)
    )
