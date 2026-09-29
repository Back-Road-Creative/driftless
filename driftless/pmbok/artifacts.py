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

#: The eight groupings above, named and exposed for
#: ``driftless.pmbok.artifact_content`` to build one ``ArtifactContent`` module
#: per family from — so a kind added to a family here can be claimed by that
#: family's content module, with no second list to keep in sync.
FAMILIES: dict[str, frozenset[str]] = {
    "plans": frozenset(_PLANS),
    "baselines": frozenset(_BASELINES),
    "documents": frozenset(_DOCUMENTS),
    "performance": frozenset(_PERFORMANCE),
    "procurement": frozenset(_PROCUREMENT),
    "deliverables": frozenset(_DELIVERABLES),
    "changes": frozenset(_CHANGES),
    "environment": frozenset(_ENVIRONMENT),
}

#: The flat closed set every process input/output must be drawn from.
ARTIFACT_KINDS: frozenset[str] = frozenset().union(*FAMILIES.values())

#: A kind that is not an independent process output but a named PART of another
#: kind's bundle — PMBOK-6's own composition, not this catalog's invention. The
#: WBS and its dictionary are components of the scope baseline (5.4 Create WBS's
#: one output IS scope_baseline; the edition never lists the WBS as a separate
#: output of any process), so no process names ``work_breakdown_structure`` in its
#: own inputs/outputs — this is what explains it instead. ``pmbok.graph`` draws
#: each entry as a ``part_of`` edge to its whole, so a component kind still
#: connects in the method graph without a process pretending to produce it
#: independently; ``tests/test_method_graph.py`` reads this map, never retypes it.
COMPONENT_OF: dict[str, str] = {
    "work_breakdown_structure": "scope_baseline",
    # ``development_approach`` is carried as ``Project.delivery_mode`` (a field on
    # the project record, per artifact_content/plans.py) rather than a document
    # any process names — its whole is the plan it is a facet of.
    "development_approach": "project_management_plan",
    # The PMB is "the same three approved baselines above, read together" per
    # artifact_content/baselines.py — it names three wholes at once (scope_,
    # schedule_ and cost_baseline), and COMPONENT_OF holds exactly one key per
    # part. Recording it against project_management_plan (which the PMB is
    # itself a component of, alongside those three) is the honest single choice;
    # picking one baseline arbitrarily among equals would not be.
    "performance_measurement_baseline": "project_management_plan",
}
