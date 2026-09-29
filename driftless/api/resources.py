"""Which resources the API serves, and the rules each one is registered with.

:mod:`driftless.api.crud` knows how to give a resource its routes; this module is the
only place that says which resources exist. Split by family rather than listed flat --
the hierarchy, the org chart, the scorecard, delivery, governance and the record ledgers
each have their own registrar below, so a new resource is added next to the ones it
belongs with instead of at the end of one long block.

``register_resources`` is the public name because :mod:`driftless.api.app` calls it; the
per-family registrars are private because nothing outside this module does.
"""

from __future__ import annotations

from fastapi import FastAPI

from driftless.api import schemas as s
from driftless.api.crud import creates, reads, writes
from driftless.api.rules import (
    baseline_delete_only_while_open,
    baseline_patch_stays_valid,
    contribution_patch_stays_in_business,
    contribution_stays_in_business,
    deliverable_lands_valid,
    deliverable_stays_valid,
    department_children_stay_home,
    dependency_lands_valid,
    estimate_scenario_lands_valid,
    estimate_scenario_stays_valid,
    line_lands_open_and_inside,
    line_leaves_baseline_open,
    line_still_open_and_inside,
    link_stays_in_department,
    link_stays_in_project,
    metric_source_is_registered,
    portfolio_children_stay_home,
    program_projects_still_home,
    project_still_consistent,
    requirement_trace_lands_valid,
    requirement_trace_stays_valid,
    resource_breakdown_lands_valid,
    resource_breakdown_stays_valid,
    responsibility_assignment_lands_valid,
    responsibility_assignment_stays_valid,
    risk_response_lands_valid,
    risk_response_stays_valid,
    sprint_window_still_ordered,
    task_patch_stays_valid,
    workstream_patch_stays_valid,
)
from driftless.models import (
    AcceptanceRecord,
    Acquisition,
    ApiToken,
    ArtifactLink,
    BacklogItem,
    Baseline,
    BaselineLine,
    BudgetLine,
    Business,
    CalendarException,
    ChangeRequest,
    ConflictAction,
    ConflictRecord,
    CostEntry,
    DefinitionOfDoneItem,
    Deliverable,
    Department,
    DepartmentService,
    EstimateScenario,
    Gate,
    Impediment,
    Improvement,
    Incident,
    Issue,
    LessonLearned,
    Milestone,
    NarrativeArtifact,
    Note,
    OperatingControl,
    Person,
    Portfolio,
    Program,
    ProcurementAgreement,
    Project,
    ProjectCalendar,
    ProjectRole,
    QualityMeasurement,
    QualityMetric,
    RecurringWork,
    Release,
    Requirement,
    RequirementTrace,
    ResourceBreakdown,
    ResourceType,
    ResponsibilityAssignment,
    Risk,
    RiskResponse,
    ScorecardContribution,
    ScorecardMetricDefinition,
    ScorecardMetricObservation,
    ScorecardSource,
    ServiceLevel,
    SignOff,
    TechniqueRun,
    Sprint,
    Stakeholder,
    StatusSnapshot,
    StrategicObjective,
    Task,
    TaskDependency,
    TeamAssessment,
    TrainingRecord,
    WorkRequest,
    Workstream,
)


def _register_hierarchy(app: FastAPI) -> None:
    """Business -> portfolio -> program -> project -> workstream -> task."""
    reads(app, "/businesses", Business, s.BusinessOut)
    reads(app, "/portfolios", Portfolio, s.PortfolioOut)
    reads(app, "/programs", Program, s.ProgramOut)
    reads(app, "/projects", Project, s.ProjectOut)
    reads(app, "/workstreams", Workstream, s.WorkstreamOut)
    reads(app, "/tasks", Task, s.TaskOut)

    writes(app, "/businesses", Business, s.BusinessOut, s.BusinessPatch)
    writes(
        app,
        "/portfolios",
        Portfolio,
        s.PortfolioOut,
        s.PortfolioPatch,
        portfolio_children_stay_home,
        business_id=Business,
    )
    writes(
        app,
        "/programs",
        Program,
        s.ProgramOut,
        s.ProgramPatch,
        program_projects_still_home,
        portfolio_id=Portfolio,
    )
    writes(
        app,
        "/projects",
        Project,
        s.ProjectOut,
        s.ProjectPatch,
        project_still_consistent,
        portfolio_id=Portfolio,
        program_id=Program,
        responsible_department_id=Department,
    )
    writes(
        app,
        "/workstreams",
        Workstream,
        s.WorkstreamOut,
        s.WorkstreamPatch,
        workstream_patch_stays_valid,
        project_id=Project,
    )
    writes(app, "/tasks", Task, s.TaskOut, s.TaskPatch, task_patch_stays_valid, assignee_id=Person)


def _register_org(app: FastAPI) -> None:
    """Who the work is assigned to: departments and the people in them."""
    # ---- org ------------------------------------------------------------------------
    creates(app, "/departments", Department, s.DepartmentIn, s.DepartmentOut, business_id=Business)
    reads(app, "/departments", Department, s.DepartmentOut)
    writes(
        app,
        "/departments",
        Department,
        s.DepartmentOut,
        s.DepartmentPatch,
        department_children_stay_home,
        business_id=Business,
    )

    creates(
        app,
        "/people",
        Person,
        s.PersonIn,
        s.PersonOut,
        department_id=Department,
        agent_token_id=ApiToken,
    )
    reads(app, "/people", Person, s.PersonOut)
    writes(
        app,
        "/people",
        Person,
        s.PersonOut,
        s.PersonPatch,
        department_id=Department,
        agent_token_id=ApiToken,
    )


def _register_department_operations(app: FastAPI) -> None:
    """What a department runs day to day: services, work queue, recurring
    work, SLAs, controls, incidents, improvements."""
    creates(
        app,
        "/department-services",
        DepartmentService,
        s.DepartmentServiceIn,
        s.DepartmentServiceOut,
        department_id=Department,
    )
    reads(app, "/department-services", DepartmentService, s.DepartmentServiceOut)
    writes(
        app,
        "/department-services",
        DepartmentService,
        s.DepartmentServiceOut,
        s.DepartmentServicePatch,
        department_id=Department,
    )

    _service_lands, _service_stays = link_stays_in_department(DepartmentService, "service_id")
    creates(
        app,
        "/work-requests",
        WorkRequest,
        s.WorkRequestIn,
        s.WorkRequestOut,
        _service_lands,
        department_id=Department,
        service_id=DepartmentService,
    )
    reads(app, "/work-requests", WorkRequest, s.WorkRequestOut)
    writes(
        app,
        "/work-requests",
        WorkRequest,
        s.WorkRequestOut,
        s.WorkRequestPatch,
        _service_stays,
        department_id=Department,
        service_id=DepartmentService,
    )

    creates(
        app,
        "/recurring-work",
        RecurringWork,
        s.RecurringWorkIn,
        s.RecurringWorkOut,
        department_id=Department,
    )
    reads(app, "/recurring-work", RecurringWork, s.RecurringWorkOut)
    writes(
        app,
        "/recurring-work",
        RecurringWork,
        s.RecurringWorkOut,
        s.RecurringWorkPatch,
        department_id=Department,
    )

    _sl_service_lands, _sl_service_stays = link_stays_in_department(DepartmentService, "service_id")
    creates(
        app,
        "/service-levels",
        ServiceLevel,
        s.ServiceLevelIn,
        s.ServiceLevelOut,
        _sl_service_lands,
        department_id=Department,
        service_id=DepartmentService,
    )
    reads(app, "/service-levels", ServiceLevel, s.ServiceLevelOut)
    writes(
        app,
        "/service-levels",
        ServiceLevel,
        s.ServiceLevelOut,
        s.ServiceLevelPatch,
        _sl_service_stays,
        department_id=Department,
        service_id=DepartmentService,
    )

    creates(
        app,
        "/operating-controls",
        OperatingControl,
        s.OperatingControlIn,
        s.OperatingControlOut,
        department_id=Department,
    )
    reads(app, "/operating-controls", OperatingControl, s.OperatingControlOut)
    writes(
        app,
        "/operating-controls",
        OperatingControl,
        s.OperatingControlOut,
        s.OperatingControlPatch,
        department_id=Department,
    )

    _control_lands, _control_stays = link_stays_in_department(OperatingControl, "control_id")
    creates(
        app,
        "/incidents",
        Incident,
        s.IncidentIn,
        s.IncidentOut,
        _control_lands,
        department_id=Department,
        control_id=OperatingControl,
    )
    reads(app, "/incidents", Incident, s.IncidentOut)
    writes(
        app,
        "/incidents",
        Incident,
        s.IncidentOut,
        s.IncidentPatch,
        _control_stays,
        department_id=Department,
        control_id=OperatingControl,
    )

    creates(
        app,
        "/improvements",
        Improvement,
        s.ImprovementIn,
        s.ImprovementOut,
        department_id=Department,
    )
    reads(app, "/improvements", Improvement, s.ImprovementOut)
    writes(
        app,
        "/improvements",
        Improvement,
        s.ImprovementOut,
        s.ImprovementPatch,
        department_id=Department,
    )


def _register_schedule(app: FastAPI) -> None:
    """The network and duration-estimation layer: typed dependencies, calendars,
    estimate scenarios."""
    creates(
        app,
        "/task-dependencies",
        TaskDependency,
        s.TaskDependencyIn,
        s.TaskDependencyOut,
        dependency_lands_valid,
        predecessor_task_id=Task,
        successor_task_id=Task,
    )
    reads(app, "/task-dependencies", TaskDependency, s.TaskDependencyOut)
    writes(
        app,
        "/task-dependencies",
        TaskDependency,
        s.TaskDependencyOut,
        s.TaskDependencyPatch,
        predecessor_task_id=Task,
        successor_task_id=Task,
    )

    creates(
        app,
        "/project-calendars",
        ProjectCalendar,
        s.ProjectCalendarIn,
        s.ProjectCalendarOut,
        project_id=Project,
    )
    reads(app, "/project-calendars", ProjectCalendar, s.ProjectCalendarOut)
    writes(
        app,
        "/project-calendars",
        ProjectCalendar,
        s.ProjectCalendarOut,
        s.ProjectCalendarPatch,
        project_id=Project,
    )

    creates(
        app,
        "/calendar-exceptions",
        CalendarException,
        s.CalendarExceptionIn,
        s.CalendarExceptionOut,
        calendar_id=ProjectCalendar,
    )
    reads(app, "/calendar-exceptions", CalendarException, s.CalendarExceptionOut)
    writes(
        app,
        "/calendar-exceptions",
        CalendarException,
        s.CalendarExceptionOut,
        s.CalendarExceptionPatch,
        calendar_id=ProjectCalendar,
    )

    creates(
        app,
        "/estimate-scenarios",
        EstimateScenario,
        s.EstimateScenarioIn,
        s.EstimateScenarioOut,
        estimate_scenario_lands_valid,
        project_id=Project,
        subject_task_id=Task,
    )
    reads(app, "/estimate-scenarios", EstimateScenario, s.EstimateScenarioOut)
    writes(
        app,
        "/estimate-scenarios",
        EstimateScenario,
        s.EstimateScenarioOut,
        s.EstimateScenarioPatch,
        estimate_scenario_stays_valid,
        project_id=Project,
        subject_task_id=Task,
    )


def _register_scorecard(app: FastAPI) -> None:
    """Strategy and how it is measured: objectives, contributions, metrics, sources."""
    # ---- balanced scorecard -------------------------------------------------------
    creates(
        app,
        "/strategic-objectives",
        StrategicObjective,
        s.StrategicObjectiveIn,
        s.StrategicObjectiveOut,
        business_id=Business,
    )
    reads(app, "/strategic-objectives", StrategicObjective, s.StrategicObjectiveOut)
    writes(
        app,
        "/strategic-objectives",
        StrategicObjective,
        s.StrategicObjectiveOut,
        s.StrategicObjectivePatch,
        business_id=Business,
    )
    creates(
        app,
        "/scorecard-contributions",
        ScorecardContribution,
        s.ScorecardContributionIn,
        s.ScorecardContributionOut,
        contribution_stays_in_business,
        project_id=Project,
        objective_id=StrategicObjective,
    )
    reads(app, "/scorecard-contributions", ScorecardContribution, s.ScorecardContributionOut)
    writes(
        app,
        "/scorecard-contributions",
        ScorecardContribution,
        s.ScorecardContributionOut,
        s.ScorecardContributionPatch,
        contribution_patch_stays_in_business,
        project_id=Project,
        objective_id=StrategicObjective,
    )
    creates(
        app,
        "/metric-definitions",
        ScorecardMetricDefinition,
        s.ScorecardMetricDefinitionIn,
        s.ScorecardMetricDefinitionOut,
        metric_source_is_registered,
        objective_id=StrategicObjective,
    )
    reads(app, "/metric-definitions", ScorecardMetricDefinition, s.ScorecardMetricDefinitionOut)
    writes(
        app,
        "/metric-definitions",
        ScorecardMetricDefinition,
        s.ScorecardMetricDefinitionOut,
        s.ScorecardMetricDefinitionPatch,
        objective_id=StrategicObjective,
    )
    creates(
        app,
        "/scorecard-sources",
        ScorecardSource,
        s.ScorecardSourceIn,
        s.ScorecardSourceOut,
        business_id=Business,
    )
    reads(app, "/scorecard-sources", ScorecardSource, s.ScorecardSourceOut)
    writes(
        app,
        "/scorecard-sources",
        ScorecardSource,
        s.ScorecardSourceOut,
        s.ScorecardSourcePatch,
        business_id=Business,
    )
    creates(
        app,
        "/metric-observations",
        ScorecardMetricObservation,
        s.ScorecardMetricObservationIn,
        s.ScorecardMetricObservationOut,
        metric_definition_id=ScorecardMetricDefinition,
    )
    reads(app, "/metric-observations", ScorecardMetricObservation, s.ScorecardMetricObservationOut)


def _register_delivery(app: FastAPI) -> None:
    """The plan the work is measured against: baselines, lines, milestones, sprints."""
    # ---- delivery -------------------------------------------------------------------
    # No create check: ``BaselineIn`` itself refuses a half-approved body, so this
    # registration cannot forget the rule the way a ``check=`` argument can be.
    creates(app, "/baselines", Baseline, s.BaselineIn, s.BaselineOut, project_id=Project)
    reads(app, "/baselines", Baseline, s.BaselineOut)
    writes(
        app,
        "/baselines",
        Baseline,
        s.BaselineOut,
        s.BaselinePatch,
        baseline_patch_stays_valid,
        delete_check=baseline_delete_only_while_open,
        project_id=Project,
    )

    creates(
        app,
        "/baseline-lines",
        BaselineLine,
        s.BaselineLineIn,
        s.BaselineLineOut,
        line_lands_open_and_inside,
        baseline_id=Baseline,
        task_id=Task,
    )
    reads(app, "/baseline-lines", BaselineLine, s.BaselineLineOut)
    writes(
        app,
        "/baseline-lines",
        BaselineLine,
        s.BaselineLineOut,
        s.BaselineLinePatch,
        line_still_open_and_inside,
        delete_check=line_leaves_baseline_open,
        baseline_id=Baseline,
        task_id=Task,
    )

    creates(app, "/milestones", Milestone, s.MilestoneIn, s.MilestoneOut, project_id=Project)
    reads(app, "/milestones", Milestone, s.MilestoneOut)
    writes(app, "/milestones", Milestone, s.MilestoneOut, s.MilestonePatch, project_id=Project)

    creates(
        app, "/sprints", Sprint, s.SprintIn, s.SprintOut, project_id=Project, release_id=Release
    )
    reads(app, "/sprints", Sprint, s.SprintOut)
    writes(
        app,
        "/sprints",
        Sprint,
        s.SprintOut,
        s.SprintPatch,
        sprint_window_still_ordered,
        project_id=Project,
    )


def _register_agile(app: FastAPI) -> None:
    """Agile execution records: roles, backlog items, releases, DoD, impediments."""
    creates(
        app, "/project-roles", ProjectRole, s.ProjectRoleIn, s.ProjectRoleOut, project_id=Project
    )
    reads(app, "/project-roles", ProjectRole, s.ProjectRoleOut)
    writes(
        app, "/project-roles", ProjectRole, s.ProjectRoleOut, s.ProjectRolePatch, project_id=Project
    )

    creates(
        app, "/backlog-items", BacklogItem, s.BacklogItemIn, s.BacklogItemOut, project_id=Project
    )
    reads(app, "/backlog-items", BacklogItem, s.BacklogItemOut)
    writes(
        app,
        "/backlog-items",
        BacklogItem,
        s.BacklogItemOut,
        s.BacklogItemPatch,
        project_id=Project,
    )

    creates(app, "/releases", Release, s.ReleaseIn, s.ReleaseOut, project_id=Project)
    reads(app, "/releases", Release, s.ReleaseOut)
    writes(app, "/releases", Release, s.ReleaseOut, s.ReleasePatch, project_id=Project)

    creates(
        app,
        "/definition-of-done-items",
        DefinitionOfDoneItem,
        s.DefinitionOfDoneItemIn,
        s.DefinitionOfDoneItemOut,
        project_id=Project,
    )
    reads(app, "/definition-of-done-items", DefinitionOfDoneItem, s.DefinitionOfDoneItemOut)
    writes(
        app,
        "/definition-of-done-items",
        DefinitionOfDoneItem,
        s.DefinitionOfDoneItemOut,
        s.DefinitionOfDoneItemPatch,
        project_id=Project,
    )

    creates(app, "/impediments", Impediment, s.ImpedimentIn, s.ImpedimentOut, project_id=Project)
    reads(app, "/impediments", Impediment, s.ImpedimentOut)
    writes(app, "/impediments", Impediment, s.ImpedimentOut, s.ImpedimentPatch, project_id=Project)


def _register_governance(app: FastAPI) -> None:
    """What threatens the plan and what it costs: risks, issues, changes, money, people."""
    # ---- RAID and cost --------------------------------------------------------------
    creates(app, "/risks", Risk, s.RiskIn, s.RiskOut, project_id=Project)
    reads(app, "/risks", Risk, s.RiskOut)
    writes(app, "/risks", Risk, s.RiskOut, s.RiskPatch, project_id=Project)

    creates(
        app,
        "/risk-responses",
        RiskResponse,
        s.RiskResponseIn,
        s.RiskResponseOut,
        risk_response_lands_valid,
        project_id=Project,
        risk_id=Risk,
        owner_id=Person,
    )
    reads(app, "/risk-responses", RiskResponse, s.RiskResponseOut)
    # TechniqueRun: append-only, like SignOff — the bespoke create is
    # driftless.api.app.post_technique_run (through services.technique_runs.record_run,
    # the ledger's one writer); read and export only here, never PATCH or DELETE.
    reads(app, "/technique-runs", TechniqueRun, s.TechniqueRunOut)
    writes(
        app,
        "/risk-responses",
        RiskResponse,
        s.RiskResponseOut,
        s.RiskResponsePatch,
        risk_response_stays_valid,
        project_id=Project,
        risk_id=Risk,
        owner_id=Person,
    )

    _risk_lands, _risk_stays = link_stays_in_project(Risk, "risk_id")
    creates(
        app, "/issues", Issue, s.IssueIn, s.IssueOut, _risk_lands, project_id=Project, risk_id=Risk
    )
    reads(app, "/issues", Issue, s.IssueOut)
    writes(
        app,
        "/issues",
        Issue,
        s.IssueOut,
        s.IssuePatch,
        _risk_stays,
        project_id=Project,
        risk_id=Risk,
    )

    _plan_lands, _plan_stays = link_stays_in_project(Baseline, "resulting_baseline_id")
    creates(
        app,
        "/change-requests",
        ChangeRequest,
        s.ChangeRequestIn,
        s.ChangeRequestOut,
        _plan_lands,
        project_id=Project,
        resulting_baseline_id=Baseline,
    )
    reads(app, "/change-requests", ChangeRequest, s.ChangeRequestOut)
    writes(
        app,
        "/change-requests",
        ChangeRequest,
        s.ChangeRequestOut,
        s.ChangeRequestPatch,
        _plan_stays,
        project_id=Project,
        resulting_baseline_id=Baseline,
    )

    creates(
        app,
        "/budget-lines",
        BudgetLine,
        s.BudgetLineIn,
        s.BudgetLineOut,
        project_id=Project,
        department_id=Department,
    )
    reads(app, "/budget-lines", BudgetLine, s.BudgetLineOut)
    writes(
        app,
        "/budget-lines",
        BudgetLine,
        s.BudgetLineOut,
        s.BudgetLinePatch,
        project_id=Project,
        department_id=Department,
    )

    creates(app, "/cost-entries", CostEntry, s.CostEntryIn, s.CostEntryOut, project_id=Project)
    reads(app, "/cost-entries", CostEntry, s.CostEntryOut)

    creates(
        app, "/stakeholders", Stakeholder, s.StakeholderIn, s.StakeholderOut, project_id=Project
    )
    reads(app, "/stakeholders", Stakeholder, s.StakeholderOut)
    writes(
        app, "/stakeholders", Stakeholder, s.StakeholderOut, s.StakeholderPatch, project_id=Project
    )

    # ArtifactLink: a URI reference filed against any record, keyed by
    # (record_kind, record_id) rather than a parent FK, so no ``parents`` kwarg
    # names one -- the row can point at any table, not just Project's children.
    creates(app, "/artifact-links", ArtifactLink, s.ArtifactLinkIn, s.ArtifactLinkOut)
    reads(app, "/artifact-links", ArtifactLink, s.ArtifactLinkOut)
    writes(app, "/artifact-links", ArtifactLink, s.ArtifactLinkOut, s.ArtifactLinkPatch)

    # Note: append-only like TechniqueRun -- create and read only, no ``writes()``
    # call, so PATCH/DELETE never get a route at all. The model layer refuses an
    # update or delete on its own (``NoteIsAppendOnly``); this is the second,
    # independent refusal at the API surface.
    creates(app, "/notes", Note, s.NoteIn, s.NoteOut)
    reads(app, "/notes", Note, s.NoteOut)


def _register_records(app: FastAPI) -> None:
    """The append-only ledgers and the artefacts hung off a project."""
    reads(app, "/status-snapshots", StatusSnapshot, s.StatusSnapshotOut)

    # ---- narrative / quality / procurement ------------------------------------------
    creates(
        app,
        "/narrative-artifacts",
        NarrativeArtifact,
        s.NarrativeArtifactIn,
        s.NarrativeArtifactOut,
        project_id=Project,
    )
    reads(app, "/narrative-artifacts", NarrativeArtifact, s.NarrativeArtifactOut)
    writes(
        app,
        "/narrative-artifacts",
        NarrativeArtifact,
        s.NarrativeArtifactOut,
        s.NarrativeArtifactPatch,
        project_id=Project,
    )

    creates(
        app,
        "/quality-metrics",
        QualityMetric,
        s.QualityMetricIn,
        s.QualityMetricOut,
        project_id=Project,
    )
    reads(app, "/quality-metrics", QualityMetric, s.QualityMetricOut)
    writes(
        app,
        "/quality-metrics",
        QualityMetric,
        s.QualityMetricOut,
        s.QualityMetricPatch,
        project_id=Project,
    )

    _quality_metric_lands, _ = link_stays_in_project(QualityMetric, "quality_metric_id")
    creates(
        app,
        "/quality-measurements",
        QualityMeasurement,
        s.QualityMeasurementIn,
        s.QualityMeasurementOut,
        _quality_metric_lands,
        project_id=Project,
        quality_metric_id=QualityMetric,
    )
    reads(app, "/quality-measurements", QualityMeasurement, s.QualityMeasurementOut)

    creates(
        app,
        "/procurement-agreements",
        ProcurementAgreement,
        s.ProcurementAgreementIn,
        s.ProcurementAgreementOut,
        project_id=Project,
    )
    reads(app, "/procurement-agreements", ProcurementAgreement, s.ProcurementAgreementOut)
    writes(
        app,
        "/procurement-agreements",
        ProcurementAgreement,
        s.ProcurementAgreementOut,
        s.ProcurementAgreementPatch,
        project_id=Project,
    )

    creates(
        app,
        "/lessons-learned",
        LessonLearned,
        s.LessonLearnedIn,
        s.LessonLearnedOut,
        project_id=Project,
    )
    reads(app, "/lessons-learned", LessonLearned, s.LessonLearnedOut)
    writes(
        app,
        "/lessons-learned",
        LessonLearned,
        s.LessonLearnedOut,
        s.LessonLearnedPatch,
        project_id=Project,
    )

    # SignOff: append-only — the bespoke create is driftless.api.app.post_sign_off;
    # reads only here, no patch or delete.
    reads(app, "/sign-offs", SignOff, s.SignOffOut)

    # Gate: a thin definition row (plan gap G20) — readiness and passage are both
    # computed/ledger-derived, never stored here, so create + read is the whole
    # surface; no patch or delete yet.
    creates(app, "/gates", Gate, s.GateIn, s.GateOut, project_id=Project)
    reads(app, "/gates", Gate, s.GateOut)


def _register_scope(app: FastAPI) -> None:
    """Requirements, their traces, the WBS/deliverable tree, and its acceptance ledger."""
    _stakeholder_lands, _stakeholder_stays = link_stays_in_project(
        Stakeholder, "source_stakeholder_id"
    )
    creates(
        app,
        "/requirements",
        Requirement,
        s.RequirementIn,
        s.RequirementOut,
        _stakeholder_lands,
        project_id=Project,
        source_stakeholder_id=Stakeholder,
    )
    reads(app, "/requirements", Requirement, s.RequirementOut)
    writes(
        app,
        "/requirements",
        Requirement,
        s.RequirementOut,
        s.RequirementPatch,
        _stakeholder_stays,
        project_id=Project,
        source_stakeholder_id=Stakeholder,
    )

    creates(
        app,
        "/requirement-traces",
        RequirementTrace,
        s.RequirementTraceIn,
        s.RequirementTraceOut,
        requirement_trace_lands_valid,
        requirement_id=Requirement,
        deliverable_id=Deliverable,
        task_id=Task,
        backlog_item_id=BacklogItem,
    )
    reads(app, "/requirement-traces", RequirementTrace, s.RequirementTraceOut)
    writes(
        app,
        "/requirement-traces",
        RequirementTrace,
        s.RequirementTraceOut,
        s.RequirementTracePatch,
        requirement_trace_stays_valid,
        requirement_id=Requirement,
        deliverable_id=Deliverable,
        task_id=Task,
        backlog_item_id=BacklogItem,
    )

    creates(
        app,
        "/deliverables",
        Deliverable,
        s.DeliverableIn,
        s.DeliverableOut,
        deliverable_lands_valid,
        project_id=Project,
        parent_id=Deliverable,
    )
    reads(app, "/deliverables", Deliverable, s.DeliverableOut)
    writes(
        app,
        "/deliverables",
        Deliverable,
        s.DeliverableOut,
        s.DeliverablePatch,
        deliverable_stays_valid,
        project_id=Project,
        parent_id=Deliverable,
    )

    # AcceptanceRecord: append-only, like SignOff — create and read only, no
    # patch or delete: a re-verification or a re-acceptance files a new row.
    creates(
        app,
        "/acceptance-records",
        AcceptanceRecord,
        s.AcceptanceRecordIn,
        s.AcceptanceRecordOut,
        deliverable_id=Deliverable,
    )
    reads(app, "/acceptance-records", AcceptanceRecord, s.AcceptanceRecordOut)


def _register_resource(app: FastAPI) -> None:
    """Resource types and the RBS tree, the stored RACI, acquisition, training,
    team assessment, conflict and its actions."""
    creates(
        app,
        "/resource-types",
        ResourceType,
        s.ResourceTypeIn,
        s.ResourceTypeOut,
        project_id=Project,
    )
    reads(app, "/resource-types", ResourceType, s.ResourceTypeOut)
    writes(
        app,
        "/resource-types",
        ResourceType,
        s.ResourceTypeOut,
        s.ResourceTypePatch,
        project_id=Project,
    )

    creates(
        app,
        "/resource-breakdowns",
        ResourceBreakdown,
        s.ResourceBreakdownIn,
        s.ResourceBreakdownOut,
        resource_breakdown_lands_valid,
        project_id=Project,
        resource_type_id=ResourceType,
        parent_id=ResourceBreakdown,
    )
    reads(app, "/resource-breakdowns", ResourceBreakdown, s.ResourceBreakdownOut)
    writes(
        app,
        "/resource-breakdowns",
        ResourceBreakdown,
        s.ResourceBreakdownOut,
        s.ResourceBreakdownPatch,
        resource_breakdown_stays_valid,
        project_id=Project,
        resource_type_id=ResourceType,
        parent_id=ResourceBreakdown,
    )

    creates(
        app,
        "/responsibility-assignments",
        ResponsibilityAssignment,
        s.ResponsibilityAssignmentIn,
        s.ResponsibilityAssignmentOut,
        responsibility_assignment_lands_valid,
        project_id=Project,
        deliverable_id=Deliverable,
        task_id=Task,
        person_id=Person,
    )
    reads(
        app, "/responsibility-assignments", ResponsibilityAssignment, s.ResponsibilityAssignmentOut
    )
    writes(
        app,
        "/responsibility-assignments",
        ResponsibilityAssignment,
        s.ResponsibilityAssignmentOut,
        s.ResponsibilityAssignmentPatch,
        responsibility_assignment_stays_valid,
        project_id=Project,
        deliverable_id=Deliverable,
        task_id=Task,
        person_id=Person,
    )

    creates(
        app,
        "/acquisitions",
        Acquisition,
        s.AcquisitionIn,
        s.AcquisitionOut,
        project_id=Project,
        resource_type_id=ResourceType,
    )
    reads(app, "/acquisitions", Acquisition, s.AcquisitionOut)
    writes(
        app,
        "/acquisitions",
        Acquisition,
        s.AcquisitionOut,
        s.AcquisitionPatch,
        project_id=Project,
        resource_type_id=ResourceType,
    )

    creates(
        app,
        "/training-records",
        TrainingRecord,
        s.TrainingRecordIn,
        s.TrainingRecordOut,
        person_id=Person,
    )
    reads(app, "/training-records", TrainingRecord, s.TrainingRecordOut)
    writes(
        app,
        "/training-records",
        TrainingRecord,
        s.TrainingRecordOut,
        s.TrainingRecordPatch,
        person_id=Person,
    )

    # TeamAssessment: append-only, like AcceptanceRecord — create and read only, no
    # patch or delete: a later reading files a new row.
    creates(
        app,
        "/team-assessments",
        TeamAssessment,
        s.TeamAssessmentIn,
        s.TeamAssessmentOut,
        project_id=Project,
    )
    reads(app, "/team-assessments", TeamAssessment, s.TeamAssessmentOut)

    creates(
        app,
        "/conflict-records",
        ConflictRecord,
        s.ConflictRecordIn,
        s.ConflictRecordOut,
        project_id=Project,
    )
    reads(app, "/conflict-records", ConflictRecord, s.ConflictRecordOut)
    writes(
        app,
        "/conflict-records",
        ConflictRecord,
        s.ConflictRecordOut,
        s.ConflictRecordPatch,
        project_id=Project,
    )

    creates(
        app,
        "/conflict-actions",
        ConflictAction,
        s.ConflictActionIn,
        s.ConflictActionOut,
        conflict_id=ConflictRecord,
        owner_id=Person,
    )
    reads(app, "/conflict-actions", ConflictAction, s.ConflictActionOut)
    writes(
        app,
        "/conflict-actions",
        ConflictAction,
        s.ConflictActionOut,
        s.ConflictActionPatch,
        conflict_id=ConflictRecord,
        owner_id=Person,
    )


def register_resources(app: FastAPI) -> None:
    """Register every resource family this module owns onto ``app``."""
    _register_hierarchy(app)
    _register_org(app)
    _register_department_operations(app)
    _register_schedule(app)
    _register_scorecard(app)
    _register_delivery(app)
    _register_agile(app)
    _register_governance(app)
    _register_records(app)
    _register_scope(app)
    _register_resource(app)
