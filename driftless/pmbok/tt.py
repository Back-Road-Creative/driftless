"""``TT_CATALOG``: the closed set of Tools & Techniques the ITTO catalog references.

Every process's ``tools_techniques`` names members of this set. It doubles as the
vocabulary the recommendation engine draws its suggested actions from — an
Action's ``pmbok_tt`` is one of these — so keeping it closed keeps
recommendations grounded in real PMBOK techniques rather than free text. A
process naming a technique not in here fails the catalog's referential test.

The PMBOK-6 "data gathering / analysis / representation", "decision making",
"interpersonal and team skills" and "communication" families are represented by
their group names plus the individual techniques the processes lean on.
"""

# The cross-cutting PMBOK-6 technique families used across many processes.
_GENERAL = {
    "expert_judgment",
    "data_gathering",
    "data_analysis",
    "data_representation",
    "decision_making",
    "interpersonal_and_team_skills",
    "communication_skills",
    "communication_methods",
    "communication_models",
    "communication_technology",
    "meetings",
    "project_management_information_system",
}

# Integration-heavy techniques.
_INTEGRATION = {
    "change_control_tools",
    "knowledge_management",
    "information_management",
}

# Scope and requirements.
_SCOPE = {
    "decomposition",
    "product_analysis",
    "prototypes",
    "context_diagram",
    "inspection",
    "benchmarking",
}

# Schedule.
_SCHEDULE = {
    "rolling_wave_planning",
    "precedence_diagramming_method",
    "dependency_determination",
    "leads_and_lags",
    "analogous_estimating",
    "parametric_estimating",
    "three_point_estimating",
    "bottom_up_estimating",
    "critical_path_method",
    "resource_optimization",
    "schedule_compression",
    "schedule_network_analysis",
    "agile_release_planning",
}

# Cost.
_COST = {
    "cost_aggregation",
    "reserve_analysis",
    "cost_of_quality",
    "funding_limit_reconciliation",
    "financing",
    "historical_information_review",
    "earned_value_analysis",
    "to_complete_performance_index",
}

# Quality.
_QUALITY = {
    "quality_improvement_methods",
    "audits",
    "design_for_x",
    "problem_solving",
    "test_and_inspection_planning",
    "testing_product_evaluations",
    "root_cause_analysis",
}

# Resource.
_RESOURCE = {
    "organizational_theory",
    "pre_assignment",
    "negotiation",
    "acquisition",
    "virtual_teams",
    "colocation",
    "training",
    "team_building",
    "recognition_and_rewards",
    "individual_and_team_assessments",
    "conflict_management",
    "influencing",
}

# Risk.
_RISK = {
    "risk_categorization",
    "risk_probability_and_impact_assessment",
    "representations_of_uncertainty",
    "strategies_for_threats",
    "strategies_for_opportunities",
    "contingent_response_strategies",
    "strategies_for_overall_project_risk",
    "simulation",
    "sensitivity_analysis",
    "decision_tree_analysis",
    "influence_diagrams",
}

# Procurement.
_PROCUREMENT = {
    "source_selection_analysis",
    "bidder_conferences",
    "advertising",
    "proposal_evaluation",
    "claims_administration",
    "procurement_performance_reviews",
    "inspections_and_audits",
    "make_or_buy_analysis",
}

# Stakeholder and estimating supports.
_STAKEHOLDER = {
    "stakeholder_analysis",
    "stakeholder_engagement_assessment_matrix",
    "ground_rules",
    "multicriteria_decision_analysis",
    "voting",
    "autocratic_decision_making",
    "focus_groups",
}

#: The flat closed set every process's tools_techniques must be drawn from.
TT_CATALOG: frozenset[str] = frozenset(
    _GENERAL
    | _INTEGRATION
    | _SCOPE
    | _SCHEDULE
    | _COST
    | _QUALITY
    | _RESOURCE
    | _RISK
    | _PROCUREMENT
    | _STAKEHOLDER
)
