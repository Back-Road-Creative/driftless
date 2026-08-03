"""PMBOK-6 Stakeholder Management: the 4 processes of knowledge area 13."""

from __future__ import annotations

from driftless.pmbok.model import KnowledgeArea, Process, ProcessGroup

PROCESSES: tuple[Process, ...] = (
    Process(
        id="13.1",
        name="Identify Stakeholders",
        group=ProcessGroup.INITIATING,
        area=KnowledgeArea.STAKEHOLDER,
        inputs=(
            "project_charter",
            "business_case",
            "benefits_management_plan",
            "agreements",
            "enterprise_environmental_factors",
            "organizational_process_assets",
        ),
        tools_techniques=(
            "expert_judgment",
            "data_gathering",
            "data_analysis",
            "data_representation",
            "meetings",
        ),
        outputs=("stakeholder_register", "change_requests"),
        optional_outputs=("change_requests",),
    ),
    Process(
        id="13.2",
        name="Plan Stakeholder Engagement",
        group=ProcessGroup.PLANNING,
        area=KnowledgeArea.STAKEHOLDER,
        inputs=(
            "project_charter",
            "project_management_plan",
            "stakeholder_register",
            "agreements",
            "enterprise_environmental_factors",
            "organizational_process_assets",
        ),
        tools_techniques=(
            "expert_judgment",
            "data_gathering",
            "data_analysis",
            "data_representation",
            "decision_making",
            "meetings",
        ),
        outputs=("stakeholder_engagement_plan",),
    ),
    Process(
        id="13.3",
        name="Manage Stakeholder Engagement",
        group=ProcessGroup.EXECUTING,
        area=KnowledgeArea.STAKEHOLDER,
        inputs=(
            "stakeholder_engagement_plan",
            "communications_management_plan",
            "risk_management_plan",
            "change_log",
            "issue_log",
            "organizational_process_assets",
        ),
        tools_techniques=(
            "expert_judgment",
            "communication_skills",
            "interpersonal_and_team_skills",
            "ground_rules",
            "meetings",
        ),
        outputs=("change_requests", "project_communications", "issue_log"),
        optional_outputs=("change_requests",),
    ),
    Process(
        id="13.4",
        name="Monitor Stakeholder Engagement",
        group=ProcessGroup.MONITORING,
        area=KnowledgeArea.STAKEHOLDER,
        inputs=(
            "project_management_plan",
            "stakeholder_engagement_plan",
            "issue_log",
            "work_performance_data",
            "agreements",
            "organizational_process_assets",
        ),
        tools_techniques=(
            "data_analysis",
            "decision_making",
            "data_representation",
            "communication_skills",
            "interpersonal_and_team_skills",
            "meetings",
        ),
        outputs=("work_performance_information", "change_requests"),
        optional_outputs=("change_requests",),
    ),
)
