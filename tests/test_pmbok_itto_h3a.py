"""Five PMBOK-6 ITTO corrections, pinned one assertion per correction.

Each test reads the live catalog/graph rather than restating a number — a process's
ITTOs are reference data, so the only thing worth asserting is that the registry now
says what the Guide says.
"""

from __future__ import annotations

from driftless.pmbok import catalog
from driftless.pmbok.graph import GRAPH


def test_validate_scope_reads_verified_deliverables_not_deliverables() -> None:
    process = catalog.get("5.5")
    assert "verified_deliverables" in process.inputs
    assert "deliverables" not in process.inputs


def test_control_quality_feeds_validate_scope_through_verified_deliverables() -> None:
    assert ("process:8.3", "process:5.5") in {
        (e.source, e.target) for e in GRAPH.edges if e.kind == "feeds"
    }


def test_estimate_costs_inputs_match_the_guide() -> None:
    process = catalog.get("7.2")
    assert set(process.inputs) == {
        "cost_management_plan",
        "quality_management_plan",
        "scope_baseline",
        "project_schedule",
        "resource_requirements",
        "risk_register",
        "enterprise_environmental_factors",
        "organizational_process_assets",
    }


def test_plan_procurement_management_outputs_bid_documents_and_independent_cost_estimates() -> None:
    process = catalog.get("12.1")
    assert "bid_documents" in process.outputs
    assert "independent_cost_estimates" in process.outputs


def test_manage_stakeholder_engagement_does_not_output_project_communications() -> None:
    process = catalog.get("13.3")
    assert "project_communications" not in process.outputs


def test_perform_quantitative_risk_analysis_outputs_only_risk_report() -> None:
    process = catalog.get("11.4")
    assert process.outputs == ("risk_report",)
    assert "risk_register" not in process.outputs
    assert process.optional_outputs == ()
