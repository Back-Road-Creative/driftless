# PMBOK practices in driftless

For a PMP-trained reader arriving at this tool: which practices it implements, which it
deliberately does not, and what it calls each thing. Every **supported** row below names the
code that backs it as `path:symbol`; `tests/test_docs_pmbok_mapping.py` fails if that symbol
is gone, if a boundary below shifts, or if a practice listed as absent quietly appears. So
this file is checked, not asserted.

Practices are named, never numbered. The catalog does carry PMBOK-6 clause numbers as its
process ids (`driftless/pmbok/model.py:Process`, e.g. `11.2`), because it is a
versioned-in-code copy of that edition's grid — nothing else in the tool depends on edition
numbering, and this document does not.

## The stance, in three sentences

- **One store; everything else is a query over it.** Dashboards, rollups and generated
  documents are computed on read, never stored copies, so no two of them can disagree.
- **Process state is derived, never recorded.** There is no ProcessInstance table: a project's
  standing on a process is computed from the artifacts it has produced plus the sign-off
  ledger, so it cannot drift from reality.
- **Every answer takes an explicit as-of date.** Nothing in the calculation core reads a wall
  clock, which is what makes "generate it twice, get identical output" a testable property.

## Vocabulary

| PMBOK says | driftless says | Note |
| --- | --- | --- |
| Project document | *record* | A row in the store, written through one validated API |
| Work performance report | *status snapshot* / Weekly Status Report | Append-only series, percent complete stamped from the engine, never typed |
| Tailoring a process out | *waived sign-off* | A decision in the ledger, not a missing row |
| Project management plan | *plan-of-plans* | The ten subsidiary plans are stored prose records; the composite is derived from them on read, never stored |
| Progressive elaboration | *re-baselining* | A new `Baseline` version; the old one is never edited |
| Process group x knowledge area grid | *process map* | `/process-map` per project and business-wide |
| Risk exposure | *exposure* | Derived from probability x impact, never stored |
| Overall project health | *RAG* | `green` / `amber` / `red`, plus `unknown` for nothing to assess — not a PMBOK term |
| Threat (in the risk sense) | *risk* | A driftless **threat** is a computed problem the assessment engine raised, not a register line |

## Supported

| Area | PMBOK practice | In driftless | Implemented by |
| --- | --- | --- | --- |
| Framework | The 5 process groups x 10 knowledge areas | PMBOK reference page and `driftless pmbok processes` | `driftless/pmbok/catalog.py:PROCESSES` |
| Framework | Inputs / Tools & Techniques / Outputs per process | ITTO catalog, closed vocabularies both sides | `driftless/pmbok/artifacts.py:ARTIFACT_KINDS`, `driftless/pmbok/tt.py:TT_CATALOG` |
| Framework | Where a project stands on a process | Five computed states: not started, in progress, produced, signed off, waived | `driftless/pmbok/state.py:process_state` |
| Framework | Tailoring | A `waived` decision in the append-only ledger | `driftless/models/governance.py:SIGNOFF_DECISIONS` |
| Framework | Development approach (predictive / adaptive / hybrid) | `Project.delivery_mode`, a CHECK vocabulary | `driftless/models/hierarchy.py:DELIVERY_MODES` |
| Framework | Tailoring | Per delivery mode, every Monitoring & Controlling process reads on a predictive baseline or an adaptive commitment, with a one-sentence plain reason; the plan itself still only changes through one approval chain (`ChangeRequest` → `Baseline`) whichever mode applies | `driftless/pmbok/tailoring.py:PROFILES` |
| Framework | Organisational project management (portfolio, program, project) | One rollup path for every level, so a drill-down cannot disagree with the level above | `driftless/calc/rollup.py:roll_up` |
| Integration | Develop Project Charter | Charter Report, generated from live rows | `driftless/report/documents/charter.py:render` |
| Integration | Perform Integrated Change Control | A change request whose approval causes a **new** baseline version; approved baselines are frozen | `driftless/models/records.py:ChangeRequest` |
| Integration | Monitor and Control Project Work | One ranked attention feed across the store | `driftless/assess/feed.py:attention_feed` |
| Integration | Overall project health as a roll-up of the others | Integration assessment = worst-of the nine areas | `driftless/assess/engine.py:assess_project` |
| Integration | Assumption log, EEFs, OPAs | Narrative records — one body of prose per project per kind | `driftless/models/narrative.py:NarrativeArtifact` |
| Integration | Lessons learned register | One dated, categorised row per lesson raised, not a single body of prose | `driftless/models/closeout.py:LessonLearned` |
| Framework | The fifteen prose planning documents: the ten subsidiary management plans (scope, requirements, schedule, cost, quality, resource, communications, risk, procurement, stakeholder engagement), the scope statement, the requirements documentation, the team charter, the basis of estimates and the team performance assessments | Stored prose per project per kind, resolved for presence health — the wizard collects each body, and the processes that owe one are assessable | `driftless/models/narrative.py:NARRATIVE_KINDS` |
| Integration | Close Project (approval that a process is done) | `accepted` / `resolved` in the sign-off ledger; a signed threat re-surfaces if its score regresses | `driftless/models/governance.py:SignOff` |
| Scope | Scope baseline | Approved `Baseline` header plus one line per task, AND a WBS — re-baselining inserts a version | `driftless/models/delivery.py:Baseline` |
| Scope | Control Scope | Approved-but-unbaselined change detection | `driftless/assess/evaluators/scope.py:evaluate` |
| Scope | Collect Requirements, requirements traceability matrix | Filed `Requirement` rows, each traced to exactly one deliverable, task or backlog item | `driftless/models/scope.py:RequirementTrace` |
| Scope | Create WBS, WBS dictionary | `Deliverable` IS the WBS node — `wbs_code` and a self-referential `parent_id`, one tree | `driftless/models/scope.py:Deliverable` |
| Scope | Validate Scope (deliverable verification and acceptance) | Append-only verify/accept ledger against a deliverable | `driftless/models/scope.py:AcceptanceRecord` |
| Scope | Product analysis, context diagram, prototypes, benchmarking, inspection | One worksheet page per project, each section reading the project's own narrative, stakeholder and milestone rows — nothing computed | `driftless/web/assist_scope.py:create_assist_scope_router` |
| Schedule | Schedule baseline, project schedule | Planned window and planned cost per task, per baseline version | `driftless/models/delivery.py:BaselineLine` |
| Schedule | Milestone list and slip | `Milestone` with target, baseline date and status | `driftless/models/delivery.py:Milestone` |
| Schedule | Sequencing activities (`project_schedule_network_diagram`) | Typed precedence edges (`TaskDependency`: FS/SS/FF/SF plus a signed lag/lead) between this project's own tasks — present once one links two of them | `driftless/pmbok/mapping.py:_project_schedule_network_diagram` |
| Schedule | Schedule data (`schedule_data`) | Present once BOTH halves exist: a dated `BaselineLine` window AND a `TaskDependency` edge between this project's own tasks — dates alone are a date list, edges alone a diagram nobody has timed | `driftless/pmbok/mapping.py:_schedule_data` |
| Schedule | Project calendars (`project_calendars`) | A `ProjectCalendar` row filed for the project — the row itself IS the calendar | `driftless/pmbok/mapping.py:_project_calendars` |
| Schedule | Critical path method, float, leads and lags, crashing and fast-tracking scenarios | Forward/backward pass over `Activity`/`Dependency` objects built from the project's own stored `TaskDependency` rows and its newest approved baseline (`schedule_facts`), wired live to the assistant page; every zero-float path, not just one; crash and fast-track candidates returned as scenarios, never applied | `driftless/calc/network.py:critical_path` |
| Schedule | Estimating techniques (analogous, parametric, three-point/PERT, bottom-up) | Frozen-dataclass calculators, each returning an `EstimateScenario` with a plain-words basis: analogous scales a reference by a size ratio, parametric multiplies rate x quantity (single or multi-driver), three-point supports both triangular and beta/PERT weighting with a confidence range at +/-sigma, and bottom-up sums typed components. Independent of the one-estimate-per-task/one-planned-cost-per-baseline-line model the store still keeps | `driftless/calc/estimating.py:analogous`, `driftless/calc/estimating.py:parametric`, `driftless/calc/estimating.py:parametric_multi`, `driftless/calc/estimating.py:three_point_triangular`, `driftless/calc/estimating.py:three_point_beta`, `driftless/calc/estimating.py:bottom_up` |
| Schedule | Agile release planning | Best / likely / worst completion band from the last three sprints' velocity, plus WIP, throughput, cycle/lead time and burndown/burnup/cumulative flow — the flow calculator, `/projects/{id}/flow`, the technique's routed assistant | `driftless/pmbok/flow_facts.py:flow_snapshot` |
| Schedule | Simulation | Seeded Monte Carlo over sprint velocities: p50 / p80 / p90 completion | `driftless/calc/forecast.py:monte_carlo_completion` |
| Schedule | Control Schedule | SPI and milestone-slip assessment | `driftless/assess/evaluators/schedule.py:evaluate` |
| Cost | Cost baseline | `BudgetLine` planned amounts over one category vocabulary | `driftless/models/records.py:BudgetLine` |
| Cost | Actual cost, time-phased | Dated `CostEntry` rows — AC(t) is recoverable, not a running total | `driftless/models/records.py:CostEntry` |
| Cost | Earned value analysis | One snapshot per as-of: BAC, PV, EV, AC, CPI, SPI, EAC, ETC, VAC, CV, SV and percent variances — each ratio `None` rather than faked on a zero denominator; EAC reads under any of four documented methods | `driftless/calc/evm.py:earned_value_snapshot` |
| Cost | To-complete performance index | Both forms — to the original budget and to the current forecast — computed from that same snapshot, with a no-write what-if on the remaining cost | `driftless/calc/evm.py:to_complete_performance_index` |
| Cost | Reserve analysis | Contingency held as a rate of remaining budget, weighed against register exposure | `driftless/calc/forecast.py:assess_contingency` |
| Cost | Determine Budget: aggregation, reserves, funding limits, financing | Planned amounts rolled up work package -> control account -> project total; cost baseline (work packages + contingency) versus the total project budget (baseline + management reserve), stated the way PMBOK states it; periods whose cumulative planned spend outruns a stated funding limit; simple/compound financing cost | `driftless/calc/cost.py:cost_aggregation`, `driftless/calc/cost.py:reserve_analysis`, `driftless/calc/cost.py:funding_limit_reconciliation`, `driftless/calc/cost.py:financing_cost` |
| Cost | The cost workbench page: aggregation, reserves, funding limits, financing, the cash-flow S-curve, run rate, cost of quality, historical spend as a reference figure and the four estimating techniques, each a no-write what-if over this project's own `BudgetLine`/`CostEntry` rows | One page per project routing ten `TT_CATALOG` techniques through `assess.model.ASSISTANT_ROUTES` | `driftless/web/assist_cost.py:create_assist_cost_router` |
| Cost | Cash-flow S-curve | Cumulative planned spend sampled off `calc.evm.planned_value` — one accrual rule, read here rather than re-derived | `driftless/calc/cost.py:cash_flow_s_curve` |
| Cost | Run rate | Trailing-window average actual spend, the steady-state figure a department or agile team's ongoing budget view reads | `driftless/calc/cost.py:run_rate` |
| Cost | Control Costs | CPI and VAC assessment | `driftless/assess/evaluators/cost.py:evaluate` |
| Quality | Quality metrics and control measurements | Direction-aware metric definitions with dated project measurements and as-of evaluation | `driftless/assess/scorecard.py:evaluate_metric` |
| Quality | Control Quality | Out-of-tolerance and stale-evidence assessment | `driftless/assess/evaluators/quality.py:evaluate` |
| Quality | Control charts, Pareto analysis, statistical sampling, cost of quality, root cause (fishbone/five-whys), checklists | Pure calculators over plain inputs — none of them store a result; a caller adapts stored rows into these functions' inputs | `driftless/calc/quality.py:control_chart`, `driftless/calc/quality.py:pareto`, `driftless/calc/quality.py:sampling_plan`, `driftless/calc/quality.py:cost_of_quality`, `driftless/calc/quality.py:root_cause`, `driftless/calc/quality.py:checklist_result` |
| Resource | Resource capacity and cost rate | `Person.capacity_hours` and `cost_rate`, under a department | `driftless/models/people.py:Person` |
| Resource | Control Resources (over-allocation) | Allocation versus capacity, per person and per week on the capacity heatmap | `driftless/assess/evaluators/resource.py:person_task_loads` |
| Resource | Resource breakdown structure | `ResourceBreakdown` — a self-referential tree over the `ResourceType` catalog, the same shape `Deliverable`'s WBS tree uses | `driftless/models/team.py:ResourceBreakdown` |
| Resource | RACI / responsibility assignment matrix | `ResponsibilityAssignment` — a person's role against exactly one of a deliverable or a task | `driftless/models/team.py:ResponsibilityAssignment` |
| Resource | Acquire Resources | `Acquisition` — one staffing/procurement event against a resource type, internal or external | `driftless/models/team.py:Acquisition` |
| Resource | Develop Team (training, assessment) | `TrainingRecord` per person; append-only `TeamAssessment` readings per project | `driftless/models/team.py:TeamAssessment` |
| Resource | Manage Team (conflict management) | `ConflictRecord` with its approach, and the `ConflictAction` follow-up ledger | `driftless/models/team.py:ConflictRecord` |
| Communications | Manage / Monitor Communications | Reporting cadence per stakeholder; staleness is a threat | `driftless/assess/evaluators/communications.py:evaluate` |
| Communications | Work performance reporting | Append-only `StatusSnapshot` series behind every trend line | `driftless/models/records.py:StatusSnapshot` |
| Risk | Risk register: probability, impact, response strategy | Per-project `Risk`; exposure derived, response one of avoid / mitigate / transfer / accept | `driftless/models/records.py:Risk` |
| Risk | Issue log | Per-project `Issue`, optionally naming the risk that became it | `driftless/models/records.py:Issue` |
| Risk | Monitor Risks | Exposure against contingency | `driftless/assess/evaluators/risk.py:evaluate` |
| Risk | Plan Risk Responses: owner, trigger, planned action, residual probability/impact, cost and schedule impact of the response — one strategy vocabulary per `Risk.kind` (threat or opportunity) | Per-response `RiskResponse`, the risk-response planner page, and residual exposure fed into the cost workbench's reserve line, the gantt page's schedule note and the threats board's "no response planned" tie-break | `driftless/models/risk.py:RiskResponse` |
| Risk | Perform Qualitative Risk Analysis: P x I matrix, risk breakdown structure | A configurable probability x impact matrix banded low/moderate/high, and the four standard RBS categories, each with a plain summary | `driftless/calc/risk.py:score`, `driftless/calc/risk.py:RiskBreakdownStructureCategory` |
| Risk | Perform Quantitative Risk Analysis: EMV, decision trees, sensitivity analysis, risk simulation | Textbook expected monetary value and decision-tree branch selection; a tornado ordering of sensitivity factors; a seeded Monte Carlo over a risk register's Bernoulli-trial exposure (p50/p80/p90) | `driftless/calc/risk.py:expected_monetary_value`, `driftless/calc/risk.py:decision_tree`, `driftless/calc/risk.py:sensitivity`, `driftless/calc/risk.py:simulate_exposure` |
| Procurement | Agreements and claims administration | Signed agreement per vendor, with a `disputed` state | `driftless/models/procurement.py:ProcurementAgreement` |
| Procurement | Make-or-buy analysis | Break-even volume and the make/buy call it implies | `driftless/calc/procurement.py:make_or_buy` |
| Procurement | Proposal evaluation | Weighted bid scoring and the ranking's sensitivity to each weight | `driftless/calc/procurement.py:bid_score` |
| Procurement | Source selection analysis | Fixed-price / cost-reimbursable / time-and-materials guidance from scope certainty and risk appetite | `driftless/calc/procurement.py:contract_type_guidance` |
| Procurement | Control Procurements | Dispute, lapse and over-budget assessment | `driftless/assess/evaluators/procurement.py:evaluate` |
| Stakeholder | Stakeholder register and engagement | Interest, influence and comms cadence per stakeholder | `driftless/models/records.py:Stakeholder` |
| Stakeholder | Voting, multicriteria decision analysis, autocratic decision making | A tally against unanimity/majority/plurality, or a weighted-criteria ranking naming which criterion decides it, or a decider-plus-rationale record — each computed, never stored | `driftless/calc/decisions.py:vote`, `driftless/calc/decisions.py:multicriteria_score`, `driftless/calc/decisions.py:autocratic_record` |
| Stakeholder | Focus groups, meetings, facilitation | A fixed plain-steps agenda per facilitation technique, plus a meeting's evidence — purpose, attendees, decisions and owned actions — recorded as a `TechniqueRun` | `driftless/calc/decisions.py:facilitation_plan`, `driftless/calc/decisions.py:meeting_record` |
| Stakeholder | Monitor Stakeholder Engagement | Disengaged power-player assessment | `driftless/assess/evaluators/stakeholder.py:evaluate` |
| Stakeholder | Stakeholder analysis, engagement assessment matrix, communication methods | Power/interest grid, current-versus-desired engagement gaps and a push/pull/interactive channel picker, all computed on read from the stored `Stakeholder` row | `driftless/calc/stakeholders.py:power_interest_grid` |
| Cross-cutting | Knowing what a tool or technique IS and how to run it | Every catalog technique explained in Driftless's own words — when to use it, when to avoid it, ordered steps, outputs, pitfalls, a worked example, and the clause it comes from where the edition defines one — read on `/techniques` and linked from every process's ITTO list | `driftless/pmbok/definitions.py:TECHNIQUES` |
| Cross-cutting | Recommending the right tool or technique | Each recommended action names a `TT_CATALOG` member, so advice stays inside real PMBOK technique | `driftless/assess/model.py:Action` |
| Cross-cutting | Running a technique, not just reading about it | The first CALCULATOR-mode assistant page: `/projects/{id}/assist/stakeholders` | `driftless/assess/model.py:ASSISTANT_ROUTES` |
| Cross-cutting | Process completeness / maturity | Share of applicable processes produced-or-better, per project and business-wide; waived and untrackable excluded | `driftless/pmbok/state.py:completeness`, `driftless/pmbok/rollup.py:business_completeness` |
| Cross-cutting | "What should I do next on this project?" | Wizard: the next incomplete process, its inputs, whether each exists, and the outputs it can produce | `driftless/wizard/engine.py:next_step` |
| Cross-cutting | Standard project documents | Generated reports, byte-identical on regeneration, never hand-edited | `driftless/report/engine.py:render_document` |

### How far the artifact vocabulary reaches

The catalog holds 49 processes naming 80 artifact kinds, of which 47 resolve against the store
(`driftless/pmbok/mapping.py:RESOLVERS`): `scope_baseline`, `schedule_baseline`,
`cost_baseline`, `project_schedule`, `activity_attributes`, `schedule_data`,
`project_calendars`, `milestone_list`, `risk_register`,
`risk_report`, `issue_log`, `change_log`, `change_requests`, `stakeholder_register`,
`project_team_assignments`,
`work_performance_reports`, `work_performance_information`, `project_communications`,
`project_management_plan`, `agreements`, `quality_report`,
`assumption_log`, `lessons_learned_register`, `enterprise_environmental_factors`,
`organizational_process_assets`, `scope_management_plan`, `requirements_management_plan`,
`schedule_management_plan`, `cost_management_plan`, `quality_management_plan`,
`resource_management_plan`, `communications_management_plan`, `risk_management_plan`,
`procurement_management_plan`, `stakeholder_engagement_plan`, `project_scope_statement`,
`requirements_documentation`, `team_charter`, `basis_of_estimates`,
`team_performance_assessments`, `requirements_traceability_matrix`,
`work_breakdown_structure`, `verified_deliverables`, `accepted_deliverables`,
`resource_breakdown_structure`, `physical_resource_assignments`. Anything else
answers `not tracked` — the store says so rather than guessing (`driftless/pmbok/mapping.py:resolve`).

Six of those are **derived**: nothing files them as artifacts of their own, so the wizard
offers no button for any of them. `work_performance_reports` is the status snapshot series
under the catalog's own name; `work_performance_information` is an approved plan plus dated
actuals, healthy while the newest actual is inside the reporting cadence. Two more read
the task register, which is why neither is a bare presence tick: `activity_attributes` is
healthy only when every task carries an estimate — an unsized activity cannot be sequenced or
weighed against capacity, so it is a name rather than an activity — and
`project_team_assignments` only when no task is unowned, because unassigned work is work
nobody has accepted. Neither table stores a date, so both count at every as-of. The last two
read no new rows: `project_communications` takes that same status series on the column the
others ignore — `StatusSnapshot.note` is nullable, so a snapshot without one is a number filed
and nobody was told anything — and `project_management_plan` rolls the ten subsidiary plans up
through their own resolvers, present only when all ten are. One resolver
still sits outside the vocabulary — `status_report`, that same series under the record name
the Communications evaluator and the wizard reach directly; no process names it, so it moves
no state itself.

Three more read native rows first and fall back to stored prose only when none exist, the same
order `requirements_documentation` already uses: `resource_management_plan` prefers a filed
`ResourceType` catalog, `team_charter` prefers filed `ResponsibilityAssignment` (RACI) rows
healthy once one names an accountable owner, and `team_performance_assessments` prefers the
latest dated `TeamAssessment` reading, healthy at or above a passing score. Two more are new
this round: `resource_breakdown_structure` reads the `ResourceBreakdown` tree, and
`physical_resource_assignments` reads `Acquisition` rows against a non-`people` resource type,
healthy once every one of them is fulfilled.

Two more are new this round, both re-readings of a table another resolver already owns:
`change_requests` (`driftless/pmbok/mapping.py:_change_requests`) reads the same dated
`ChangeRequest` rows `change_log` already surfaces, under the catalog's own name for the
raw list. `risk_report` (`driftless/pmbok/mapping.py:_risk_report`) reads the same `Risk`
rows `risk_register` already reads, plus a probability-weighted exposure total summed on
read — never stored, and not the Monte Carlo simulation in `driftless/calc/risk.py`, which
nothing in the risk area wires up. Neither is a resolver its area can make a process's
*required* output: every process that names `change_requests` (11.5-11.7) and every process
that names `risk_report` (11.2-11.7) lists it under `optional_outputs`, so a project with no
filed change, or no risk report of its own, is never held short for lacking one.

`schedule_data` (`driftless/pmbok/mapping.py:_schedule_data`) and `project_calendars`
(`driftless/pmbok/mapping.py:_project_calendars`) are new this round too: the first reads the
same dated `BaselineLine` rows `schedule_baseline` reads plus the same `TaskDependency` edges
`project_schedule_network_diagram` reads, present only once both exist; the second is present
once one `ProjectCalendar` row is filed for the project. PMBOK 6.5 Develop Schedule names both
as outputs beside `schedule_baseline` and `project_schedule`, and lists both under
`optional_outputs` for the same reason `risk_report` is optional above. Of the three,
`schedule_data` joins the six derived kinds above — it has no row of its own, only the two it
reads together. `project_calendars` and `project_schedule_network_diagram` are not: the wizard
can now produce both (a filed `ProjectCalendar`, and a predecessor/successor task pair joined
by a `TaskDependency`), which is what keeps PMBOK 6.3 Sequence Activities — the one process that
names `project_schedule_network_diagram` as a *required* output — from being a dead end.

Coverage is now total: 0 of the 49 processes have no tracked output, so nothing drops out of a
completeness figure for being invisible to the store — the only exclusion left is a waived
process, a decision somebody signed. It still is not a PMP audit score: it reads "of the
processes not tailored out, how many are done".

## Agile equivalences

Nine of the kinds above have a second reading. A Scrum or Kanban project's evidence for
the same control question often does not live in the predictive-shaped rows `mapping.py`
reads (a `Baseline`, a `Milestone`) — it lives in `driftless/models/agile.py`'s roles,
backlog items, releases, definition-of-done items and impediments, plus the
review/retrospective fields `Sprint` carries; an operations-cadence project's evidence for
two of those nine lives instead in `driftless/models/operations.py`'s service levels,
incidents and recurring work, read off `Project.responsible_department_id`.
`driftless/pmbok/crosswalk.py:EQUIVALENCES` names, for each kind, where that evidence lives
and the rule that reads it; `mapping.resolve` consults it only when its own resolver finds
nothing, so a native row always wins when one exists, and the crosswalk never writes a row
of its own. `driftless/pmbok/tailoring.py` decides, per Monitoring & Controlling process and
per project, whether that fallback is even reached — see that module's own docstring.

| Artifact kind | Counted from | Rule |
| --- | --- | --- |
| `requirements_documentation` | backlog items (driftless/models/agile.py:BacklogItem) | a backlog item's description IS its requirement statement; present once any item has one, healthy once every item does |
| `project_schedule` | releases (driftless/models/agile.py:Release) | a release with a target date is the agile reading of a project schedule when there is no sprint or milestone to read one from |
| `scope_baseline` | committed backlog items and definition-of-done items (models/agile.py) | a committed backlog (status ready/in_progress/done) plus a written definition of done is what an agile team baselines scope against |
| `issue_log` | impediments (driftless/models/agile.py:Impediment) | an impediment IS an issue raised against the team's progress; healthy once none are open or in progress |
| `lessons_learned_register` | sprint retrospective evidence (driftless/models/delivery.py:Sprint) | a sprint closed with retrospective notes is a lesson captured, the way a predictive project files one as prose |
| `resource_management_plan` | project roles (driftless/models/agile.py:ProjectRole) | naming who holds each agile role (product owner, Scrum Master, developer, stakeholder proxy) is how an agile team plans its resources, in place of the stored prose plan a predictive project writes |
| `work_performance_reports` | sprint review evidence (driftless/models/delivery.py:Sprint) | a sprint closed with review notes is the periodic report the sprint's own cadence produces, fresh while the latest is inside the reporting window |
| `work_performance_information` | sprints under way (driftless/models/delivery.py:Sprint) for an agile project, or service levels and incidents (driftless/models/operations.py) for an operations-cadence one | a sprint under way is the work performance data an agile team reads instead of a baseline-and-actuals pair; an operations-cadence project reads the same question off its service levels and the incidents raised against them |
| `schedule_baseline` | the current sprint's committed window (driftless/models/delivery.py:Sprint) for an agile project, or the department's own recurring work (driftless/models/operations.py:RecurringWork) for an operations-cadence one | an agile team's schedule is the sprint it has committed to, not a fixed baseline; an operations-cadence project's schedule is the cadence the department already runs |
| `accepted_deliverables` | reviewed sprints with completed points (driftless/models/delivery.py:Sprint) for an agile project, or the department's service levels (driftless/models/operations.py:ServiceLevel) for an operations-cadence one | an agile team accepts an increment at the sprint review, so a reviewed sprint that completed points is accepted work; an operations-cadence project accepts finished work against the department's own service levels |

Every `models/agile.py` model is read by at least one row above — `tests/test_pmbok_crosswalk.py`
pins that set-equality against the module's own mapped classes, the same way `NAMED_MODELS`
and `NO_EQUIVALENCE` partition it in code. `models/operations.py`'s models get the same
treatment against `OPERATIONS_NAMED_MODELS`/`OPERATIONS_NO_EQUIVALENCE`
(`tests/test_pmbok_mode_aware_state.py`).

## Not implemented

These are boundaries, not backlog. Each names the artifact kinds it would have produced, all
of which the store reports as untracked.

| PMBOK practice | Artifact kinds | Why not |
| --- | --- | --- |
| The bare activity enumeration as its own artifact | `activity_list` | The activities themselves are the tasks under a workstream, and their attributes resolve above — the list is that resolver's own count, not a second record |
| Schedule compression as a filed forecast | `schedule_forecasts` | The arithmetic — critical path, float, leads and lags — now reads real stored predecessor edges (see Supported) and is wired live to the assistant page, but nothing computes a compression forecast of its own |
| Resource levelling and smoothing | `resource_calendars`, `resource_requirements` | The heatmap shows who is over capacity and in which week. It never moves work to fix it; one project-wide calendar now resolves (see Supported), but no per-resource one exists |
| Estimating techniques (analogous, parametric, three-point, bottom-up) | `duration_estimates`, `cost_estimates`, `independent_cost_estimates` | A task carries one estimate and a baseline line one planned cost — no range and no PERT. The written basis for those figures is stored prose (see Supported); nothing computes from it |
| Estimate ranges as stored artifacts | `duration_estimates`, `cost_estimates`, `independent_cost_estimates` | The techniques themselves compute now (see Supported), but a task still carries one estimate and a baseline line one planned cost — the range and its basis are computed on demand, never filed as a row of their own |
| The development approach as a document | `development_approach` | Carried as `Project.delivery_mode`, a field rather than a document. The plan-of-plans left this row when it became a roll-up over the ten stored subsidiary plans (see Supported) — derived on read, so it still stores nothing that would restate what it binds |
| Quality metrics and audits | `quality_metrics`, `quality_control_measurements`, `test_and_evaluation_documents` | Quality enters as a dated measurement against a target. Control charts, Pareto, sampling, cost of quality and root-cause chains are now computed by `driftless/calc/quality.py` from plain inputs (see Supported), but nothing stores an audit finding, a checklist result, or a control-chart series — so these three artifact kinds still resolve as untracked |
| Solicitation and source selection | `bid_documents`, `seller_proposals`, `source_selection_criteria`, `selected_sellers`, `procurement_statement_of_work`, `procurement_strategy`, `procurement_documentation`, `closed_procurements` | Procurement enters the store at signature. Everything before it happens elsewhere |
| The bare deliverable list as its own artifact | `deliverables` | The `Deliverable` rows themselves are the list — see Create WBS above; there is no second, undecomposed listing artifact |
| Closing documents | `final_report`, `final_product_service_result`, `closed_procurements` | There is no closeout document. A finished project is one whose processes are signed off |
| Business case and benefits realisation | `business_case`, `benefits_management_plan`, `agreements_initial` | The store begins at the project. Pre-authorisation value analysis is somebody else's tool |
| Work performance data as a stored artifact | `work_performance_data` | The dated rows themselves are the data. The information, the reports and the communications derived from them are supported above — computed on read, never stored, which is the duplication the design forbids |
| The charter as a stored document | `project_charter` | Develop Project Charter is supported above — as the Charter Report, generated on read from live rows. Storing a copy of the output is the same duplication the design forbids |
| Funding requirements as a stored document | `project_funding_requirements` | Arithmetic over the cost baseline's budget lines, computed on read — the budget lines are the record |
| Configuration and change management plans | `configuration_management_plan`, `change_management_plan`, `approved_change_requests` | Change control is enforced structurally — an approved baseline is frozen, so approval reads through the baseline it produces rather than a filter of its own — described in a plan and hoped for is what these stay short of |

Two more boundaries worth stating plainly: driftless **does not level resources** (the
heatmap shows who is over capacity and in which week; it never moves work to fix it — it
computes a critical path over the stored plan and its dependency edges, but that is
measuring the plan, not building or rebalancing one), and it is **not a document
editor** (every report is regenerated from the store, so an edit to the output is lost by
design — human narrative goes in a record field instead).

## Keeping this true

`tests/test_docs_pmbok_mapping.py` reads this file and checks six things: every `path:symbol`
citation resolves to that symbol defined in that file; no citation addresses a line number; the
counts above match the live catalog; every artifact kind named in the supported half really
does resolve against the store; every kind named under **Not implemented** really does not; and
the **Agile equivalences** table names every `crosswalk.EQUIVALENCES` entry's own
`native_source` and `rule_in_plain_words`, verbatim, so it cannot drift from the code it walks.
Implementing one of the rows above turns the test red until this document is updated with it.
