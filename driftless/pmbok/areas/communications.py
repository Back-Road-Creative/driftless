"""PMBOK-6 Communications Management knowledge area: its three ITTO processes."""

from __future__ import annotations

from driftless.pmbok.model import KnowledgeArea, Process, ProcessGroup

PROCESSES: tuple[Process, ...] = (
    Process(
        id="10.1",
        name="Plan Communications Management",
        group=ProcessGroup.PLANNING,
        area=KnowledgeArea.COMMUNICATIONS,
        inputs=(
            "project_charter",
            "project_management_plan",
            "stakeholder_register",
            "requirements_documentation",
            "enterprise_environmental_factors",
            "organizational_process_assets",
        ),
        tools_techniques=(
            "expert_judgment",
            "communication_technology",
            "communication_models",
            "communication_methods",
            "data_representation",
            "interpersonal_and_team_skills",
            "meetings",
        ),
        outputs=(
            "communications_management_plan",
            "project_management_plan",
        ),
        optional_outputs=("project_management_plan",),
    ),
    Process(
        id="10.2",
        name="Manage Communications",
        group=ProcessGroup.EXECUTING,
        area=KnowledgeArea.COMMUNICATIONS,
        inputs=(
            "communications_management_plan",
            "stakeholder_engagement_plan",
            "change_log",
            "issue_log",
            "quality_report",
            "work_performance_reports",
        ),
        tools_techniques=(
            "communication_technology",
            "communication_methods",
            "communication_skills",
            "communication_models",
            "project_management_information_system",
            "interpersonal_and_team_skills",
            "meetings",
        ),
        outputs=("project_communications",),
    ),
    Process(
        id="10.3",
        name="Monitor Communications",
        group=ProcessGroup.MONITORING,
        area=KnowledgeArea.COMMUNICATIONS,
        inputs=(
            "project_management_plan",
            "issue_log",
            "lessons_learned_register",
            "project_communications",
            "work_performance_data",
            "enterprise_environmental_factors",
            "organizational_process_assets",
        ),
        tools_techniques=(
            "expert_judgment",
            "project_management_information_system",
            "data_analysis",
            "data_representation",
            "interpersonal_and_team_skills",
            "meetings",
        ),
        outputs=(
            "work_performance_information",
            "change_requests",
        ),
        optional_outputs=("change_requests",),
    ),
)
