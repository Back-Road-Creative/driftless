"""PMBOK-6 accuracy fixes: communications 10.1/10.2 and risk 11.2 tools &
techniques, and the retirement of the PMBOK-5 ``acquisition`` technique from
Acquire Resources (9.3). See ``driftless/pmbok/areas/communications.py``,
``driftless/pmbok/areas/risk.py``, ``driftless/pmbok/areas/resource.py`` and
``driftless/pmbok/tt.py`` for the corrected catalog data these pin.
"""

from __future__ import annotations

from driftless.pmbok.areas import communications, resource, risk
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.model import Process
from driftless.pmbok.tt import TT_CATALOG


def _process(processes: tuple[Process, ...], process_id: str) -> Process:
    return next(p for p in processes if p.id == process_id)


def test_communication_models_is_only_in_plan_communications_management() -> None:
    """PMBOK-6 10.1.2 (Plan Communications Management) names communication
    models; 10.2.2 (Manage Communications) does not (its T&T are
    communication technology, methods, skills, PMIS, project reporting,
    interpersonal and team skills, meetings)."""
    plan = _process(communications.PROCESSES, "10.1")
    manage = _process(communications.PROCESSES, "10.2")
    assert "communication_models" in plan.tools_techniques
    assert "communication_models" not in manage.tools_techniques


def test_communication_requirements_analysis_and_project_reporting_are_catalogued() -> None:
    plan = _process(communications.PROCESSES, "10.1")
    manage = _process(communications.PROCESSES, "10.2")
    assert "communication_requirements_analysis" in plan.tools_techniques
    assert "communication_requirements_analysis" in TT_CATALOG
    assert "project_reporting" in manage.tools_techniques
    assert "project_reporting" in TT_CATALOG


def test_prompt_lists_is_catalogued_and_named_by_identify_risks() -> None:
    identify = _process(risk.PROCESSES, "11.2")
    assert "prompt_lists" in identify.tools_techniques
    assert "prompt_lists" in TT_CATALOG


def test_acquisition_is_retired_as_a_pmbok_6_technique() -> None:
    """PMBOK-5 vocabulary: PMBOK-6 9.3 (Acquire Resources) names decision
    making, interpersonal and team skills (negotiation), pre-assignment and
    virtual teams instead."""
    acquire = _process(resource.PROCESSES, "9.3")
    assert "acquisition" not in acquire.tools_techniques
    assert "acquisition" not in TT_CATALOG
    for technique in ("decision_making", "pre_assignment", "negotiation", "virtual_teams"):
        assert technique in acquire.tools_techniques


def test_new_techniques_have_definitions() -> None:
    for key in ("communication_requirements_analysis", "project_reporting", "prompt_lists"):
        assert key in TECHNIQUES
        assert TECHNIQUES[key].summary.strip()
