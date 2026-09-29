"""Documented decisions, not placeholders: why a launcher, a producer or a
citation is missing, for the members of ``TT_CATALOG`` and ``ARTIFACT_KINDS``
that do not have one yet.

Three exemption dicts share one shape — a :class:`Reason` (``kind`` plus one
prose ``why`` sentence):

* ``GUIDE_ONLY_REASONS`` — every ``TT_CATALOG`` member outside
  ``assess.model.ASSISTANT_ROUTES`` gets one, so ``TT_CATALOG`` is exactly the
  union of the two (``tests/test_launcher_totality.py``). A ``kind`` of
  ``NOT_YET_BUILT`` is the only one that says "we could serve this and
  haven't" — everything else is an honest ceiling: a skill, a meeting, an
  external system, a call only a person can make, or a printable worksheet
  that is already the whole of the help.
* ``UNTRACKED_REASONS`` — every ``ARTIFACT_KINDS`` member outside
  ``wizard.cli.producible_kinds`` gets one, for the same reason
  (``tests/test_launcher_totality.py``).
* ``UNCITED_EXEMPTIONS`` — every technique the totality suite finds uncited
  gets one (``tests/test_technique_totality.py``, which owns those checks;
  this module only holds the data and the kind vocabulary).

None of the three is a place to explain a gap once and move on: each is
walked and asserted equal to the gap it covers, so an entry that stops being
true (a route ships, a producer lands, a citation is found) fails the suite
that owns it until the entry is deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class Reason:
    """One documented decision: a machine-readable ``kind`` plus the one
    sentence a reader needs. Reused by all three exemption dicts below, each
    with its own ``kind`` vocabulary, so "no assistant", "no producer" and "no
    citation" are recorded in the same shape rather than three ad hoc ones."""

    kind: Enum
    why: str


class GuideOnlyKind(str, Enum):
    """Why a technique has no assistant yet — the ceiling on what a launcher
    could ever honestly offer it, not a snapshot of today's backlog."""

    #: A human relational skill: no worksheet substitutes for negotiating,
    #: influencing or building a team.
    INTERPERSONAL_SKILL = "interpersonal_skill"
    #: The technique IS a meeting of a particular shape; running it is the work.
    MEETING_FORMAT = "meeting_format"
    #: Depends on a tool or channel Driftless does not operate.
    EXTERNAL_SYSTEM = "external_system"
    #: A judgment call with no deterministic procedure to encode.
    JUDGMENT_ONLY = "judgment_only"
    #: A printable worksheet in ``worksheets.WORKSHEETS`` is the whole of the help:
    #: the reader fills it in, and no figure follows for a launcher to compute. A
    #: ceiling rather than a backlog item — unlike ``NOT_YET_BUILT``, nothing
    #: further is owed once the sheet is written.
    WORKSHEET_ONLY = "worksheet_only"
    #: A worksheet or calculator could clearly serve it; nobody has built one.
    NOT_YET_BUILT = "not_yet_built"


class UntrackedKind(str, Enum):
    """Why an ``ARTIFACT_KINDS`` member has no wizard producer form."""

    #: Computed from other stored rows on read; a stored copy would duplicate them.
    DERIVED_ON_READ = "derived_on_read"
    #: Produced before the store's tracked boundary begins, or by a process outside it.
    EXTERNAL_DOCUMENT = "external_document"
    #: A form could clearly serve it; nobody has built one.
    NOT_YET_BUILT = "not_yet_built"


class CitationGapKind(str, Enum):
    """Why a technique carries no ``further_reading`` clause."""

    #: PMBOK-6 numbers the group, not each member technique.
    UNNUMBERED_GROUP = "unnumbered_group"
    #: PMBOK-6 discusses it in narrative prose rather than a numbered clause.
    NARRATIVE_ONLY = "narrative_only"
    #: Listed as a tool of nearly every process rather than defined at one clause.
    CROSS_CUTTING = "cross_cutting"
    #: A candidate clause was found and ruled out — it names an inputs/outputs
    #: subsection, or collides with another technique's leaf clause.
    MISCITED_CLAUSE = "miscited_clause"
    #: A Driftless extension; no PMBOK-6 clause defines it.
    EXTENSION = "extension"
    #: The right clause could not be established from the edition.
    UNCONFIRMED = "unconfirmed"


#: Every ``TT_CATALOG`` member outside ``ASSISTANT_ROUTES``, classified.
GUIDE_ONLY_REASONS: dict[str, Reason] = {
    # general
    "communication_models": Reason(
        GuideOnlyKind.JUDGMENT_ONLY, "A conceptual model, not a computable procedure."
    ),
    "communication_requirements_analysis": Reason(
        GuideOnlyKind.JUDGMENT_ONLY,
        "Deciding who needs what information is a judgment call informed by "
        "the stakeholders assistant, not a computed procedure of its own.",
    ),
    "communication_skills": Reason(
        GuideOnlyKind.INTERPERSONAL_SKILL, "Active listening and clarity are practiced, not run."
    ),
    "data_analysis": Reason(
        GuideOnlyKind.JUDGMENT_ONLY, "An umbrella group; its members are the runnable ones."
    ),
    "data_gathering": Reason(
        GuideOnlyKind.JUDGMENT_ONLY, "An umbrella group; its members are the runnable ones."
    ),
    "data_representation": Reason(
        GuideOnlyKind.JUDGMENT_ONLY, "An umbrella group; its members are the runnable ones."
    ),
    "decision_making": Reason(
        GuideOnlyKind.JUDGMENT_ONLY, "An umbrella group; its members are the runnable ones."
    ),
    "expert_judgment": Reason(
        GuideOnlyKind.JUDGMENT_ONLY, "Expert judgment is, by definition, not encodable."
    ),
    "interpersonal_and_team_skills": Reason(
        GuideOnlyKind.INTERPERSONAL_SKILL, "An umbrella of relational skills, not a procedure."
    ),
    "project_management_information_system": Reason(
        GuideOnlyKind.EXTERNAL_SYSTEM, "Names whatever PMIS tooling the org already runs."
    ),
    "project_reporting": Reason(
        GuideOnlyKind.JUDGMENT_ONLY,
        "Deciding what belongs in a status report for a given audience is a judgment call.",
    ),
    # integration
    "change_control_tools": Reason(
        GuideOnlyKind.EXTERNAL_SYSTEM, "Names whatever change-control tooling the org runs."
    ),
    "information_management": Reason(
        GuideOnlyKind.EXTERNAL_SYSTEM, "Names whatever information systems the org runs."
    ),
    "knowledge_management": Reason(
        GuideOnlyKind.EXTERNAL_SYSTEM, "Names whatever knowledge-management systems the org runs."
    ),
    # schedule
    "dependency_determination": Reason(
        GuideOnlyKind.WORKSHEET_ONLY,
        "A printable worksheet is written for it; there is no figure for a launcher to compute.",
    ),
    "rolling_wave_planning": Reason(
        GuideOnlyKind.WORKSHEET_ONLY,
        "A printable worksheet is written for it; there is no figure for a launcher to compute.",
    ),
    # quality
    "design_for_x": Reason(
        GuideOnlyKind.JUDGMENT_ONLY, "Applying a design guideline is a judgment call."
    ),
    "problem_solving": Reason(
        GuideOnlyKind.JUDGMENT_ONLY, "Diagnosing and resolving a problem is a judgment call."
    ),
    "quality_improvement_methods": Reason(
        GuideOnlyKind.JUDGMENT_ONLY,
        "Choosing and applying an improvement method is a judgment call.",
    ),
    "test_and_inspection_planning": Reason(
        GuideOnlyKind.JUDGMENT_ONLY, "Deciding what and how to test is a judgment call."
    ),
    "testing_product_evaluations": Reason(
        GuideOnlyKind.JUDGMENT_ONLY, "Running and judging a test is a judgment call."
    ),
    # resource
    "influencing": Reason(
        GuideOnlyKind.INTERPERSONAL_SKILL, "Influencing without authority is practiced, not run."
    ),
    "negotiation": Reason(GuideOnlyKind.INTERPERSONAL_SKILL, "Negotiating is practiced, not run."),
    # risk
    "influence_diagrams": Reason(
        GuideOnlyKind.NOT_YET_BUILT, "A diagram builder could serve this."
    ),
    "representations_of_uncertainty": Reason(
        GuideOnlyKind.NOT_YET_BUILT, "A distribution-shape picker could serve this."
    ),
    "risk_categorization": Reason(
        GuideOnlyKind.JUDGMENT_ONLY, "Sorting risks into categories is a judgment call."
    ),
    "prompt_lists": Reason(
        GuideOnlyKind.WORKSHEET_ONLY,
        "The checklist a reader fills in IS the technique; no figure follows it.",
    ),
    "sensitivity_analysis": Reason(
        GuideOnlyKind.NOT_YET_BUILT, "A tornado-diagram calculator could serve this."
    ),
    "simulation": Reason(
        GuideOnlyKind.NOT_YET_BUILT,
        "A Monte Carlo exists for schedule forecasting; it is not wired to any risk output.",
    ),
    # procurement
    "advertising": Reason(
        GuideOnlyKind.EXTERNAL_SYSTEM,
        "Reaching the market runs through channels Driftless does not own.",
    ),
    "bidder_conferences": Reason(
        GuideOnlyKind.MEETING_FORMAT, "The technique is holding the conference."
    ),
    "claims_administration": Reason(
        GuideOnlyKind.JUDGMENT_ONLY, "Adjudicating a contested claim is a judgment call."
    ),
    "inspections_and_audits": Reason(
        GuideOnlyKind.JUDGMENT_ONLY, "Inspecting a seller's work is a judgment call."
    ),
    "procurement_performance_reviews": Reason(
        GuideOnlyKind.JUDGMENT_ONLY, "Judging a seller's performance is a judgment call."
    ),
    # stakeholder
    "ground_rules": Reason(
        GuideOnlyKind.MEETING_FORMAT, "Setting ground rules is done in the kickoff meeting itself."
    ),
}


#: Every ``ARTIFACT_KINDS`` member outside ``wizard.cli.producible_kinds``, classified.
UNTRACKED_REASONS: dict[str, Reason] = {
    # Resolved from other stored rows, but has no producer form of its own.
    "activity_attributes": Reason(
        UntrackedKind.DERIVED_ON_READ, "Every task IS the activity; nothing separate to produce."
    ),
    "project_communications": Reason(
        UntrackedKind.DERIVED_ON_READ,
        "Read off a status snapshot's note; nothing separate to produce.",
    ),
    "project_management_plan": Reason(
        UntrackedKind.DERIVED_ON_READ,
        "A roll-up over the ten subsidiary plans; storing it would duplicate them.",
    ),
    "project_team_assignments": Reason(
        UntrackedKind.DERIVED_ON_READ,
        "Task.assignee_id IS the assignment; nothing separate to produce.",
    ),
    "work_performance_information": Reason(
        UntrackedKind.DERIVED_ON_READ, "Computed on read from the baseline and dated actuals."
    ),
    "work_performance_reports": Reason(
        UntrackedKind.DERIVED_ON_READ,
        "The status-snapshot series, read back; nothing separate to produce.",
    ),
    # Not tracked at all: generated, computed, or structural rather than stored.
    "project_charter": Reason(
        UntrackedKind.DERIVED_ON_READ, "Generated on read by the report engine's Charter document."
    ),
    "change_management_plan": Reason(
        UntrackedKind.DERIVED_ON_READ, "Change control is structural: approval freezes a baseline."
    ),
    "configuration_management_plan": Reason(
        UntrackedKind.DERIVED_ON_READ, "Enforced structurally — read the baseline versions."
    ),
    "development_approach": Reason(
        UntrackedKind.DERIVED_ON_READ, "Carried as Project.delivery_mode already."
    ),
    "activity_list": Reason(
        UntrackedKind.DERIVED_ON_READ, "The enumeration is activity_attributes' own count."
    ),
    "schedule_data": Reason(
        UntrackedKind.DERIVED_ON_READ,
        "Read off the same dated baseline lines and dependency edges other resolvers "
        "already read; no separate row for a wizard to file.",
    ),
    "schedule_forecasts": Reason(
        UntrackedKind.DERIVED_ON_READ, "Computed on read from sprint velocity."
    ),
    "resource_calendars": Reason(
        UntrackedKind.DERIVED_ON_READ,
        "One project calendar exists; per-person calendars do not — capacity is weekly "
        "hours on the heatmap.",
    ),
    "resource_requirements": Reason(
        UntrackedKind.DERIVED_ON_READ, "Implicit in assignment versus capacity — read the heatmap."
    ),
    "duration_estimates": Reason(
        UntrackedKind.DERIVED_ON_READ, "A task carries exactly one estimate — read the task rows."
    ),
    "cost_estimates": Reason(
        UntrackedKind.DERIVED_ON_READ, "One planned cost per baseline line — read cost_baseline."
    ),
    "independent_cost_estimates": Reason(
        UntrackedKind.EXTERNAL_DOCUMENT,
        "Pre-award estimating happens before the store's tracked boundary.",
    ),
    "performance_measurement_baseline": Reason(
        UntrackedKind.DERIVED_ON_READ, "The three approved baselines are the PMB already."
    ),
    "cost_forecasts": Reason(
        UntrackedKind.DERIVED_ON_READ,
        "EAC/ETC/VAC are computed on read from the earned-value snapshot.",
    ),
    "project_funding_requirements": Reason(
        UntrackedKind.DERIVED_ON_READ, "Arithmetic over budget lines — read cost_baseline."
    ),
    "quality_metrics": Reason(
        UntrackedKind.DERIVED_ON_READ, "Targets live on each dated measurement row already."
    ),
    "quality_control_measurements": Reason(
        UntrackedKind.DERIVED_ON_READ, "The dated measurement rows are themselves the record."
    ),
    "test_and_evaluation_documents": Reason(
        UntrackedKind.DERIVED_ON_READ, "No test record; the quality measurements are the evidence."
    ),
    "procurement_statement_of_work": Reason(
        UntrackedKind.EXTERNAL_DOCUMENT,
        "Pre-signature work happens before the store's tracked boundary.",
    ),
    "procurement_documentation": Reason(
        UntrackedKind.EXTERNAL_DOCUMENT, "The store starts at signature — read agreements."
    ),
    "procurement_strategy": Reason(
        UntrackedKind.EXTERNAL_DOCUMENT,
        "Pre-signature work happens before the store's tracked boundary.",
    ),
    "source_selection_criteria": Reason(
        UntrackedKind.EXTERNAL_DOCUMENT, "Selection precedes the store — read agreements."
    ),
    "bid_documents": Reason(
        UntrackedKind.EXTERNAL_DOCUMENT, "Solicitation happens outside the store."
    ),
    "seller_proposals": Reason(
        UntrackedKind.EXTERNAL_DOCUMENT, "Solicitation happens outside the store."
    ),
    "selected_sellers": Reason(
        UntrackedKind.EXTERNAL_DOCUMENT,
        "Selection precedes signature — read agreements for the outcome.",
    ),
    "closed_procurements": Reason(
        UntrackedKind.DERIVED_ON_READ, "Closure is an agreement status, not a separate document."
    ),
    "deliverables": Reason(
        UntrackedKind.DERIVED_ON_READ, "Done-ness is task status and percent complete already."
    ),
    "verified_deliverables": Reason(
        UntrackedKind.DERIVED_ON_READ, "Verification is not stored — read task status and percent."
    ),
    "accepted_deliverables": Reason(
        UntrackedKind.DERIVED_ON_READ, "Acceptance is 'accepted' in the sign-off ledger already."
    ),
    "final_product_service_result": Reason(
        UntrackedKind.DERIVED_ON_READ, "No closeout artifact — read the sign-off ledger."
    ),
    "final_report": Reason(
        UntrackedKind.DERIVED_ON_READ,
        "No closeout document — read the sign-off ledger for done-ness.",
    ),
    "business_case": Reason(
        UntrackedKind.EXTERNAL_DOCUMENT,
        "The store begins at the project; earlier analysis is elsewhere.",
    ),
    "benefits_management_plan": Reason(
        UntrackedKind.EXTERNAL_DOCUMENT, "Pre-authorisation value analysis happens elsewhere."
    ),
    "agreements_initial": Reason(
        UntrackedKind.EXTERNAL_DOCUMENT,
        "Pre-project agreements live elsewhere; signed ones are agreements.",
    ),
    "work_performance_data": Reason(
        UntrackedKind.DERIVED_ON_READ,
        "Computed on read; storing it would duplicate the source rows.",
    ),
    "risk_report": Reason(
        UntrackedKind.DERIVED_ON_READ,
        "The register plus derived exposure, on read — read risk_register.",
    ),
    "change_requests": Reason(
        UntrackedKind.DERIVED_ON_READ,
        "Stored as ChangeRequest rows surfaced as change_log already.",
    ),
    "approved_change_requests": Reason(
        UntrackedKind.DERIVED_ON_READ, "Approval causes a new baseline version — read change_log."
    ),
}


#: Every technique the totality suite finds carrying no ``further_reading``.
#: Owned in prose by ``tests/test_technique_totality.py``; this module holds
#: only the data and the kind vocabulary.
UNCITED_EXEMPTIONS: dict[str, Reason] = {
    "agile_release_planning": Reason(
        CitationGapKind.NARRATIVE_ONLY,
        "PMBOK-6 discusses release planning in its adaptive-environment narrative "
        "rather than defining it at a numbered tools-and-techniques clause.",
    ),
    "critical_chain_method": Reason(
        CitationGapKind.EXTENSION,
        "A Driftless extension: no PMBOK-6 clause defines it (see tt.EXTENSIONS).",
    ),
    "data_analysis": Reason(
        CitationGapKind.UNNUMBERED_GROUP,
        "An umbrella technique group PMBOK-6 names in many processes' ITTO tables "
        "across knowledge areas; its members carry the clause numbers, it does not.",
    ),
    "data_gathering": Reason(
        CitationGapKind.UNNUMBERED_GROUP,
        "An umbrella technique group PMBOK-6 names in many processes' ITTO tables "
        "across knowledge areas; its members carry the clause numbers, it does not.",
    ),
    "data_representation": Reason(
        CitationGapKind.UNNUMBERED_GROUP,
        "An umbrella technique group PMBOK-6 names in many processes' ITTO tables "
        "across knowledge areas; its members carry the clause numbers, it does not.",
    ),
    "decision_making": Reason(
        CitationGapKind.UNNUMBERED_GROUP,
        "An umbrella technique group PMBOK-6 names in many processes' ITTO tables "
        "across knowledge areas; its members carry the clause numbers, it does not.",
    ),
    "expert_judgment": Reason(
        CitationGapKind.CROSS_CUTTING,
        "Cross-cutting: PMBOK-6 lists it as a tool of nearly every process rather "
        "than defining it at one clause.",
    ),
    "financing": Reason(
        CitationGapKind.UNCONFIRMED,
        "We could not confirm which numbered PMBOK-6 clause defines it, so it is "
        "left uncited rather than cited by guess.",
    ),
    "funding_limit_reconciliation": Reason(
        CitationGapKind.MISCITED_CLAUSE,
        "Cited PMBOK-6 §7.2.3.4 — a §X.Y.3 subsection numbers a process's outputs, "
        "so no clause under it can define a technique. The correct clause could "
        "not be established from the edition, so the citation is blanked.",
    ),
    "interpersonal_and_team_skills": Reason(
        CitationGapKind.UNNUMBERED_GROUP,
        "An umbrella technique group PMBOK-6 names in many processes' ITTO tables "
        "across knowledge areas; its members carry the clause numbers, it does not.",
    ),
    "project_management_information_system": Reason(
        CitationGapKind.CROSS_CUTTING,
        "Cross-cutting: PMBOK-6 lists it as a tool of many processes rather than "
        "defining it at one clause.",
    ),
    "reserve_analysis": Reason(
        CitationGapKind.MISCITED_CLAUSE,
        "Cited PMBOK-6 §7.2.3.5 — a §X.Y.3 subsection numbers a process's outputs, "
        "so no clause under it can define a technique. The correct clause could "
        "not be established from the edition, so the citation is blanked.",
    ),
}
