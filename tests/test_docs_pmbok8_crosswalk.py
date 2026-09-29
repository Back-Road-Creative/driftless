"""``docs/pmbok8-crosswalk.md`` maps every catalog process onto the PMBOK 8 processes.
It is driftless's own editorial reading, built from two secondary sources (PMI has not
published the PMBOK Guide 8th edition's own text at the time of writing), not PMI's, but the
process ids and names in its table must still be the live catalog's own — a catalog change
(an id renamed, a process added or removed) has to turn this red rather than let the doc
quietly drift out of sync.
"""

from __future__ import annotations

import re
from pathlib import Path

from driftless.pmbok import catalog

DOC = Path(__file__).resolve().parents[1] / "docs" / "pmbok8-crosswalk.md"
WRITTEN = DOC.read_text()

#: The 40 PMBOK 8 processes, grouped by domain, per two secondary sources (brainbok.com and
#: projinsights.com, 2026) — PMI's own 8th-edition text was not available at time of writing.
DOMAIN_PROCESSES: dict[str, set[str]] = {
    "Governance": {
        "Initiate Project or Phase",
        "Integrate and Align Project Plans",
        "Manage Project Execution",
        "Manage Project Knowledge",
        "Manage Quality Assurance",
        "Monitor and Control Project Performance",
        "Assess and Implement Changes",
        "Plan Sourcing Strategy",
        "Close Project or Phase",
    },
    "Scope": {
        "Plan Scope Management",
        "Elicit and Analyze Requirements",
        "Define Scope",
        "Develop Scope Structure",
        "Validate Scope",
        "Monitor and Control Scope",
    },
    "Schedule": {
        "Plan Schedule Management",
        "Develop Schedule",
        "Monitor and Control Schedule",
    },
    "Finance": {
        "Plan Financial Management",
        "Estimate Costs",
        "Develop Budget",
        "Monitor and Control Finances",
    },
    "Stakeholders": {
        "Identify Stakeholders",
        "Plan Stakeholder Engagement",
        "Plan Communications Management",
        "Manage Stakeholder Engagement",
        "Manage Communications",
        "Monitor Communications",
        "Monitor Stakeholder Engagement",
    },
    "Resources": {
        "Plan Resource Management",
        "Estimate Resources",
        "Acquire Resources",
        "Lead the Team",
        "Monitor and Control Resourcing",
    },
    "Risk": {
        "Plan Risk Management",
        "Identify Risks",
        "Perform Risk Analysis",
        "Plan Risk Responses",
        "Implement Risk Responses",
        "Monitor Risks",
    },
}

ALL_PROCESSES: set[str] = {p for domain in DOMAIN_PROCESSES.values() for p in domain}
PROCESS_TO_DOMAIN: dict[str, str] = {
    p: domain for domain, procs in DOMAIN_PROCESSES.items() for p in procs
}

DASH_MARKERS = {"— (absorbed)", "— (appendix)"}

ROW = re.compile(
    r"^\|\s*(?P<id>\d+\.\d+)\s*\|\s*(?P<name>[^|]+?)\s*\|\s*(?P<process>[^|]+?)\s*\|"
    r"\s*(?P<domain>[^|]+?)\s*\|\s*$",
    re.MULTILINE,
)


def _rows() -> list[re.Match[str]]:
    return list(ROW.finditer(WRITTEN))


def test_doc_exists() -> None:
    assert DOC.exists()


def test_table_has_a_row_per_row_found() -> None:
    assert len(_rows()) > 0


def test_process_ids_match_the_catalog_exactly() -> None:
    doc_ids = {m.group("id") for m in _rows()}
    catalog_ids = {p.id for p in catalog.PROCESSES}
    assert doc_ids == catalog_ids


def test_process_names_match_the_catalog_verbatim() -> None:
    catalog_by_id = {p.id: p.name for p in catalog.PROCESSES}
    for m in _rows():
        assert m.group("name") == catalog_by_id[m.group("id")], m.group("id")


def test_every_pmbok8_process_cell_is_one_of_the_forty_or_a_dash_marker() -> None:
    for m in _rows():
        cell = m.group("process").strip()
        assert cell in ALL_PROCESSES or cell in DASH_MARKERS, (m.group("id"), cell)


def test_domain_cell_matches_the_process_cells_domain() -> None:
    for m in _rows():
        process_cell = m.group("process").strip()
        domain_cell = m.group("domain").strip()
        if process_cell in DASH_MARKERS:
            assert domain_cell in DASH_MARKERS, (m.group("id"), domain_cell)
        else:
            assert domain_cell == PROCESS_TO_DOMAIN[process_cell], (m.group("id"), domain_cell)


def test_every_one_of_the_forty_is_fed_or_listed_as_not_fed() -> None:
    fed = {m.group("process").strip() for m in _rows()} & ALL_PROCESSES
    not_fed_line = WRITTEN[WRITTEN.find("not fed by the catalog") :]
    for process in ALL_PROCESSES:
        assert process in fed or process in not_fed_line, process


def test_doc_states_it_is_editorial_not_pmis() -> None:
    assert "editorial crosswalk, not PMI's" in WRITTEN


def test_doc_states_the_secondary_sources() -> None:
    assert "brainbok.com" in WRITTEN
    assert "projinsights.com" in WRITTEN
