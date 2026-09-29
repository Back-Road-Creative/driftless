"""Request and response models — the API's upstream gate.

Separate from the ORM classes on purpose: a bad request is refused here, before
any row can land, rather than repaired afterwards. Every closed vocabulary is
re-declared as a ``Literal`` so an unknown value returns 422 instead of reaching
the database as a CHECK-constraint 500; the ``assert``s fail the import if a
Literal and the ORM tuple it mirrors ever drift, so the boundary vocabulary and
the stored vocabulary cannot silently disagree. Every request body also carries
``_Strict``'s ``extra="forbid"`` (directly or via a ``_XxxFields`` mixin), so a
caller's typo'd or retired field name is a 422 instead of a value Pydantic quietly
threw away and a 201 that told nobody. ``_Out`` stays permissive on purpose — a
response model must keep reading back a row carrying a column its own read side
has not caught up to, never refuse one the way a request rightly does.

Most response models are their request twin plus the surrogate ``id``, and most
patch models are their request twin with every field merely un-required — both
generated once from ``_REQUESTS`` rather than written out. Two records break the
twin symmetry and are written by hand: ``StatusSnapshot`` never accepts
``percent_complete`` (it is stamped from calc, never typed), and ``SignOff`` is
append-only, so it has an ``Out`` carrying the server-stamped ``signed_at`` but
no ``Patch`` at all.
"""

import json
from datetime import date, datetime
from typing import Annotated, Any, Literal, get_args, get_type_hints

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, create_model, model_validator

from driftless.models import (
    ACQUISITION_SOURCES,
    ACQUISITION_STATUSES,
    AGILE_ROLES,
    BACKLOG_ITEM_PRIORITIES,
    BACKLOG_ITEM_STATUSES,
    BASELINE_STATUSES,
    CADENCES,
    CHANGE_STATUSES,
    COMMS_CADENCES,
    CONFLICT_APPROACHES,
    COST_CATEGORIES,
    DELIVERY_MODES,
    DEPENDENCY_KINDS,
    ESTIMATE_KINDS,
    ESTIMATE_TARGETS,
    ESTIMATE_UNITS,
    IMPEDIMENT_STATUSES,
    IMPROVEMENT_STATUSES,
    INCIDENT_SEVERITIES,
    INCIDENT_STATUSES,
    ISSUE_STATUSES,
    LESSON_CATEGORIES,
    MILESTONE_STATUSES,
    RELEASE_STATUSES,
    WORK_REQUEST_PRIORITIES,
    WORK_REQUEST_STATUSES,
    METRIC_ALWAYS,
    METRIC_SOURCE_TYPES,
    NARRATIVE_KINDS,
    OBJECTIVE_STATUSES,
    PERSON_KINDS,
    PROCUREMENT_STATUSES,
    DELIVERABLE_STATUSES,
    QUALITY_DIRECTIONS,
    RACI_ROLES,
    RAG_STATUSES,
    RESOURCE_KINDS,
    TECHNIQUE_RUN_METHODS,
    REQUIREMENT_CATEGORIES,
    REQUIREMENT_PRIORITIES,
    REQUIREMENT_STATUSES,
    RESPONSE_STATUSES,
    RESPONSE_STRATEGIES,
    RISK_KINDS,
    RISK_RESPONSES,
    RISK_STATUSES,
    SCORECARD_PERSPECTIVES,
    SCORECARD_DIRECTIONS,
    SCORECARD_CONTRIBUTION_STATUSES,
    SCORECARD_CONTRIBUTION_TYPES,
    SCORECARD_SOURCE_STATUSES,
    SIGNOFF_ACTOR_KINDS,
    SIGNOFF_DECISIONS,
    SIGNOFF_SUBJECTS,
    STAKEHOLDER_LEVELS,
    TASK_STATUSES,
)
from driftless.models.records import COST_ENTRY_AMOUNT_BOUND
from driftless.pmbok import catalog

DeliveryMode = Literal["predictive", "agile", "hybrid", "operations"]
EstimateUnit = Literal["points", "hours"]
TaskStatus = Literal["todo", "in_progress", "blocked", "done"]
BaselineStatus = Literal["draft", "approved", "superseded"]
MilestoneStatus = Literal["pending", "at_risk", "met", "missed"]
RiskStatus = Literal["open", "mitigating", "closed", "realised"]
RiskResponse = Literal["avoid", "mitigate", "transfer", "accept"]
RiskKind = Literal["threat", "opportunity"]
ResponseStrategy = Literal[
    "avoid", "mitigate", "transfer", "exploit", "enhance", "share", "accept", "escalate"
]
ResponseStatus = Literal["planned", "in_progress", "implemented", "abandoned"]
IssueStatus = Literal["open", "in_progress", "resolved", "closed"]
ChangeStatus = Literal["proposed", "approved", "rejected", "withdrawn"]
CostCategory = Literal["labour", "materials", "services", "travel", "contingency"]
Rag = Literal["green", "amber", "red"]
StakeholderLevel = Literal["low", "medium", "high"]
CommsCadence = Literal["weekly", "fortnightly", "monthly", "on_request"]
NarrativeKind = Literal[
    "assumption_log",
    "eef",
    "opa",
    "lessons_learned",
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
    "project_scope_statement",
    "requirements_documentation",
    "team_charter",
    "basis_of_estimates",
    "team_performance_assessments",
]
ProcurementStatus = Literal["draft", "active", "closed", "disputed"]
AgileRole = Literal["product_owner", "scrum_master", "developer", "stakeholder_proxy"]
BacklogItemStatus = Literal["proposed", "ready", "in_progress", "done"]
BacklogItemPriority = Literal["must_have", "should_have", "could_have", "wont_have"]
ReleaseStatus = Literal["planned", "released", "cancelled"]
ImpedimentStatus = Literal["open", "in_progress", "resolved", "closed"]
WorkRequestStatus = Literal["requested", "queued", "in_progress", "done", "cancelled"]
WorkRequestPriority = Literal["low", "medium", "high", "urgent"]
Cadence = Literal["weekly", "fortnightly", "monthly", "quarterly", "annual"]
IncidentSeverity = Literal["low", "medium", "high", "critical"]
IncidentStatus = Literal["open", "investigating", "resolved", "closed"]
ImprovementStatus = Literal["proposed", "in_progress", "done", "abandoned"]
TechniqueRunMethod = Literal["predictive", "scrum", "kanban", "department"]
LessonCategory = Literal[
    "integration",
    "scope",
    "schedule",
    "cost",
    "quality",
    "resource",
    "communications",
    "risk",
    "procurement",
    "stakeholder",
]
QualityDirection = Literal["lower_is_better", "higher_is_better", "target_band"]
SignoffSubject = Literal["threat", "process", "baseline", "gate"]
SignoffDecision = Literal["accepted", "resolved", "deferred", "rejected", "waived"]
SignoffActorKind = Literal["human", "agent"]
PersonKind = Literal["human", "agent"]
ScorecardPerspective = Literal[
    "financial", "customer_stakeholder", "internal_operations", "people_capability"
]
ObjectiveStatus = Literal["active", "paused", "retired"]
ScorecardDirection = Literal["higher_is_better", "lower_is_better"]
MetricSourceType = Literal["manual", "registered_connector"]
ScorecardSourceStatus = Literal["active", "retired"]
ScorecardContributionType = Literal["direct", "supporting"]
ScorecardContributionStatus = Literal["active", "retired"]
SourceKey = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$")]
DependencyKind = Literal["FS", "SS", "FF", "SF"]
EstimateTarget = Literal["duration", "cost", "resource"]
EstimateKind = Literal["analogous", "parametric", "three_point", "bottom_up"]
RequirementCategory = Literal[
    "business", "stakeholder", "functional", "nonfunctional", "quality", "transition"
]
RequirementPriority = Literal["must_have", "should_have", "could_have", "wont_have"]
RequirementStatus = Literal["proposed", "approved", "traced", "verified", "withdrawn"]
DeliverableStatus = Literal["planned", "in_progress", "verified", "accepted", "rejected"]
ResourceKind = Literal["people", "equipment", "material"]
RaciRole = Literal["responsible", "accountable", "consulted", "informed"]
AcquisitionSource = Literal["internal", "external"]
AcquisitionStatus = Literal["requested", "approved", "fulfilled", "cancelled"]
ConflictApproach = Literal["withdraw", "smooth", "compromise", "force", "collaborate"]

# Each Literal must name exactly the ORM tuple it mirrors — drift fails the import.
assert get_args(DeliveryMode) == DELIVERY_MODES
assert get_args(EstimateUnit) == ESTIMATE_UNITS
assert get_args(TaskStatus) == TASK_STATUSES
assert get_args(BaselineStatus) == BASELINE_STATUSES
assert get_args(MilestoneStatus) == MILESTONE_STATUSES
assert get_args(RiskStatus) == RISK_STATUSES
assert get_args(RiskResponse) == RISK_RESPONSES
assert get_args(RiskKind) == RISK_KINDS
assert get_args(ResponseStrategy) == RESPONSE_STRATEGIES
assert get_args(ResponseStatus) == RESPONSE_STATUSES
assert get_args(IssueStatus) == ISSUE_STATUSES
assert get_args(ChangeStatus) == CHANGE_STATUSES
assert get_args(CostCategory) == COST_CATEGORIES
assert get_args(Rag) == RAG_STATUSES
assert get_args(StakeholderLevel) == STAKEHOLDER_LEVELS
assert get_args(CommsCadence) == COMMS_CADENCES
assert get_args(NarrativeKind) == NARRATIVE_KINDS
assert get_args(ProcurementStatus) == PROCUREMENT_STATUSES
assert get_args(AgileRole) == AGILE_ROLES
assert get_args(BacklogItemStatus) == BACKLOG_ITEM_STATUSES
assert get_args(BacklogItemPriority) == BACKLOG_ITEM_PRIORITIES
assert get_args(ReleaseStatus) == RELEASE_STATUSES
assert get_args(ImpedimentStatus) == IMPEDIMENT_STATUSES
assert get_args(WorkRequestStatus) == WORK_REQUEST_STATUSES
assert get_args(WorkRequestPriority) == WORK_REQUEST_PRIORITIES
assert get_args(Cadence) == CADENCES
assert get_args(IncidentSeverity) == INCIDENT_SEVERITIES
assert get_args(IncidentStatus) == INCIDENT_STATUSES
assert get_args(ImprovementStatus) == IMPROVEMENT_STATUSES
assert get_args(LessonCategory) == LESSON_CATEGORIES
assert get_args(TechniqueRunMethod) == TECHNIQUE_RUN_METHODS
assert get_args(QualityDirection) == QUALITY_DIRECTIONS
assert get_args(SignoffSubject) == SIGNOFF_SUBJECTS
assert get_args(SignoffDecision) == SIGNOFF_DECISIONS
assert get_args(SignoffActorKind) == SIGNOFF_ACTOR_KINDS
assert get_args(PersonKind) == PERSON_KINDS
assert get_args(ScorecardPerspective) == SCORECARD_PERSPECTIVES
assert get_args(ScorecardDirection) == SCORECARD_DIRECTIONS
assert get_args(ScorecardSourceStatus) == SCORECARD_SOURCE_STATUSES
assert get_args(ScorecardContributionType) == SCORECARD_CONTRIBUTION_TYPES
assert get_args(ScorecardContributionStatus) == SCORECARD_CONTRIBUTION_STATUSES
assert get_args(MetricSourceType) == METRIC_SOURCE_TYPES
assert get_args(ObjectiveStatus) == OBJECTIVE_STATUSES
assert get_args(RequirementCategory) == REQUIREMENT_CATEGORIES
assert get_args(RequirementPriority) == REQUIREMENT_PRIORITIES
assert get_args(RequirementStatus) == REQUIREMENT_STATUSES
assert get_args(DeliverableStatus) == DELIVERABLE_STATUSES
assert get_args(ResourceKind) == RESOURCE_KINDS
assert get_args(RaciRole) == RACI_ROLES
assert get_args(AcquisitionSource) == ACQUISITION_SOURCES
assert get_args(AcquisitionStatus) == ACQUISITION_STATUSES
assert get_args(ConflictApproach) == CONFLICT_APPROACHES
assert get_args(DependencyKind) == DEPENDENCY_KINDS
assert get_args(EstimateTarget) == ESTIMATE_TARGETS
assert get_args(EstimateKind) == ESTIMATE_KINDS

# The PMBOK process vocabulary is code (``driftless.pmbok.catalog``), not an ORM tuple,
# so it is checked against the live catalog rather than mirrored as a 49-arm Literal.
# Annotated on purpose: the generated Patch twin copies annotations but not class
# validators, so this is what keeps a PATCH from laundering in an id a POST refuses.
_PROCESS_IDS = frozenset(process.id for process in catalog.PROCESSES)


def _known_process(value: str) -> str:
    if value not in _PROCESS_IDS:
        raise ValueError(f"{value!r} is not a PMBOK process id")
    return value


ProcessId = Annotated[str, AfterValidator(_known_process)]


def _json_object(value: str) -> str:
    """JSON text holding one object — what ``TechniqueRun`` stores; anything else is
    refused here rather than landing as a row nothing can read back as a snapshot."""
    try:
        parsed = json.loads(value)
    except ValueError as error:
        raise ValueError(f"not JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("must be a JSON object")
    return value


JsonText = Annotated[str, AfterValidator(_json_object)]

Name = Annotated[str, Field(min_length=1, max_length=200)]
Text2000 = Annotated[str, Field(min_length=1, max_length=2000)]
Effort = Annotated[float, Field(ge=0)] | None
Probability = Annotated[float, Field(ge=0, le=1)]
NonNegative = Annotated[float, Field(ge=0)]
Percent = Annotated[int, Field(ge=0, le=100)]
# CostEntry alone: a correction is a reversing negative row plus a new correct one (see
# docs/temporal-model.md), so its amount cannot be NonNegative. The bound is the same
# sanity range the DB CHECK enforces (driftless.models.records.COST_ENTRY_AMOUNT_BOUND)
# so schema and column cannot drift apart.
CostAmount = Annotated[float, Field(ge=-COST_ENTRY_AMOUNT_BOUND, le=COST_ENTRY_AMOUNT_BOUND)]


class _Out(BaseModel):
    """Mixin adding the surrogate key: responses carry it, requests never do.

    ``extra="ignore"`` is spelled out here rather than left as Pydantic's own default,
    because every generated ``*Out`` model below lists this mixin alongside a now-strict
    request class (see ``_Strict``, and — for the 29 records ``_REVISIONED`` names —
    ``_Revision`` besides), and no ``__base__`` order gives every shape both the field
    order ``test_api_export`` pins byte-for-byte and this mixin's own ``"ignore"`` over
    the request class's ``"forbid"``. So the value set here is restored explicitly after
    each ``*Out`` model is built instead (see the loop below ``_PATCH``): a response
    model must keep deserializing a row carrying a column its own read side has not
    caught up to yet, which is the ordinary shape of an in-flight migration, and must
    never refuse one the way a request rightly does.
    """

    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: int


class _Strict(BaseModel):
    """Mixin every request body uses so an unrecognised field is refused, not dropped.

    Bare ``BaseModel`` accepts a request carrying a field it does not declare and
    silently discards it: a caller who mistypes ``dscription`` for ``description``, or
    replays a field the API retired, still gets a 201 — the write looks like it landed
    and it did not. Every request model below inherits this, directly or through a
    ``_XxxFields`` mixin that also feeds a response model's ``Out`` twin, so that shape
    of mistake is a 422 at the boundary instead of a row silently missing a value its
    caller believes it set.
    """

    model_config = ConfigDict(extra="forbid")


# ---- hierarchy -----------------------------------------------------------------


class BusinessIn(_Strict):
    name: Name


class PortfolioIn(_Strict):
    name: Name
    business_id: int


class ProgramIn(_Strict):
    name: Name
    portfolio_id: int


class ProjectIn(_Strict):
    name: Name
    portfolio_id: int
    delivery_mode: DeliveryMode = "predictive"
    status_note: Annotated[str, Field(max_length=2000)] | None = None
    program_id: int | None = None
    responsible_department_id: int | None = None


class WorkstreamIn(_Strict):
    name: Name
    project_id: int


class TaskIn(_Strict):
    name: Name
    workstream_id: int
    status: TaskStatus = "todo"
    estimate: Effort = None
    estimate_unit: EstimateUnit = "points"
    actual_effort: Effort = None
    percent_complete: Percent = 0
    actual_finish: date | None = None
    forecast_finish: date | None = None
    assignee_id: int | None = None


# ---- org -----------------------------------------------------------------------


class DepartmentIn(_Strict):
    name: Name
    business_id: int


class PersonIn(_Strict):
    name: Name
    department_id: int | None = None
    role: Annotated[str, Field(max_length=100)] | None = None
    cost_rate: NonNegative = 0.0
    capacity_hours: Annotated[float, Field(gt=0)] = 40.0
    kind: PersonKind = "human"
    agent_token_id: int | None = None


# ---- department operations -------------------------------------------------


class DepartmentServiceIn(_Strict):
    department_id: int
    name: Name
    description: Annotated[str, Field(max_length=2000)] = ""
    owner: Name


class WorkRequestIn(_Strict):
    department_id: int
    service_id: int | None = None
    requester: Name
    raised_on: date
    priority: WorkRequestPriority = "medium"
    status: WorkRequestStatus = "requested"
    started_on: date | None = None
    done_on: date | None = None


class RecurringWorkIn(_Strict):
    department_id: int
    name: Name
    cadence: Cadence = "monthly"
    owner: Name
    last_completed_on: date | None = None
    next_due_on: date | None = None


class ServiceLevelIn(_Strict):
    department_id: int
    service_id: int | None = None
    measure: Name
    target: NonNegative
    window: Cadence = "monthly"


class OperatingControlIn(_Strict):
    department_id: int
    name: Name
    description: Annotated[str, Field(max_length=2000)] = ""
    owner: Name


class IncidentIn(_Strict):
    department_id: int
    control_id: int | None = None
    description: Text2000
    severity: IncidentSeverity = "medium"
    raised_on: date
    resolved_on: date | None = None
    root_cause: Annotated[str, Field(max_length=2000)] | None = None
    status: IncidentStatus = "open"


class ImprovementIn(_Strict):
    department_id: int
    what: Text2000
    why: Text2000
    owner: Name
    status: ImprovementStatus = "proposed"


# ---- schedule: typed dependencies, calendars, estimate scenarios ---------------


class _TaskDependencyFields(BaseModel):
    """``TaskDependency``'s plain fields, with no business validator — see
    ``_SprintFields`` for why ``TaskDependencyOut`` builds from this and not
    from ``TaskDependencyIn`` directly: a request-side rule must reject a bad
    *write*, but must never stop a legal *row* from being read back."""

    predecessor_task_id: int
    successor_task_id: int
    kind: DependencyKind = "FS"
    lag_days: int = 0


class TaskDependencyIn(_TaskDependencyFields, _Strict):
    """A typed precedence edge. Project scoping and cycle refusal are cross-row
    rules (``driftless.api.rules.dependency_lands_valid``); this only catches
    what one request body can see on its own — a task cannot depend on itself,
    the same CHECK the row itself carries, refused here as a plain 422 instead
    of the constraint-violation 409 a self-loop would otherwise answer with."""

    @model_validator(mode="after")
    def _not_self_dependent(self) -> "TaskDependencyIn":
        if self.predecessor_task_id == self.successor_task_id:
            raise ValueError("a task cannot depend on itself")
        return self


class ProjectCalendarIn(_Strict):
    project_id: int
    name: Name
    working_days: Annotated[int, Field(ge=0, le=127)] = 31


class CalendarExceptionIn(_Strict):
    calendar_id: int
    on_date: date
    working: bool = False
    note: Annotated[str, Field(max_length=2000)] | None = None


class _EstimateScenarioFields(BaseModel):
    """``EstimateScenario``'s plain fields, with no business validator — see
    ``_SprintFields`` for why ``EstimateScenarioOut`` builds from this rather
    than from ``EstimateScenarioIn`` directly."""

    project_id: int
    target: EstimateTarget
    subject_task_id: int | None = None
    kind: EstimateKind
    inputs: Annotated[str, Field(max_length=2000)] = "{}"
    value: float
    low: float | None = None
    high: float | None = None
    basis: Annotated[str, Field(max_length=2000)] = ""
    actor: Name
    as_of: date


class EstimateScenarioIn(_EstimateScenarioFields, _Strict):
    """``inputs`` is JSON *text*, matching ``ChangeLog.detail`` — a caller sends
    an already-encoded object, checked for validity here rather than left to
    fail silently the first time something tries to parse a stored row."""

    @model_validator(mode="after")
    def _inputs_is_json(self) -> "EstimateScenarioIn":
        try:
            json.loads(self.inputs)
        except json.JSONDecodeError as exc:
            raise ValueError(f"inputs must be valid JSON text: {exc}") from exc
        return self


# ---- scope: requirements, traces, the WBS/deliverable tree, acceptance ---------


class RequirementIn(_Strict):
    project_id: int
    code: Annotated[str, Field(min_length=1, max_length=50)]
    statement: Text2000
    category: RequirementCategory = "functional"
    priority: RequirementPriority = "should_have"
    source_stakeholder_id: int | None = None
    status: RequirementStatus = "proposed"
    actor: Name


class _RequirementTraceFields(BaseModel):
    """``RequirementTrace``'s plain fields, with no business validator — see
    ``_SprintFields`` for why ``RequirementTraceOut`` builds from this and not
    from ``RequirementTraceIn`` directly: "exactly one target" must reject a
    bad *write*, but must never stop a legal *row* from reading back."""

    requirement_id: int
    deliverable_id: int | None = None
    task_id: int | None = None
    backlog_item_id: int | None = None


class RequirementTraceIn(_RequirementTraceFields, _Strict):
    """Exactly one of ``deliverable_id``/``task_id``/``backlog_item_id`` — the
    same rule the row's own CHECK carries, refused here as a plain 422 instead
    of the constraint-violation 409 a bad request would otherwise answer with."""

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "RequirementTraceIn":
        targets = (self.deliverable_id, self.task_id, self.backlog_item_id)
        if sum(target is not None for target in targets) != 1:
            raise ValueError(
                "exactly one of deliverable_id, task_id or backlog_item_id must be set"
            )
        return self


class DeliverableIn(_Strict):
    project_id: int
    name: Name
    wbs_code: Annotated[str, Field(min_length=1, max_length=50)]
    parent_id: int | None = None
    description: Annotated[str, Field(max_length=2000)] = ""
    acceptance_criteria: Annotated[str, Field(max_length=2000)] = ""
    status: DeliverableStatus = "planned"
    accepted_on: date | None = None
    accepted_by: Annotated[str, Field(max_length=200)] | None = None


class AcceptanceRecordIn(_Strict):
    """Create body: append-only, like ``SignOffIn`` — no ``Patch`` twin exists at
    all, so a re-verification or a re-acceptance files a NEW row rather than
    editing one already on the ledger."""

    deliverable_id: int
    verified_on: date | None = None
    accepted_on: date | None = None
    actor: Name
    note: Annotated[str, Field(max_length=2000)] | None = None

    @model_validator(mode="after")
    def _has_a_date(self) -> "AcceptanceRecordIn":
        if self.verified_on is None and self.accepted_on is None:
            raise ValueError("at least one of verified_on or accepted_on must be set")
        return self


class AcceptanceRecordOut(_Out):
    deliverable_id: int
    verified_on: date | None = None
    accepted_on: date | None = None
    actor: str
    note: str | None = None


# ---- resource: types and the RBS tree, the stored RACI, acquisition, training, --
# ---- team assessment, conflict and its actions -----------------------------------


class ResourceTypeIn(_Strict):
    project_id: int
    name: Name
    kind: ResourceKind
    unit: Annotated[str, Field(min_length=1, max_length=50)] = "each"
    rate: NonNegative = 0.0


class ResourceBreakdownIn(_Strict):
    project_id: int
    resource_type_id: int
    parent_id: int | None = None
    quantity: Annotated[float, Field(gt=0)] = 1.0


class _ResponsibilityAssignmentFields(BaseModel):
    """``ResponsibilityAssignment``'s plain fields, with no business validator —
    see ``_SprintFields`` for why ``ResponsibilityAssignmentOut`` builds from this
    and not from ``ResponsibilityAssignmentIn`` directly: "exactly one target" must
    reject a bad *write*, but must never stop a legal *row* from reading back."""

    project_id: int
    deliverable_id: int | None = None
    task_id: int | None = None
    person_id: int
    role: RaciRole = "responsible"


class ResponsibilityAssignmentIn(_ResponsibilityAssignmentFields, _Strict):
    """Exactly one of ``deliverable_id``/``task_id`` — the same rule the row's own
    CHECK carries, refused here as a plain 422 instead of the constraint-violation
    409 a bad request would otherwise answer with."""

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "ResponsibilityAssignmentIn":
        targets = (self.deliverable_id, self.task_id)
        if sum(target is not None for target in targets) != 1:
            raise ValueError("exactly one of deliverable_id or task_id must be set")
        return self


class AcquisitionIn(_Strict):
    project_id: int
    resource_type_id: int
    source: AcquisitionSource = "internal"
    requested_on: date
    fulfilled_on: date | None = None
    status: AcquisitionStatus = "requested"


class TrainingRecordIn(_Strict):
    person_id: int
    topic: Name
    completed_on: date


class TeamAssessmentIn(_Strict):
    """Create body: append-only, like ``AcceptanceRecordIn`` — no ``Patch`` twin
    exists at all, so a later reading files a NEW row rather than editing one
    already on the ledger."""

    project_id: int
    assessed_on: date
    dimension: Annotated[str, Field(min_length=1, max_length=100)]
    score: Annotated[float, Field(ge=0, le=100)]
    note: Annotated[str, Field(max_length=2000)] | None = None
    actor: Name


class TeamAssessmentOut(_Out):
    project_id: int
    assessed_on: date
    dimension: str
    score: float
    note: str | None = None
    actor: str


class ConflictRecordIn(_Strict):
    project_id: int
    raised_on: date
    parties: Text2000
    approach: ConflictApproach = "collaborate"
    resolved_on: date | None = None
    actor: Name


class ConflictActionIn(_Strict):
    conflict_id: int
    owner_id: int
    due_on: date | None = None
    done_on: date | None = None


# ---- balanced scorecard -------------------------------------------------------


class _StrategicObjectiveFields(BaseModel):
    business_id: int
    perspective: ScorecardPerspective
    name: Name
    description: Annotated[str, Field(max_length=2000)] = ""
    owner: Annotated[str, Field(max_length=200)] | None = None
    status: ObjectiveStatus = "active"
    active_from: date | None = None
    active_until: date | None = None


class StrategicObjectiveIn(_StrategicObjectiveFields, _Strict):
    @model_validator(mode="after")
    def active_window_is_ordered(self) -> "StrategicObjectiveIn":
        if self.active_from is not None and self.active_until is not None:
            if self.active_from > self.active_until:
                raise ValueError("active_until must not be before active_from")
        return self


class _ScorecardMetricDefinitionFields(BaseModel):
    objective_id: int
    name: Name
    direction: ScorecardDirection
    unit: Annotated[str, Field(min_length=1, max_length=50)]
    target_value: float
    amber_threshold: float
    red_threshold: float
    cadence_days: Annotated[int, Field(gt=0)]
    owner: Annotated[str, Field(max_length=200)] | None = None
    source_type: MetricSourceType = "manual"
    source_key: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    effective_from: date = METRIC_ALWAYS


class ScorecardMetricDefinitionIn(_ScorecardMetricDefinitionFields, _Strict):
    @model_validator(mode="after")
    def thresholds_follow_direction(self) -> "ScorecardMetricDefinitionIn":
        ordered = (
            self.target_value >= self.amber_threshold >= self.red_threshold
            if self.direction == "higher_is_better"
            else self.target_value <= self.amber_threshold <= self.red_threshold
        )
        if not ordered:
            raise ValueError("target, amber, and red thresholds must follow the direction")
        if (self.source_type == "manual") != (self.source_key is None):
            raise ValueError("manual metrics have no source_key; connectors require one")
        return self


class ScorecardMetricObservationIn(_Strict):
    metric_definition_id: int
    observed_on: date
    value: float
    evidence_note: Annotated[str, Field(max_length=2000)] = ""


class ScorecardSourceIn(_Strict):
    business_id: int
    key: SourceKey
    name: Name
    description: Annotated[str, Field(max_length=2000)] = ""
    status: ScorecardSourceStatus = "active"


class ScorecardContributionIn(_Strict):
    project_id: int
    objective_id: int
    contribution_type: ScorecardContributionType
    rationale: Annotated[str, Field(max_length=2000)] = ""
    status: ScorecardContributionStatus = "active"


# ---- delivery ------------------------------------------------------------------


def approval_is_atomic(status: str, approved_at: datetime | None) -> bool:
    """Is a baseline's approval one fact rather than two half-set columns?

    ``status == "approved"`` and ``approved_at`` are the same fact in two
    columns: PMBOK reports the status, the write freeze reads the approval. Set
    one alone and the plan is either frozen but reported draft, or reported
    approved and still editable by anyone. This is the *only* statement of that
    rule — ``BaselineIn`` below settles it for a create, and the patch path
    (``api.rules._baseline_approval_stays_atomic``) asks it of the row as the patch
    will leave it, because a partial update carries only some of the fields.
    """
    return (status == "approved") == (approved_at is not None)


class _BaselineFields(BaseModel):
    """Baseline's plain fields, with no business validator — ``BaselineOut``
    builds from this rather than from ``BaselineIn``, so a stored row that
    predates the rule below still reads back instead of 500ing."""

    project_id: int
    version: Annotated[int, Field(gt=0)]
    status: BaselineStatus = "draft"
    approved_at: datetime | None = None


class BaselineIn(_BaselineFields, _Strict):
    """Approval atomicity settled in the type, not in a route's check list.

    A create carries every field, so the inconsistent body is simply not
    constructable — which is stronger than a runtime check, because a check has
    to be remembered at each registration and this one was not. Existing clients
    are unaffected: the demo seed creates a draft and approves it by PATCH.
    """

    @model_validator(mode="after")
    def _approval_atomic(self) -> "BaselineIn":
        if not approval_is_atomic(self.status, self.approved_at):
            raise ValueError("status 'approved' and approved_at must be set together")
        return self


class BaselineLineIn(_Strict):
    baseline_id: int
    task_id: int
    planned_start: date
    planned_finish: date
    planned_cost: NonNegative


class MilestoneIn(_Strict):
    project_id: int
    name: Name
    target_date: date
    baseline_date: date | None = None
    status: MilestoneStatus = "pending"


class _SprintFields(BaseModel):
    """Sprint's plain fields, with no business validators. ``SprintOut`` builds
    from this, not from ``SprintIn`` directly: a request-side rule must reject a
    bad *write*, but it must never stop a legal *row* from being read back — a
    same-day sprint is DB-legal (the CHECK allows ``>=``), so a legacy one
    predating the write-side rule below has to keep serializing."""

    project_id: int
    name: Name
    start_date: date
    end_date: date
    committed_points: Annotated[int, Field(ge=0)] = 0
    completed_points: Annotated[int, Field(ge=0)] = 0
    goal: Annotated[str, Field(max_length=2000)] | None = None
    release_id: int | None = None
    review_held_on: date | None = None
    review_notes: Annotated[str, Field(max_length=2000)] | None = None
    retrospective_held_on: date | None = None
    retrospective_notes: Annotated[str, Field(max_length=2000)] | None = None


class SprintIn(_SprintFields, _Strict):
    """The window is strictly ordered: a same-day sprint is DB-legal (the CHECK
    allows ``>=``) but zero days long, which ``calc.forecast`` refuses — so it
    is refused here, before the row can crash every later forecast render."""

    @model_validator(mode="after")
    def _window_strictly_ordered(self) -> "SprintIn":
        if self.end_date <= self.start_date:
            raise ValueError(
                f"end_date {self.end_date} must be strictly after start_date {self.start_date}"
            )
        return self


# ---- gate (a stage boundary; passage is recorded as a "gate" sign-off) ---------


class GateIn(_Strict):
    project_id: int
    name: Annotated[str, Field(min_length=1, max_length=200)]
    position: int = 0
    #: Comma-separated PMBOK clause numbers (``Process.id``); ``""`` means none.
    required_processes: Annotated[str, Field(max_length=2000)] = ""


# ---- RAID and cost -------------------------------------------------------------


class RiskIn(_Strict):
    project_id: int
    description: Text2000
    probability: Probability
    impact: NonNegative
    response: RiskResponse = "mitigate"
    owner: Annotated[str, Field(max_length=200)] | None = None
    status: RiskStatus = "open"
    kind: RiskKind = "threat"


class IssueIn(_Strict):
    project_id: int
    description: Text2000
    raised_on: date
    resolved_on: date | None = None
    status: IssueStatus = "open"
    risk_id: int | None = None


class _RiskResponseFields(BaseModel):
    """``RiskResponse``'s plain fields, with no business validator — see
    ``_SprintFields`` for why ``RiskResponseOut`` builds from this and not from
    ``RiskResponseIn`` directly: whether ``strategy`` matches its risk's ``kind``
    is a cross-row rule (``driftless.api.rules.risk_response_matches_kind``) that
    must reject a bad *write*, but must never stop a legal *row* from reading back."""

    project_id: int
    risk_id: int
    strategy: ResponseStrategy
    owner_id: int
    trigger: Text2000
    planned_action: Text2000
    residual_probability: Probability
    residual_impact: NonNegative
    cost_of_response: NonNegative = 0.0
    schedule_days: Annotated[int, Field(ge=0)] = 0
    status: ResponseStatus = "planned"
    actor: Name
    as_of: date


class RiskResponseIn(_RiskResponseFields, _Strict):
    pass


class ArtifactLinkIn(_Strict):
    """A URI reference filed against any record — ``record_kind`` is a table
    name (the same convention ``ChangeLog.table_name`` uses), ``record_id`` that
    table's primary key as text. Never a file store: ``uri`` names where the
    artifact actually lives."""

    record_kind: Annotated[str, Field(min_length=1, max_length=100)]
    record_id: Annotated[str, Field(min_length=1, max_length=100)]
    uri: Annotated[str, Field(min_length=1, max_length=2000)]
    title: Name
    sha256: Annotated[str, Field(max_length=64)] | None = None
    actor: Name
    as_of: date


class NoteIn(_Strict):
    """One append-only note filed against any record, same ``record_kind``/
    ``record_id`` convention as ``ArtifactLinkIn``. A correction is a new note
    whose ``supersedes_id`` names the note it replaces; nothing here ever
    updates or deletes a prior row."""

    record_kind: Annotated[str, Field(min_length=1, max_length=100)]
    record_id: Annotated[str, Field(min_length=1, max_length=100)]
    body: Annotated[str, Field(min_length=1)]
    actor: Name
    as_of: date
    supersedes_id: int | None = None


class TechniqueRunIn(_Strict):
    """One append-only provenance row: this project ran this technique for this
    process. ``inputs_snapshot``/``outputs_produced`` are JSON text exactly as the
    table stores them, so an exported row re-imports unchanged; the endpoint writes
    through :func:`driftless.services.technique_runs.record_run`, the ledger's one
    writer, which is where an unknown technique or process is refused."""

    project_id: int
    technique_key: Annotated[str, Field(min_length=1, max_length=100)]
    process_id: ProcessId
    actor: Name
    as_of: date
    method: TechniqueRunMethod
    source_version: Annotated[str, Field(max_length=200)] = ""
    inputs_snapshot: JsonText = "{}"
    outputs_produced: JsonText = "{}"


class ChangeRequestIn(_Strict):
    project_id: int
    description: Text2000
    raised_on: date
    status: ChangeStatus = "proposed"
    resulting_baseline_id: int | None = None
    origin_process_id: ProcessId | None = None


class _BudgetLineFields(BaseModel):
    """BudgetLine's plain fields, with no business validator. ``BudgetLineOut``
    builds from this, not from ``BudgetLineIn`` directly — see ``SprintIn``'s
    ``_SprintFields`` twin for why a request-side rule must never reach the
    response model."""

    project_id: int | None = None
    department_id: int | None = None
    category: CostCategory
    planned_amount: NonNegative


class BudgetLineIn(_BudgetLineFields, _Strict):
    """Exactly one of ``project_id``/``department_id`` — a line plans either a
    project's budget or a department's operating budget, never both and never
    neither (mirrors ``ck_budget_line_one_scope``, refused here before the row
    can reach the database's own CHECK)."""

    @model_validator(mode="after")
    def _exactly_one_scope(self) -> "BudgetLineIn":
        if (self.project_id is None) == (self.department_id is None):
            raise ValueError(
                "exactly one of project_id or department_id must be set, not "
                f"{'neither' if self.project_id is None else 'both'}"
            )
        return self


class CostEntryIn(_Strict):
    project_id: int
    category: CostCategory
    incurred_on: date
    amount: CostAmount


class StakeholderIn(_Strict):
    project_id: int
    name: Name
    interest: StakeholderLevel = "medium"
    influence: StakeholderLevel = "medium"
    comms_cadence: CommsCadence = "monthly"


# ---- narrative / quality / procurement -----------------------------------------


class NarrativeArtifactIn(_Strict):
    project_id: int
    kind: NarrativeKind
    body: Annotated[str, Field(max_length=100_000)] = ""
    updated_on: date | None = None


class _QualityMetricFields(BaseModel):
    project_id: int
    name: Name
    direction: QualityDirection
    lower_bound: float | None = None
    upper_bound: float | None = None
    unit: Annotated[str, Field(max_length=50)] | None = None


class QualityMetricIn(_QualityMetricFields, _Strict):
    @model_validator(mode="after")
    def directional_bounds_are_complete(self) -> "QualityMetricIn":
        lower, upper = self.lower_bound, self.upper_bound
        valid = (
            (self.direction == "lower_is_better" and lower is None and upper is not None)
            or (self.direction == "higher_is_better" and lower is not None and upper is None)
            or (
                self.direction == "target_band"
                and lower is not None
                and upper is not None
                and lower <= upper
            )
        )
        if not valid:
            raise ValueError("direction requires its matching lower and upper threshold(s)")
        return self


class QualityMeasurementIn(_Strict):
    project_id: int
    quality_metric_id: int | None = None
    metric: Name
    target_value: float
    actual_value: float
    unit: Annotated[str, Field(max_length=50)] | None = None
    measured_on: date


class ProcurementAgreementIn(_Strict):
    project_id: int
    vendor: Name
    description: Annotated[str, Field(max_length=2000)] = ""
    amount: NonNegative = 0.0
    status: ProcurementStatus = "draft"
    start_date: date
    end_date: date | None = None


# ---- agile ----------------------------------------------------------------------


class ProjectRoleIn(_Strict):
    project_id: int
    role: AgileRole
    holder: Name


class BacklogItemIn(_Strict):
    project_id: int
    title: Name
    description: Annotated[str, Field(max_length=2000)] = ""
    priority: BacklogItemPriority = "should_have"
    story_points: Annotated[int, Field(ge=0)] | None = None
    status: BacklogItemStatus = "proposed"
    # Effective time, the write half of the columns ``pmbok.flow_facts`` reads: a
    # caller that knows when a card was raised, picked up and finished says so, and
    # one that does not leaves them null for the ``ChangeLog`` replay to answer. The
    # model's CHECK, not this schema, is what keeps the three in order.
    created_on: date | None = None
    started_on: date | None = None
    done_on: date | None = None


class ReleaseIn(_Strict):
    project_id: int
    name: Name
    target_date: date | None = None
    status: ReleaseStatus = "planned"


class DefinitionOfDoneItemIn(_Strict):
    project_id: int
    description: Text2000


class ImpedimentIn(_Strict):
    project_id: int
    description: Text2000
    raised_by: Name
    raised_on: date
    resolved_on: date | None = None
    status: ImpedimentStatus = "open"


class LessonLearnedIn(_Strict):
    project_id: int
    raised_on: date
    category: LessonCategory
    what_happened: Text2000
    what_to_do_next_time: Text2000
    actor: Name


# Every model whose response is exactly "the request plus id" and whose patch is
# "the request, un-required". StatusSnapshot and SignOff are handled by hand below.
_REQUESTS = (
    BusinessIn,
    PortfolioIn,
    ProgramIn,
    ProjectIn,
    WorkstreamIn,
    TaskIn,
    DepartmentIn,
    PersonIn,
    StrategicObjectiveIn,
    ScorecardMetricDefinitionIn,
    ScorecardMetricObservationIn,
    ScorecardSourceIn,
    ScorecardContributionIn,
    BaselineIn,
    BaselineLineIn,
    MilestoneIn,
    SprintIn,
    GateIn,
    RiskIn,
    RiskResponseIn,
    IssueIn,
    ChangeRequestIn,
    BudgetLineIn,
    CostEntryIn,
    StakeholderIn,
    NarrativeArtifactIn,
    QualityMetricIn,
    QualityMeasurementIn,
    ProcurementAgreementIn,
    ProjectRoleIn,
    BacklogItemIn,
    ReleaseIn,
    DefinitionOfDoneItemIn,
    ImpedimentIn,
    DepartmentServiceIn,
    WorkRequestIn,
    RecurringWorkIn,
    ServiceLevelIn,
    OperatingControlIn,
    IncidentIn,
    ImprovementIn,
    TaskDependencyIn,
    ProjectCalendarIn,
    CalendarExceptionIn,
    EstimateScenarioIn,
    RequirementIn,
    RequirementTraceIn,
    DeliverableIn,
    ResourceTypeIn,
    ResourceBreakdownIn,
    ResponsibilityAssignmentIn,
    AcquisitionIn,
    TrainingRecordIn,
    ConflictRecordIn,
    ConflictActionIn,
    LessonLearnedIn,
    TechniqueRunIn,
    ArtifactLinkIn,
    NoteIn,
)


# Most request models carry no business validator, so their Out twin can inherit
# the request class directly. ``SprintIn`` and ``BaselineIn`` are the exceptions;
# each Out twin builds from the validator-free field base instead.
# A meta test asserts no Out model ever carries a model_validator, so a future
# request that adds one and forgets this map fails loudly rather than 500ing reads.
_OUT_BASE: dict[type[BaseModel], type[BaseModel]] = {
    SprintIn: _SprintFields,
    BaselineIn: _BaselineFields,
    QualityMetricIn: _QualityMetricFields,
    StrategicObjectiveIn: _StrategicObjectiveFields,
    ScorecardMetricDefinitionIn: _ScorecardMetricDefinitionFields,
    BudgetLineIn: _BudgetLineFields,
    TaskDependencyIn: _TaskDependencyFields,
    EstimateScenarioIn: _EstimateScenarioFields,
    RiskResponseIn: _RiskResponseFields,
    RequirementTraceIn: _RequirementTraceFields,
    ResponsibilityAssignmentIn: _ResponsibilityAssignmentFields,
}

# The requests whose ORM row carries ``row_revision`` — every entity a PATCH or DELETE
# can reach. Absent: CostEntry, ScorecardMetricObservation, QualityMeasurement (plus
# StatusSnapshot, SignOff and auth's User/ApiToken, which have no twin generated below
# at all) — none of them PATCH or DELETE, so a token would guard nothing (see
# ``driftless.models.hierarchy``'s module docstring). Hand-listed because the loop below
# needs to know, per request, which extra base to add; policed as an exact set against
# the ORM's own mappers by
# ``test_row_revision_is_on_every_out_model_whose_row_carries_the_column`` in
# ``tests/test_api_write.py``, so a model that gains or drops the column and this list
# forgets to follow fails there rather than drifting quietly.
_REVISIONED: frozenset[type[BaseModel]] = frozenset(
    {
        BusinessIn,
        PortfolioIn,
        ProgramIn,
        ProjectIn,
        WorkstreamIn,
        TaskIn,
        DepartmentIn,
        PersonIn,
        StrategicObjectiveIn,
        ScorecardMetricDefinitionIn,
        ScorecardSourceIn,
        ScorecardContributionIn,
        BaselineIn,
        BaselineLineIn,
        MilestoneIn,
        SprintIn,
        RiskIn,
        IssueIn,
        ChangeRequestIn,
        BudgetLineIn,
        StakeholderIn,
        NarrativeArtifactIn,
        QualityMetricIn,
        ProcurementAgreementIn,
        ProjectRoleIn,
        BacklogItemIn,
        ReleaseIn,
        DefinitionOfDoneItemIn,
        ImpedimentIn,
        DepartmentServiceIn,
        WorkRequestIn,
        RecurringWorkIn,
        ServiceLevelIn,
        OperatingControlIn,
        IncidentIn,
        ImprovementIn,
        TaskDependencyIn,
        ProjectCalendarIn,
        CalendarExceptionIn,
        EstimateScenarioIn,
        RiskResponseIn,
        RequirementIn,
        RequirementTraceIn,
        DeliverableIn,
        ResourceTypeIn,
        ResourceBreakdownIn,
        ResponsibilityAssignmentIn,
        AcquisitionIn,
        TrainingRecordIn,
        ConflictRecordIn,
        ConflictActionIn,
        LessonLearnedIn,
        ArtifactLinkIn,
    }
)


class _Revision(BaseModel):
    """Mixin adding the concurrency token a stale ``If-Match`` is checked against.

    Its own mixin rather than a field on ``_Out``: ``_Out`` is shared by every
    response model, including the create-only and append-only ones no PATCH or
    DELETE route ever reaches, so a token on ``_Out`` itself would either lie
    about those rows carrying one or force ``int | None`` on the 25 that always
    do and hide the very distinction this field exists to state. Listed *before*
    ``_Out`` in ``__base__`` below (see the ``_REVISIONED`` branch), which lands
    ``row_revision`` *after* ``id`` in field order — ``id`` keeps the position
    both ``test_api_export`` and ``bin/driftless-import.py``'s "id comes from an
    export" check already expect of it.
    """

    row_revision: int


# Parent-scoping foreign keys a partial update must never move. Re-filing a row
# under a different parent silently lifts it out of one project's rollup and
# drops it into another's — a relocated budget line, a milestone injected into a
# foreign project's numbers, a baseline line pointed across projects. A misfiled
# row is corrected by delete+recreate, not re-parented, so these fields are
# excluded from every generated patch twin *by construction*: there is no field
# to set, hence no per-entity check to forget. ``SignOffIn`` already proves the
# same "drop it, don't merely relax it" idiom by hand, at the limit — it has no
# ``Patch`` at all because none of its fields may move; this generalizes it to
# the whole class of parent FKs so the hole cannot regrow.
_FROZEN_FK = frozenset(
    {
        "project_id",
        "workstream_id",
        "baseline_id",
        "task_id",
        "quality_metric_id",
        "release_id",
        "department_id",
        "calendar_id",
        "predecessor_task_id",
        "successor_task_id",
        "requirement_id",
        "deliverable_id",
        "backlog_item_id",
        "resource_type_id",
        "conflict_id",
        # Which token acts as an agent gates the sign-off ledger; a partial
        # update must not quietly move that binding onto another credential.
        "agent_token_id",
    }
)

# The parents that genuinely move, each behind a boundary check rather than a
# bare open field: a workstream changes project (its tasks follow it, validated
# against the target mode's unit), and a task changes workstream *within its own
# project* — the API refuses a target workstream owned by a different project, so
# no rollup ever loses or gains a task by a partial update. Freezing the task's
# FK outright is what made a misfiled task uncorrectable once its baseline was
# approved: the patch was inert, and delete+recreate is refused while a line
# exists. ``Person`` keeps its own ``department_id`` movable for the ordinary
# reason a person changes desks — nothing downstream freezes an approved plan
# the way a baseline line does, so there is no boundary check to write. Every
# other leaf record freezes its ``department_id``/``project_id`` FK.
_KEEPS_MOVABLE_FK: dict[type[BaseModel], frozenset[str]] = {
    WorkstreamIn: frozenset({"project_id"}),
    TaskIn: frozenset({"workstream_id"}),
    PersonIn: frozenset({"department_id"}),
}

# Versioned-definition fields (docs/temporal-model.md): changed by a NEW dated row.
# Deliberately NOT in ``_frozen_fk``, which STRIPS a frozen key -- right for
# re-parenting, rarely meant. A threshold edit is always meant, so these stay in the
# body for ``extra="forbid"`` to refuse by name rather than discard in silence.
_FROZEN_VERSION_FIELDS: dict[type[BaseModel], frozenset[str]] = {
    ScorecardMetricDefinitionIn: frozenset(
        "name direction target_value amber_threshold red_threshold cadence_days "
        "effective_from".split()
    ),
}


def _frozen_fk(request: type[BaseModel]) -> frozenset[str]:
    """The parent-scoping FKs a partial update for ``request`` must never move.

    Shared by ``_unrequired`` (which leaves them off the patch twin's fields
    entirely) and ``_dropping_frozen_fk`` (which strips them from a patch body
    before ``_Strict``'s ``extra="forbid"`` ever sees them) — one computation
    feeding both the field list and the pre-validation strip, so the two can
    never name a different set of FKs by accident.
    """
    # Objectives begin at one business scope. Moving one through a partial
    # update would silently detach its later metric/benefit history from the
    # strategy it was created to serve, so correct a mistaken scope by
    # delete-and-recreate just like the other non-movable parent links.
    objective_parent = (
        frozenset({"business_id"})
        if request in (StrategicObjectiveIn, ScorecardSourceIn)
        else frozenset({"objective_id"})
        if request in (ScorecardMetricDefinitionIn, ScorecardContributionIn)
        else frozenset()
    )
    return (_FROZEN_FK | objective_parent) - _KEEPS_MOVABLE_FK.get(request, frozenset())


def _unrequired(request: type[BaseModel]) -> dict[str, Any]:
    """Every field of ``request``, merely un-required — the annotation is untouched.

    Dropping the requirement rather than widening the type to ``| None`` is what
    makes a partial update honest: an omitted key stays out of
    ``model_fields_set`` and never reaches the row, while an explicit null is
    still checked against the column, so ``{"estimate": null}`` clears a
    nullable field and ``{"name": null}`` is refused as a 422. The ``None``
    default is never read — every write path dumps with ``exclude_unset``.

    Parent-scoping foreign keys (``_frozen_fk``) are dropped entirely rather than
    un-required: a partial update must not be able to re-parent a row at all.
    """
    frozen = _frozen_fk(request) | _FROZEN_VERSION_FIELDS.get(request, frozenset())
    hints = get_type_hints(request, include_extras=True)
    return {name: (hint, None) for name, hint in hints.items() if name not in frozen}


def _dropping_frozen_fk(request: type[BaseModel]) -> Any:
    """A ``model_validator(mode="before")`` stripping ``request``'s frozen FKs from a
    patch body before ``_Strict``'s ``extra="forbid"`` ever inspects the keys.

    A parent-scoping FK is deliberately absent from the patch twin's own fields (see
    ``_unrequired``), so a caller who includes one is meant to have the attempt land as
    a no-op — the row stays under its own parent while every other field in the same
    body still applies. ``extra="forbid"`` cannot tell that shape of "known but inert"
    key apart from a genuine typo, so the frozen keys are removed from the raw payload
    here, before the strict check runs, and every other unrecognised key still 422s.
    """
    frozen = _frozen_fk(request)

    @model_validator(mode="before")
    def _strip(data: Any) -> Any:
        if isinstance(data, dict) and frozen:
            return {key: value for key, value in data.items() if key not in frozen}
        return data

    return _strip


_OUT = {
    r: create_model(
        r.__name__[:-2] + "Out",
        __base__=(_Revision, _Out, _OUT_BASE.get(r, r))
        if r in _REVISIONED
        else (_Out, _OUT_BASE.get(r, r)),
    )
    for r in _REQUESTS
}
_PATCH = {
    r: create_model(
        r.__name__[:-2] + "Patch",
        __base__=_Strict,
        __validators__={"_drop_frozen_fk": _dropping_frozen_fk(r)},
        **_unrequired(r),
    )
    for r in _REQUESTS
}

BusinessOut = _OUT[BusinessIn]
PortfolioOut = _OUT[PortfolioIn]
ProgramOut = _OUT[ProgramIn]
ProjectOut = _OUT[ProjectIn]
WorkstreamOut = _OUT[WorkstreamIn]
TaskOut = _OUT[TaskIn]
DepartmentOut = _OUT[DepartmentIn]
PersonOut = _OUT[PersonIn]
StrategicObjectiveOut = _OUT[StrategicObjectiveIn]
ScorecardMetricDefinitionOut = _OUT[ScorecardMetricDefinitionIn]
ScorecardMetricObservationOut = create_model(
    "ScorecardMetricObservationOut", __base__=(_Out, ScorecardMetricObservationIn)
)


# A generated *Out model lists a now-strict request class as a sibling base alongside
# _Out (directly, or via a _OUT_BASE fields-only mixin) — and, for the 29 records
# _REVISIONED names, _Revision besides. No tuple order gives every shape both the field
# order test_api_export.py pins byte-for-byte AND _Out's own "ignore" over the request
# class's "forbid", so the value is restored explicitly after creation instead of relied
# on from __base__ order: a response model must keep reading back a row carrying a
# column its own read side has not caught up to, never refuse one the way a request
# rightly does. __base__ order IS what field order comes from: the request's own fields
# first, then id, then — for the 25 — row_revision last (see _Revision's docstring).
for _out_model in (*_OUT.values(), ScorecardMetricObservationOut):
    _out_model.model_config["extra"] = "ignore"
    _out_model.model_rebuild(force=True)
del _out_model
ScorecardSourceOut = _OUT[ScorecardSourceIn]
ScorecardContributionOut = _OUT[ScorecardContributionIn]
BaselineOut = _OUT[BaselineIn]
BaselineLineOut = _OUT[BaselineLineIn]
MilestoneOut = _OUT[MilestoneIn]
SprintOut = _OUT[SprintIn]
GateOut = _OUT[GateIn]
RiskOut = _OUT[RiskIn]
RiskResponseOut = _OUT[RiskResponseIn]
IssueOut = _OUT[IssueIn]
ChangeRequestOut = _OUT[ChangeRequestIn]
BudgetLineOut = _OUT[BudgetLineIn]
CostEntryOut = _OUT[CostEntryIn]
StakeholderOut = _OUT[StakeholderIn]
NarrativeArtifactOut = _OUT[NarrativeArtifactIn]
QualityMetricOut = _OUT[QualityMetricIn]
QualityMeasurementOut = _OUT[QualityMeasurementIn]
ProcurementAgreementOut = _OUT[ProcurementAgreementIn]
ProjectRoleOut = _OUT[ProjectRoleIn]
BacklogItemOut = _OUT[BacklogItemIn]
ReleaseOut = _OUT[ReleaseIn]
DefinitionOfDoneItemOut = _OUT[DefinitionOfDoneItemIn]
ImpedimentOut = _OUT[ImpedimentIn]
DepartmentServiceOut = _OUT[DepartmentServiceIn]
WorkRequestOut = _OUT[WorkRequestIn]
RecurringWorkOut = _OUT[RecurringWorkIn]
ServiceLevelOut = _OUT[ServiceLevelIn]
OperatingControlOut = _OUT[OperatingControlIn]
IncidentOut = _OUT[IncidentIn]
ImprovementOut = _OUT[ImprovementIn]
TaskDependencyOut = _OUT[TaskDependencyIn]
ProjectCalendarOut = _OUT[ProjectCalendarIn]
CalendarExceptionOut = _OUT[CalendarExceptionIn]
EstimateScenarioOut = _OUT[EstimateScenarioIn]
RequirementOut = _OUT[RequirementIn]
RequirementTraceOut = _OUT[RequirementTraceIn]
DeliverableOut = _OUT[DeliverableIn]
ResourceTypeOut = _OUT[ResourceTypeIn]
ResourceBreakdownOut = _OUT[ResourceBreakdownIn]
ResponsibilityAssignmentOut = _OUT[ResponsibilityAssignmentIn]
AcquisitionOut = _OUT[AcquisitionIn]
TrainingRecordOut = _OUT[TrainingRecordIn]
ConflictRecordOut = _OUT[ConflictRecordIn]
ConflictActionOut = _OUT[ConflictActionIn]
LessonLearnedOut = _OUT[LessonLearnedIn]
TechniqueRunOut = _OUT[TechniqueRunIn]
ArtifactLinkOut = _OUT[ArtifactLinkIn]
ArtifactLinkPatch = _PATCH[ArtifactLinkIn]
NoteOut = _OUT[NoteIn]

BusinessPatch = _PATCH[BusinessIn]
PortfolioPatch = _PATCH[PortfolioIn]
ProgramPatch = _PATCH[ProgramIn]
ProjectPatch = _PATCH[ProjectIn]
WorkstreamPatch = _PATCH[WorkstreamIn]
TaskPatch = _PATCH[TaskIn]
DepartmentPatch = _PATCH[DepartmentIn]
PersonPatch = _PATCH[PersonIn]
StrategicObjectivePatch = _PATCH[StrategicObjectiveIn]
ScorecardMetricDefinitionPatch = _PATCH[ScorecardMetricDefinitionIn]
ScorecardSourcePatch = _PATCH[ScorecardSourceIn]
ScorecardContributionPatch = _PATCH[ScorecardContributionIn]
BaselinePatch = _PATCH[BaselineIn]
BaselineLinePatch = _PATCH[BaselineLineIn]
MilestonePatch = _PATCH[MilestoneIn]
SprintPatch = _PATCH[SprintIn]
RiskPatch = _PATCH[RiskIn]
RiskResponsePatch = _PATCH[RiskResponseIn]
IssuePatch = _PATCH[IssueIn]
ChangeRequestPatch = _PATCH[ChangeRequestIn]
BudgetLinePatch = _PATCH[BudgetLineIn]
StakeholderPatch = _PATCH[StakeholderIn]
NarrativeArtifactPatch = _PATCH[NarrativeArtifactIn]
QualityMetricPatch = _PATCH[QualityMetricIn]
ProcurementAgreementPatch = _PATCH[ProcurementAgreementIn]
ProjectRolePatch = _PATCH[ProjectRoleIn]
BacklogItemPatch = _PATCH[BacklogItemIn]
ReleasePatch = _PATCH[ReleaseIn]
DefinitionOfDoneItemPatch = _PATCH[DefinitionOfDoneItemIn]
ImpedimentPatch = _PATCH[ImpedimentIn]
DepartmentServicePatch = _PATCH[DepartmentServiceIn]
WorkRequestPatch = _PATCH[WorkRequestIn]
RecurringWorkPatch = _PATCH[RecurringWorkIn]
ServiceLevelPatch = _PATCH[ServiceLevelIn]
OperatingControlPatch = _PATCH[OperatingControlIn]
IncidentPatch = _PATCH[IncidentIn]
ImprovementPatch = _PATCH[ImprovementIn]
TaskDependencyPatch = _PATCH[TaskDependencyIn]
ProjectCalendarPatch = _PATCH[ProjectCalendarIn]
CalendarExceptionPatch = _PATCH[CalendarExceptionIn]
EstimateScenarioPatch = _PATCH[EstimateScenarioIn]
RequirementPatch = _PATCH[RequirementIn]
RequirementTracePatch = _PATCH[RequirementTraceIn]
DeliverablePatch = _PATCH[DeliverableIn]
ResourceTypePatch = _PATCH[ResourceTypeIn]
ResourceBreakdownPatch = _PATCH[ResourceBreakdownIn]
ResponsibilityAssignmentPatch = _PATCH[ResponsibilityAssignmentIn]
AcquisitionPatch = _PATCH[AcquisitionIn]
TrainingRecordPatch = _PATCH[TrainingRecordIn]
ConflictRecordPatch = _PATCH[ConflictRecordIn]
ConflictActionPatch = _PATCH[ConflictActionIn]
LessonLearnedPatch = _PATCH[LessonLearnedIn]


# ---- status snapshot (append-only: percent_complete is stamped, never patched) -


class StatusSnapshotIn(_Strict):
    """Create body: no ``percent_complete`` — the endpoint stamps it from calc.

    A hand-typed ``percent_complete`` in the body is refused outright (``_Strict``'s
    ``extra="forbid"``) rather than merely dropped, so a caller who believes their
    figure stuck gets a 422 telling them so instead of a 201 that quietly used the
    computed one.
    """

    project_id: int
    taken_on: date
    rag_status: Rag = "green"
    note: Annotated[str, Field(max_length=2000)] | None = None


class StatusSnapshotOut(_Out):
    """Response carries the stamped ``percent_complete`` the create computed."""

    project_id: int
    taken_on: date
    percent_complete: int
    rag_status: Rag
    note: str | None = None


# ---- sign-off (append-only: create + read, never patched) ----------------------


class SignOffIn(_Strict):
    """Create body: no ``signal`` — the endpoint stamps it from the live score.

    ``signal`` is the suppression threshold a signed-off threat re-crosses when it
    regresses, so accepting it from the request let one posted number mute a threat
    permanently. Absent from the body exactly as ``percent_complete`` is absent from
    :class:`StatusSnapshotIn`, and dropped rather than kept-and-ignored so there is no
    field left to be wrong about. A body that posts one anyway is refused outright
    (``_Strict``'s ``extra="forbid"``) rather than merely ignored — the hidden
    ``signal`` input is gone from both ``threats.html`` and ``home.html``, so a 422
    here can only mean a hand-crafted request, never the UI's own write tripping its
    own guardrail. The 201 body carries the value actually stored, so no caller is
    told a claim it did not get. See :func:`driftless.services.sign_offs.stamped_signal`.

    A **process** decision must carry ``as_of`` — see :meth:`_process_records_its_as_of`.
    """

    project_id: int | None = None
    subject_kind: SignoffSubject
    subject_ref: Annotated[str, Field(min_length=1, max_length=200)]
    decision: SignoffDecision
    signed_by: Annotated[str, Field(min_length=1, max_length=200)] = "unknown"
    note: Annotated[str, Field(max_length=2000)] | None = None
    as_of: date | None = None

    @model_validator(mode="after")
    def _process_records_its_as_of(self) -> "SignOffIn":
        """A process sign-off names the assessment date it was judged at.

        ``as_of`` is what bounds the ledger: ``pmbok.state.current_sign_off`` skips a
        decision recorded against a later date than the one being asked about, so this
        week's waiver cannot rewrite last month's process map. A row with no recorded
        date has nothing to compare and applies at *every* as-of — for a process that
        is the whole state of the cell, so one dateless JSON post silently re-scored
        every map back to the store's first day. Required here, at the only write path,
        rather than repaired downstream: the browser form always stamps the date, so
        the bound is now unconditional instead of a convention the JSON route could opt
        out of.

        Threat decisions keep it optional: theirs suppress only while the stamped
        ``signal`` holds, and :func:`driftless.services.sign_offs.stamped_signal` records ``None``
        without an as-of to score at — a dateless threat sign-off suppresses nothing.

        A **gate** decision needs the same bound, for the same reason: readiness is
        read off ``pmbok.state.gate_readiness`` at a date, exactly like a process's
        own state, so a dateless gate sign-off has no as-of to judge readiness at.
        """
        if self.subject_kind in ("process", "gate") and self.as_of is None:
            raise ValueError(
                f"as_of is required for a {self.subject_kind} sign-off: it bounds the ledger"
            )
        return self


class SignOffOut(_Out):
    project_id: int | None = None
    subject_kind: SignoffSubject
    subject_ref: str
    decision: SignoffDecision
    signal: float | None = None
    signed_by: str
    signed_by_kind: SignoffActorKind = "human"
    note: str | None = None
    as_of: date | None = None
    signed_at: datetime
