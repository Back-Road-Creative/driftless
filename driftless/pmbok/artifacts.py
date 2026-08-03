"""``ARTIFACT_KINDS``: the closed set of artifact types the ITTO catalog references.

Every process input and output names one of these. It is deliberately a curated
closed set rather than a free-text field: ``driftless.pmbok.mapping`` resolves
each kind to concrete rows in the live store, so the set is the vocabulary that
bridges PMBOK theory to this system's data. A process referencing a kind not in
here fails the catalog's referential-integrity test.

Grouped only for reading; the public value is the flat ``ARTIFACT_KINDS`` set.
"""

# Charters, plans and their subsidiary management plans.
_PLANS = {
    "project_charter",
    "project_management_plan",
    "scope_management_plan",
    "requirements_management_plan",
    "schedule_management_plan",
    "cost_management_plan",
    "quality_management_plan",
    "resource_management_plan",
    "communications_management_plan",
    "risk_management_plan",
    "procurement_management_plan",
    "stakeholder_engagement_plan",
    "change_management_plan",
    "configuration_management_plan",
    "development_approach",
}

# The measurement baselines.
_BASELINES = {
    "scope_baseline",
    "schedule_baseline",
    "cost_baseline",
    "performance_measurement_baseline",
}

# Project documents — the working artifacts a process reads and revises.
_DOCUMENTS = {
    "assumption_log",
    "issue_log",
    "change_log",
    "lessons_learned_register",
    "milestone_list",
    "project_schedule",
    "schedule_data",
    "activity_list",
    "activity_attributes",
    "project_schedule_network_diagram",
    "duration_estimates",
    "basis_of_estimates",
    "cost_estimates",
    "project_calendars",
    "requirements_documentation",
    "requirements_traceability_matrix",
    "project_scope_statement",
    "work_breakdown_structure",
    "risk_register",
    "risk_report",
    "quality_metrics",
    "quality_control_measurements",
    "quality_report",
    "resource_requirements",
    "resource_breakdown_structure",
    "resource_calendars",
    "team_charter",
    "project_team_assignments",
    "physical_resource_assignments",
    "stakeholder_register",
    "test_and_evaluation_documents",
    "project_communications",
    "cost_forecasts",
    "schedule_forecasts",
    "project_funding_requirements",
    "team_performance_assessments",
}

# Work-performance flow.
_PERFORMANCE = {
    "work_performance_data",
    "work_performance_information",
    "work_performance_reports",
}

# Procurement artifacts.
_PROCUREMENT = {
    "procurement_statement_of_work",
    "procurement_documentation",
    "procurement_strategy",
    "source_selection_criteria",
    "bid_documents",
    "seller_proposals",
    "agreements",
    "selected_sellers",
    "closed_procurements",
    "independent_cost_estimates",
}

# Deliverables and closeout products.
_DELIVERABLES = {
    "deliverables",
    "verified_deliverables",
    "accepted_deliverables",
    "final_product_service_result",
    "final_report",
}

# Change control.
_CHANGES = {
    "change_requests",
    "approved_change_requests",
}

# Enterprise inputs — the environment and the organisation's own assets.
_ENVIRONMENT = {
    "enterprise_environmental_factors",
    "organizational_process_assets",
    "business_case",
    "benefits_management_plan",
    "agreements_initial",
}

#: The flat closed set every process input/output must be drawn from.
ARTIFACT_KINDS: frozenset[str] = frozenset(
    _PLANS
    | _BASELINES
    | _DOCUMENTS
    | _PERFORMANCE
    | _PROCUREMENT
    | _DELIVERABLES
    | _CHANGES
    | _ENVIRONMENT
)
