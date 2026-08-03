"""PMBOK-6 Quality Management knowledge area: Plan/Manage/Control Quality (8.1-8.3)."""

from driftless.pmbok.model import KnowledgeArea, Process, ProcessGroup

PROCESSES: tuple[Process, ...] = (
    Process(
        id="8.1",
        name="Plan Quality Management",
        group=ProcessGroup.PLANNING,
        area=KnowledgeArea.QUALITY,
        inputs=(
            "project_charter",
            "requirements_management_plan",
            "risk_management_plan",
            "stakeholder_engagement_plan",
            "scope_baseline",
            "requirements_documentation",
            "stakeholder_register",
        ),
        tools_techniques=(
            "expert_judgment",
            "data_gathering",
            "data_analysis",
            "decision_making",
            "data_representation",
            "test_and_inspection_planning",
        ),
        outputs=(
            "quality_management_plan",
            "quality_metrics",
            "project_management_plan",
        ),
        optional_outputs=("project_management_plan",),
    ),
    Process(
        id="8.2",
        name="Manage Quality",
        group=ProcessGroup.EXECUTING,
        area=KnowledgeArea.QUALITY,
        inputs=(
            "quality_management_plan",
            "lessons_learned_register",
            "quality_control_measurements",
            "quality_metrics",
            "risk_report",
            "organizational_process_assets",
        ),
        tools_techniques=(
            "data_analysis",
            "root_cause_analysis",
            "audits",
            "design_for_x",
            "problem_solving",
            "quality_improvement_methods",
        ),
        outputs=(
            "quality_report",
            "test_and_evaluation_documents",
            "change_requests",
            "project_management_plan",
        ),
        optional_outputs=("change_requests", "project_management_plan"),
    ),
    Process(
        id="8.3",
        name="Control Quality",
        group=ProcessGroup.MONITORING,
        area=KnowledgeArea.QUALITY,
        inputs=(
            "quality_management_plan",
            "quality_metrics",
            "deliverables",
            "work_performance_data",
            "approved_change_requests",
            "test_and_evaluation_documents",
        ),
        tools_techniques=(
            "data_gathering",
            "data_analysis",
            "inspection",
            "testing_product_evaluations",
            "data_representation",
            "meetings",
        ),
        outputs=(
            "quality_control_measurements",
            "verified_deliverables",
            "work_performance_information",
            "change_requests",
        ),
        optional_outputs=("change_requests",),
    ),
)
