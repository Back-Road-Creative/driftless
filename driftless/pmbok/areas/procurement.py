"""PMBOK-6 Procurement Management: the three processes and their ITTOs."""

from __future__ import annotations

from driftless.pmbok.model import KnowledgeArea, Process, ProcessGroup

PROCESSES: tuple[Process, ...] = (
    Process(
        id="12.1",
        name="Plan Procurement Management",
        group=ProcessGroup.PLANNING,
        area=KnowledgeArea.PROCUREMENT,
        inputs=(
            "project_charter",
            "business_case",
            "project_management_plan",
            "scope_baseline",
            "requirements_documentation",
            "risk_register",
            "enterprise_environmental_factors",
            "organizational_process_assets",
        ),
        tools_techniques=(
            "expert_judgment",
            "data_gathering",
            "data_analysis",
            "source_selection_analysis",
            "make_or_buy_analysis",
            "meetings",
        ),
        outputs=(
            "procurement_management_plan",
            "procurement_strategy",
            "procurement_statement_of_work",
            "source_selection_criteria",
        ),
    ),
    Process(
        id="12.2",
        name="Conduct Procurements",
        group=ProcessGroup.EXECUTING,
        area=KnowledgeArea.PROCUREMENT,
        inputs=(
            "procurement_management_plan",
            "procurement_documentation",
            "seller_proposals",
            "source_selection_criteria",
            "bid_documents",
            "procurement_statement_of_work",
        ),
        tools_techniques=(
            "expert_judgment",
            "advertising",
            "bidder_conferences",
            "proposal_evaluation",
            "interpersonal_and_team_skills",
        ),
        outputs=(
            "selected_sellers",
            "agreements",
            "change_requests",
        ),
        optional_outputs=("change_requests",),
    ),
    Process(
        id="12.3",
        name="Control Procurements",
        group=ProcessGroup.MONITORING,
        area=KnowledgeArea.PROCUREMENT,
        inputs=(
            "project_management_plan",
            "agreements",
            "procurement_documentation",
            "approved_change_requests",
            "work_performance_data",
            "risk_register",
            "enterprise_environmental_factors",
        ),
        tools_techniques=(
            "expert_judgment",
            "claims_administration",
            "data_analysis",
            "inspections_and_audits",
            "procurement_performance_reviews",
        ),
        outputs=(
            "closed_procurements",
            "work_performance_information",
            "change_requests",
        ),
        optional_outputs=("closed_procurements", "change_requests"),
    ),
)
