"""The wizard step is a workspace, not a bare form (Wave 1.3).

Before this change the page named a process by its clause number and a raw
``kind``/``tools_techniques`` string, offered a select with no reading of what each
choice meant, and said nothing about which method (if any) the project runs. This
adds, in plain words, for the CURRENT step: the process's own explanation, what the
project already has for its inputs (linking to the artifact and, where known, the
process that produces it), how to run each technique (its support tier and a link to
run or read it), what each output is (the on-page form, or why it is read rather
than produced), the method practices that cross-walk to this process (from
``?method=``, since ``Project`` carries no method yet), and a link to the same
process focused on the method map.

The totality test below is unit-level, over ``wizard_form``'s row builders directly
against a synthetic ``WizardStep`` for EVERY catalog process — no store needed, since
those builders take only the step's own tuples. It is what keeps a future process
(or a future artifact/technique key) from reaching the page as its raw identifier.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from driftless.pmbok import catalog
from driftless.web import wizard_form
from driftless.wizard import cli as wizard_cli
from driftless.wizard.engine import InputStatus, WizardStep, _step_kind
import test_web_pages
from test_web_pages import Q

client, db = test_web_pages.client, test_web_pages.db


def _step_for(process: object) -> WizardStep:
    from driftless.pmbok.model import Process

    assert isinstance(process, Process)
    offered = frozenset(wizard_cli.producible_kinds())
    return WizardStep(
        process_id=process.id,
        name=process.name,
        group=process.group.value,
        area=process.area.value,
        state="not_started",
        inputs=tuple(InputStatus(kind, True) for kind in process.inputs),
        tools_techniques=process.tools_techniques,
        outputs=process.outputs,
        producible=tuple(kind for kind in process.outputs if kind in offered),
        kind=_step_kind(process),
    )


def test_every_process_s_rows_carry_no_raw_identifier() -> None:
    """Every input, technique and output row, for every catalog process, reads in
    words — never the snake_case key the catalog names it by."""
    # The row's own NAME and HREF are what this workspace derives; a technique's
    # support-tier sentence or an untracked output's explanation is authored prose
    # (``reasons.py``) that may legitimately point at another kind by its store name
    # (e.g. "read change_log") — that provenance is not this row-builder's to rewrite.
    offences = []
    for process in catalog.PROCESSES:
        step = _step_for(process)
        for row in wizard_form.input_rows(step):
            if "_" in row["name"] or "_" in row["href"]:
                offences.append(f"{process.id}: input row {row!r} is a raw key")
        for row in wizard_form.technique_rows(step):
            if "_" in row["name"] or "_" in row["href"]:
                offences.append(f"{process.id}: technique row {row!r} carries a raw key")
        for row in wizard_form.output_rows(step):
            if "_" in row["name"] or "_" in row["href"]:
                offences.append(f"{process.id}: output row {row!r} carries a raw key")
    assert not offences, "\n".join(offences)


def test_the_workspace_names_all_six_sections(client: TestClient) -> None:
    body = client.get(f"/projects/1/wizard{Q}").text
    assert "What you need" in body
    assert "How you do it" in body
    assert "What you get" in body
    assert "See it on the map" in body
    from driftless.pmbok.process_definitions import PROCESS_DEFINITIONS

    assert PROCESS_DEFINITIONS["4.1"].plain_summary in body


def test_the_workspace_links_an_input_to_its_artifact_page(client: TestClient) -> None:
    body = client.get(f"/projects/1/wizard{Q}").text
    assert 'href="/artifacts/business-case"' in body
    assert "Business Case" in body
    assert "business_case" not in body


def test_the_workspace_shows_a_technique_s_support_tier_and_its_page(
    client: TestClient,
) -> None:
    body = client.get(f"/projects/1/wizard{Q}").text
    assert 'href="/techniques/expert-judgment"' in body
    assert "Expert judgment is, by definition, not encodable." in body
    assert "expert_judgment" not in body


def test_the_workspace_explains_an_output_it_cannot_produce(client: TestClient) -> None:
    """4.1's ``project_charter`` has no wizard producer; the workspace says why
    rather than offering a dead-end form entry with no explanation."""
    body = client.get(f"/projects/1/wizard{Q}").text
    assert "Generated on read by the report engine" in body


def test_the_workspace_links_the_map_focused_on_this_process(client: TestClient) -> None:
    body = client.get(f"/projects/1/wizard{Q}").text
    assert 'href="/map?focus=process:4.1&amp;project=1"' in body


def test_the_workspace_reads_method_context_from_the_query_param(client: TestClient) -> None:
    """``Project`` carries no method yet, so the crosswalk reads ``?method=`` —
    offered on the page as real links to the same step, never as query-string
    mechanics a reader has to type themselves."""
    without = client.get(f"/projects/1/wizard{Q}").text
    assert "Product Goal" not in without
    assert "method=scrum" in without and "method=kanban" in without
    with_scrum = client.get(f"/projects/1/wizard{Q}&method=scrum").text
    assert "Product Goal" in with_scrum
