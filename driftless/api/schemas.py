"""Request and response models — the API's upstream gate.

Separate from the ORM classes on purpose: a bad request is refused here, before
any row can land, rather than repaired afterwards. Every closed vocabulary is
re-declared as a ``Literal`` so an unknown value returns 422 instead of reaching
the database as a CHECK-constraint 500; the ``assert``s fail the import if a
Literal and the ORM tuple it mirrors ever drift, so the boundary vocabulary and
the stored vocabulary cannot silently disagree.

Most response models are their request twin plus the surrogate ``id``, and most
patch models are their request twin with every field merely un-required — both
generated once from ``_REQUESTS`` rather than written out. Two records break the
twin symmetry and are written by hand: ``StatusSnapshot`` never accepts
``percent_complete`` (it is stamped from calc, never typed), and ``SignOff`` is
append-only, so it has an ``Out`` carrying the server-stamped ``signed_at`` but
no ``Patch`` at all.
"""

from datetime import date, datetime
from typing import Annotated, Any, Literal, get_args, get_type_hints

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, create_model, model_validator

from driftless.models import (
    BASELINE_STATUSES,
    CHANGE_STATUSES,
    COMMS_CADENCES,
    COST_CATEGORIES,
    DELIVERY_MODES,
    ESTIMATE_UNITS,
    ISSUE_STATUSES,
    MILESTONE_STATUSES,
    NARRATIVE_KINDS,
    PROCUREMENT_STATUSES,
    RAG_STATUSES,
    RISK_RESPONSES,
    RISK_STATUSES,
    SIGNOFF_DECISIONS,
    SIGNOFF_SUBJECTS,
    STAKEHOLDER_LEVELS,
    TASK_STATUSES,
)
from driftless.pmbok import catalog

DeliveryMode = Literal["predictive", "agile", "hybrid"]
EstimateUnit = Literal["points", "hours"]
TaskStatus = Literal["todo", "in_progress", "blocked", "done"]
BaselineStatus = Literal["draft", "approved", "superseded"]
MilestoneStatus = Literal["pending", "at_risk", "met", "missed"]
RiskStatus = Literal["open", "mitigating", "closed", "realised"]
RiskResponse = Literal["avoid", "mitigate", "transfer", "accept"]
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
SignoffSubject = Literal["threat", "process"]
SignoffDecision = Literal["accepted", "resolved", "deferred", "rejected", "waived"]

# Each Literal must name exactly the ORM tuple it mirrors — drift fails the import.
assert get_args(DeliveryMode) == DELIVERY_MODES
assert get_args(EstimateUnit) == ESTIMATE_UNITS
assert get_args(TaskStatus) == TASK_STATUSES
assert get_args(BaselineStatus) == BASELINE_STATUSES
assert get_args(MilestoneStatus) == MILESTONE_STATUSES
assert get_args(RiskStatus) == RISK_STATUSES
assert get_args(RiskResponse) == RISK_RESPONSES
assert get_args(IssueStatus) == ISSUE_STATUSES
assert get_args(ChangeStatus) == CHANGE_STATUSES
assert get_args(CostCategory) == COST_CATEGORIES
assert get_args(Rag) == RAG_STATUSES
assert get_args(StakeholderLevel) == STAKEHOLDER_LEVELS
assert get_args(CommsCadence) == COMMS_CADENCES
assert get_args(NarrativeKind) == NARRATIVE_KINDS
assert get_args(ProcurementStatus) == PROCUREMENT_STATUSES
assert get_args(SignoffSubject) == SIGNOFF_SUBJECTS
assert get_args(SignoffDecision) == SIGNOFF_DECISIONS

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

Name = Annotated[str, Field(min_length=1, max_length=200)]
Text2000 = Annotated[str, Field(min_length=1, max_length=2000)]
Effort = Annotated[float, Field(ge=0)] | None
Probability = Annotated[float, Field(ge=0, le=1)]
NonNegative = Annotated[float, Field(ge=0)]
Percent = Annotated[int, Field(ge=0, le=100)]


class _Out(BaseModel):
    """Mixin adding the surrogate key: responses carry it, requests never do."""

    model_config = ConfigDict(from_attributes=True)
    id: int


# ---- hierarchy -----------------------------------------------------------------


class BusinessIn(BaseModel):
    name: Name


class PortfolioIn(BaseModel):
    name: Name
    business_id: int


class ProgramIn(BaseModel):
    name: Name
    portfolio_id: int


class ProjectIn(BaseModel):
    name: Name
    portfolio_id: int
    delivery_mode: DeliveryMode = "predictive"
    status_note: Annotated[str, Field(max_length=2000)] | None = None
    program_id: int | None = None
    responsible_department_id: int | None = None


class WorkstreamIn(BaseModel):
    name: Name
    project_id: int


class TaskIn(BaseModel):
    name: Name
    workstream_id: int
    status: TaskStatus = "todo"
    estimate: Effort = None
    estimate_unit: EstimateUnit = "points"
    actual_effort: Effort = None
    percent_complete: Percent = 0
    assignee_id: int | None = None


# ---- org -----------------------------------------------------------------------


class DepartmentIn(BaseModel):
    name: Name
    business_id: int


class PersonIn(BaseModel):
    name: Name
    department_id: int | None = None
    role: Annotated[str, Field(max_length=100)] | None = None
    cost_rate: NonNegative = 0.0
    capacity_hours: Annotated[float, Field(gt=0)] = 40.0


# ---- delivery ------------------------------------------------------------------


def approval_is_atomic(status: str, approved_at: datetime | None) -> bool:
    """Is a baseline's approval one fact rather than two half-set columns?

    ``status == "approved"`` and ``approved_at`` are the same fact in two
    columns: PMBOK reports the status, the write freeze reads the approval. Set
    one alone and the plan is either frozen but reported draft, or reported
    approved and still editable by anyone. This is the *only* statement of that
    rule — ``BaselineIn`` below settles it for a create, and the patch path
    (``api.app._baseline_approval_stays_atomic``) asks it of the row as the patch
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


class BaselineIn(_BaselineFields):
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


class BaselineLineIn(BaseModel):
    baseline_id: int
    task_id: int
    planned_start: date
    planned_finish: date
    planned_cost: NonNegative


class MilestoneIn(BaseModel):
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


class SprintIn(_SprintFields):
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


# ---- RAID and cost -------------------------------------------------------------


class RiskIn(BaseModel):
    project_id: int
    description: Text2000
    probability: Probability
    impact: NonNegative
    response: RiskResponse = "mitigate"
    owner: Annotated[str, Field(max_length=200)] | None = None
    status: RiskStatus = "open"


class IssueIn(BaseModel):
    project_id: int
    description: Text2000
    raised_on: date
    resolved_on: date | None = None
    status: IssueStatus = "open"
    risk_id: int | None = None


class ChangeRequestIn(BaseModel):
    project_id: int
    description: Text2000
    raised_on: date
    status: ChangeStatus = "proposed"
    resulting_baseline_id: int | None = None
    origin_process_id: ProcessId | None = None


class BudgetLineIn(BaseModel):
    project_id: int
    category: CostCategory
    planned_amount: NonNegative


class CostEntryIn(BaseModel):
    project_id: int
    category: CostCategory
    incurred_on: date
    amount: NonNegative


class StakeholderIn(BaseModel):
    project_id: int
    name: Name
    interest: StakeholderLevel = "medium"
    influence: StakeholderLevel = "medium"
    comms_cadence: CommsCadence = "monthly"


# ---- narrative / quality / procurement -----------------------------------------


class NarrativeArtifactIn(BaseModel):
    project_id: int
    kind: NarrativeKind
    body: Annotated[str, Field(max_length=100_000)] = ""
    updated_on: date | None = None


class QualityMeasurementIn(BaseModel):
    project_id: int
    metric: Name
    target_value: float
    actual_value: float
    unit: Annotated[str, Field(max_length=50)] | None = None
    measured_on: date


class ProcurementAgreementIn(BaseModel):
    project_id: int
    vendor: Name
    description: Annotated[str, Field(max_length=2000)] = ""
    amount: NonNegative = 0.0
    status: ProcurementStatus = "draft"
    start_date: date
    end_date: date | None = None


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
    BaselineIn,
    BaselineLineIn,
    MilestoneIn,
    SprintIn,
    RiskIn,
    IssueIn,
    ChangeRequestIn,
    BudgetLineIn,
    CostEntryIn,
    StakeholderIn,
    NarrativeArtifactIn,
    QualityMeasurementIn,
    ProcurementAgreementIn,
)


# Most request models carry no business validator, so their Out twin can inherit
# the request class directly. ``SprintIn`` and ``BaselineIn`` are the exceptions;
# each Out twin builds from the validator-free field base instead.
# A meta test asserts no Out model ever carries a model_validator, so a future
# request that adds one and forgets this map fails loudly rather than 500ing reads.
_OUT_BASE: dict[type[BaseModel], type[BaseModel]] = {
    SprintIn: _SprintFields,
    BaselineIn: _BaselineFields,
}

# Parent-scoping foreign keys a partial update must never move. Re-filing a row
# under a different parent silently lifts it out of one project's rollup and
# drops it into another's — a relocated cost entry, a milestone injected into a
# foreign project's numbers, a baseline line pointed across projects. A misfiled
# row is corrected by delete+recreate, not re-parented, so these fields are
# excluded from every generated patch twin *by construction*: there is no field
# to set, hence no per-entity check to forget. ``StatusSnapshotPatch`` already
# proves the shape by hand (it drops the stamped percent); this generalizes it to
# the whole class of parent FKs so the hole cannot regrow.
_FROZEN_FK = frozenset({"project_id", "workstream_id", "baseline_id", "task_id"})

# The parents that genuinely move, each behind a boundary check rather than a
# bare open field: a workstream changes project (its tasks follow it, validated
# against the target mode's unit), and a task changes workstream *within its own
# project* — the API refuses a target workstream owned by a different project, so
# no rollup ever loses or gains a task by a partial update. Freezing the task's
# FK outright is what made a misfiled task uncorrectable once its baseline was
# approved: the patch was inert, and delete+recreate is refused while a line
# exists. Every other leaf record freezes its FK.
_KEEPS_MOVABLE_FK: dict[type[BaseModel], frozenset[str]] = {
    WorkstreamIn: frozenset({"project_id"}),
    TaskIn: frozenset({"workstream_id"}),
}


def _unrequired(request: type[BaseModel]) -> dict[str, Any]:
    """Every field of ``request``, merely un-required — the annotation is untouched.

    Dropping the requirement rather than widening the type to ``| None`` is what
    makes a partial update honest: an omitted key stays out of
    ``model_fields_set`` and never reaches the row, while an explicit null is
    still checked against the column, so ``{"estimate": null}`` clears a
    nullable field and ``{"name": null}`` is refused as a 422. The ``None``
    default is never read — every write path dumps with ``exclude_unset``.

    Parent-scoping foreign keys (``_FROZEN_FK``) are dropped entirely rather than
    un-required: a partial update must not be able to re-parent a row at all.
    """
    frozen = _FROZEN_FK - _KEEPS_MOVABLE_FK.get(request, frozenset())
    hints = get_type_hints(request, include_extras=True)
    return {name: (hint, None) for name, hint in hints.items() if name not in frozen}


_OUT = {
    r: create_model(r.__name__[:-2] + "Out", __base__=(_Out, _OUT_BASE.get(r, r)))
    for r in _REQUESTS
}
_PATCH = {r: create_model(r.__name__[:-2] + "Patch", **_unrequired(r)) for r in _REQUESTS}

BusinessOut = _OUT[BusinessIn]
PortfolioOut = _OUT[PortfolioIn]
ProgramOut = _OUT[ProgramIn]
ProjectOut = _OUT[ProjectIn]
WorkstreamOut = _OUT[WorkstreamIn]
TaskOut = _OUT[TaskIn]
DepartmentOut = _OUT[DepartmentIn]
PersonOut = _OUT[PersonIn]
BaselineOut = _OUT[BaselineIn]
BaselineLineOut = _OUT[BaselineLineIn]
MilestoneOut = _OUT[MilestoneIn]
SprintOut = _OUT[SprintIn]
RiskOut = _OUT[RiskIn]
IssueOut = _OUT[IssueIn]
ChangeRequestOut = _OUT[ChangeRequestIn]
BudgetLineOut = _OUT[BudgetLineIn]
CostEntryOut = _OUT[CostEntryIn]
StakeholderOut = _OUT[StakeholderIn]
NarrativeArtifactOut = _OUT[NarrativeArtifactIn]
QualityMeasurementOut = _OUT[QualityMeasurementIn]
ProcurementAgreementOut = _OUT[ProcurementAgreementIn]

BusinessPatch = _PATCH[BusinessIn]
PortfolioPatch = _PATCH[PortfolioIn]
ProgramPatch = _PATCH[ProgramIn]
ProjectPatch = _PATCH[ProjectIn]
WorkstreamPatch = _PATCH[WorkstreamIn]
TaskPatch = _PATCH[TaskIn]
DepartmentPatch = _PATCH[DepartmentIn]
PersonPatch = _PATCH[PersonIn]
BaselinePatch = _PATCH[BaselineIn]
BaselineLinePatch = _PATCH[BaselineLineIn]
MilestonePatch = _PATCH[MilestoneIn]
SprintPatch = _PATCH[SprintIn]
RiskPatch = _PATCH[RiskIn]
IssuePatch = _PATCH[IssueIn]
ChangeRequestPatch = _PATCH[ChangeRequestIn]
BudgetLinePatch = _PATCH[BudgetLineIn]
CostEntryPatch = _PATCH[CostEntryIn]
StakeholderPatch = _PATCH[StakeholderIn]
NarrativeArtifactPatch = _PATCH[NarrativeArtifactIn]
QualityMeasurementPatch = _PATCH[QualityMeasurementIn]
ProcurementAgreementPatch = _PATCH[ProcurementAgreementIn]


# ---- status snapshot (percent_complete is stamped, never accepted) -------------


class StatusSnapshotIn(BaseModel):
    """Create body: no ``percent_complete`` — the endpoint stamps it from calc."""

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


class StatusSnapshotPatch(BaseModel):
    """Only the human-authored fields are editable; the stamped percent is not."""

    rag_status: Rag | None = None
    note: Annotated[str, Field(max_length=2000)] | None = None


# ---- sign-off (append-only: create + read, never patched) ----------------------


class SignOffIn(BaseModel):
    """Create body: no ``signal`` — the endpoint stamps it from the live score.

    ``signal`` is the suppression threshold a signed-off threat re-crosses when it
    regresses, so accepting it from the request let one posted number mute a threat
    permanently. Absent from the body exactly as ``percent_complete`` is absent from
    :class:`StatusSnapshotIn`, and dropped rather than kept-and-ignored so there is no
    field left to be wrong about. An extra key is ignored rather than refused — both
    browser forms still post one, and a 4xx would break the UI's own write — and the
    201 body carries the value actually stored, so no caller is told a claim it did
    not get. See :func:`driftless.api.app.stamped_signal`.

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
        ``signal`` holds, and :func:`driftless.api.app.stamped_signal` records ``None``
        without an as-of to score at — a dateless threat sign-off suppresses nothing.
        """
        if self.subject_kind == "process" and self.as_of is None:
            raise ValueError("as_of is required for a process sign-off: it bounds the ledger")
        return self


class SignOffOut(_Out):
    project_id: int | None = None
    subject_kind: SignoffSubject
    subject_ref: str
    decision: SignoffDecision
    signal: float | None = None
    signed_by: str
    note: str | None = None
    as_of: date | None = None
    signed_at: datetime
