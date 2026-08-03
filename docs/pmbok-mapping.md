# PMBOK practices in driftless

For a PMP-trained reader arriving at this tool: which practices it implements, which it
deliberately does not, and what it calls each thing. Every **supported** row below names the
code that backs it as `path:line symbol`; `tests/test_docs_pmbok_mapping.py` fails if that
symbol moves, if a boundary below shifts, or if a practice listed as absent quietly appears.
So this file is checked, not asserted.

Practices are named, never numbered. The catalog does carry PMBOK-6 clause numbers as its
process ids (`driftless/pmbok/model.py:45 Process`, e.g. `11.2`), because it is a
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
| Framework | The 5 process groups x 10 knowledge areas | PMBOK reference page and `driftless pmbok processes` | `driftless/pmbok/catalog.py:41 PROCESSES` |
| Framework | Inputs / Tools & Techniques / Outputs per process | ITTO catalog, closed vocabularies both sides | `driftless/pmbok/artifacts.py:125 ARTIFACT_KINDS`, `driftless/pmbok/tt.py:142 TT_CATALOG` |
| Framework | Where a project stands on a process | Five computed states: not started, in progress, produced, signed off, waived | `driftless/pmbok/state.py:145 process_state` |
| Framework | Tailoring | A `waived` decision in the append-only ledger | `driftless/models/governance.py:38 SIGNOFF_DECISIONS` |
| Framework | Development approach (predictive / adaptive / hybrid) | `Project.delivery_mode`, a CHECK vocabulary | `driftless/models/hierarchy.py:46 DELIVERY_MODES` |
| Framework | Organisational project management (portfolio, program, project) | One rollup path for every level, so a drill-down cannot disagree with the level above | `driftless/calc/rollup.py:104 roll_up` |
| Integration | Develop Project Charter | Charter Report, generated from live rows | `driftless/report/documents/charter.py:18 render` |
| Integration | Perform Integrated Change Control | A change request whose approval causes a **new** baseline version; approved baselines are frozen | `driftless/models/records.py:100 ChangeRequest` |
| Integration | Monitor and Control Project Work | One ranked attention feed across the store | `driftless/assess/feed.py:94 attention_feed` |
| Integration | Overall project health as a roll-up of the others | Integration assessment = worst-of the nine areas | `driftless/assess/engine.py:125 assess_project` |
| Integration | Assumption log, lessons learned register, EEFs, OPAs | Narrative records — one body of prose per project per kind | `driftless/models/narrative.py:53 NarrativeArtifact` |
| Framework | The fifteen prose planning documents: the ten subsidiary management plans (scope, requirements, schedule, cost, quality, resource, communications, risk, procurement, stakeholder engagement), the scope statement, the requirements documentation, the team charter, the basis of estimates and the team performance assessments | Stored prose per project per kind, resolved for presence health — the wizard collects each body, and the processes that owe one are assessable | `driftless/models/narrative.py:30 NARRATIVE_KINDS` |
| Integration | Close Project (approval that a process is done) | `accepted` / `resolved` in the sign-off ledger; a signed threat re-surfaces if its score regresses | `driftless/models/governance.py:50 SignOff` |
| Scope | Scope baseline | Approved `Baseline` header plus one line per task; re-baselining inserts a version | `driftless/models/delivery.py:39 Baseline` |
| Scope | Control Scope | Approved-but-unbaselined change detection | `driftless/assess/evaluators/scope.py:28 evaluate` |
| Schedule | Schedule baseline, project schedule | Planned window and planned cost per task, per baseline version | `driftless/models/delivery.py:66 BaselineLine` |
| Schedule | Milestone list and slip | `Milestone` with target, baseline date and status | `driftless/models/delivery.py:87 Milestone` |
| Schedule | Agile release planning | Best / likely / worst completion band from the last three sprints' velocity | `driftless/calc/forecast.py:130 forecast_completion` |
| Schedule | Simulation | Seeded Monte Carlo over sprint velocities: p50 / p80 / p90 completion | `driftless/calc/forecast.py:224 monte_carlo_completion` |
| Schedule | Control Schedule | SPI and milestone-slip assessment | `driftless/assess/evaluators/schedule.py:48 evaluate` |
| Cost | Cost baseline | `BudgetLine` planned amounts over one category vocabulary | `driftless/models/records.py:127 BudgetLine` |
| Cost | Actual cost, time-phased | Dated `CostEntry` rows — AC(t) is recoverable, not a running total | `driftless/models/records.py:145 CostEntry` |
| Cost | Earned value analysis | One snapshot per as-of: BAC, PV, EV, AC, CPI, SPI, EAC, ETC, VAC — each ratio `None` rather than faked on a zero denominator | `driftless/calc/evm.py:160 earned_value_snapshot` |
| Cost | Reserve analysis | Contingency held as a rate of remaining budget, weighed against register exposure | `driftless/calc/forecast.py:170 assess_contingency` |
| Cost | Control Costs | CPI and VAC assessment | `driftless/assess/evaluators/cost.py:30 evaluate` |
| Quality | Quality metrics and control measurements | Dated target-versus-actual measurement per project | `driftless/models/quality.py:25 QualityMeasurement` |
| Quality | Control Quality | Out-of-tolerance and stale-evidence assessment | `driftless/assess/evaluators/quality.py:35 evaluate` |
| Resource | Resource capacity and cost rate | `Person.capacity_hours` and `cost_rate`, under a department | `driftless/models/people.py:57 Person` |
| Resource | Control Resources (over-allocation) | Allocation versus capacity, per person and per week on the capacity heatmap | `driftless/assess/evaluators/resource.py:189 person_task_loads` |
| Communications | Manage / Monitor Communications | Reporting cadence per stakeholder; staleness is a threat | `driftless/assess/evaluators/communications.py:26 evaluate` |
| Communications | Work performance reporting | Append-only `StatusSnapshot` series behind every trend line | `driftless/models/records.py:163 StatusSnapshot` |
| Risk | Risk register: probability, impact, response strategy | Per-project `Risk`; exposure derived, response one of avoid / mitigate / transfer / accept | `driftless/models/records.py:48 Risk` |
| Risk | Issue log | Per-project `Issue`, optionally naming the risk that became it | `driftless/models/records.py:79 Issue` |
| Risk | Monitor Risks | Exposure against contingency | `driftless/assess/evaluators/risk.py:47 evaluate` |
| Procurement | Agreements and claims administration | Signed agreement per vendor, with a `disputed` state | `driftless/models/procurement.py:27 ProcurementAgreement` |
| Procurement | Control Procurements | Dispute, lapse and over-budget assessment | `driftless/assess/evaluators/procurement.py:38 evaluate` |
| Stakeholder | Stakeholder register and engagement | Interest, influence and comms cadence per stakeholder | `driftless/models/records.py:195 Stakeholder` |
| Stakeholder | Monitor Stakeholder Engagement | Disengaged power-player assessment | `driftless/assess/evaluators/stakeholder.py:28 evaluate` |
| Cross-cutting | Recommending the right tool or technique | Each recommended action names a `TT_CATALOG` member, so advice stays inside real PMBOK technique | `driftless/assess/model.py:47 Action` |
| Cross-cutting | Process completeness / maturity | Share of applicable processes produced-or-better, per project and business-wide; waived and untrackable excluded | `driftless/pmbok/state.py:190 completeness`, `driftless/pmbok/rollup.py:45 business_completeness` |
| Cross-cutting | "What should I do next on this project?" | Wizard: the next incomplete process, its inputs, whether each exists, and the outputs it can produce | `driftless/wizard/engine.py:92 next_step` |
| Cross-cutting | Standard project documents | Generated reports, byte-identical on regeneration, never hand-edited | `driftless/report/engine.py:54 render_document` |

### How far the artifact vocabulary reaches

The catalog holds 49 processes naming 80 artifact kinds, of which 36 resolve against the store
(`driftless/pmbok/mapping.py:418 RESOLVERS`): `scope_baseline`, `schedule_baseline`,
`cost_baseline`, `project_schedule`, `activity_attributes`, `milestone_list`, `risk_register`,
`issue_log`, `change_log`, `stakeholder_register`, `project_team_assignments`,
`work_performance_reports`, `work_performance_information`, `project_communications`,
`project_management_plan`, `agreements`, `quality_report`,
`assumption_log`, `lessons_learned_register`, `enterprise_environmental_factors`,
`organizational_process_assets`, `scope_management_plan`, `requirements_management_plan`,
`schedule_management_plan`, `cost_management_plan`, `quality_management_plan`,
`resource_management_plan`, `communications_management_plan`, `risk_management_plan`,
`procurement_management_plan`, `stakeholder_engagement_plan`, `project_scope_statement`,
`requirements_documentation`, `team_charter`, `basis_of_estimates`,
`team_performance_assessments`. Anything else answers `not tracked` — the store says so
rather than guessing (`driftless/pmbok/mapping.py:459 resolve`).

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

Coverage is now total: 0 of the 49 processes have no tracked output, so nothing drops out of a
completeness figure for being invisible to the store — the only exclusion left is a waived
process, a decision somebody signed. It still is not a PMP audit score: it reads "of the
processes not tailored out, how many are done".

## Not implemented

These are boundaries, not backlog. Each names the artifact kinds it would have produced, all
of which the store reports as untracked.

| PMBOK practice | Artifact kinds | Why not |
| --- | --- | --- |
| Create WBS / decomposition | `work_breakdown_structure` | The hierarchy is business → portfolio → program → project → workstream → task. There is no WBS node type and no WBS dictionary; a workstream is a grouping, not a deliverable-oriented decomposition. The scope statement a WBS would decompose is stored prose (see Supported); nothing decomposes it |
| Requirements traceability | `requirements_traceability_matrix` | The requirements documentation is stored prose (see Supported), but no requirement *record* exists — there are no rows to trace from a requirement to a deliverable |
| Sequencing activities | `activity_list`, `project_schedule_network_diagram` | A task carries no predecessor, so there are no edges and no network to draw. The activities themselves are the tasks under a workstream, and their attributes resolve above — the list is that resolver's own count, not a second record |
| Critical path, float, leads and lags, schedule compression | `schedule_data`, `schedule_forecasts` | Follows from the row above. The Gantt **draws** baseline windows; it never computes them, and no path is marked critical |
| Resource levelling and smoothing | `resource_calendars`, `project_calendars`, `resource_requirements`, `resource_breakdown_structure` | The heatmap shows who is over capacity and in which week. It never moves work to fix it |
| Estimating techniques (analogous, parametric, three-point, bottom-up) | `duration_estimates`, `cost_estimates`, `independent_cost_estimates` | A task carries one estimate and a baseline line one planned cost — no range and no PERT. The written basis for those figures is stored prose (see Supported); nothing computes from it |
| To-complete performance index, earned schedule | `performance_measurement_baseline`, `cost_forecasts` | EVM stops at the snapshot above. TCPI is in the technique vocabulary because processes cite it; nothing computes it |
| The development approach as a document | `development_approach` | Carried as `Project.delivery_mode`, a field rather than a document. The plan-of-plans left this row when it became a roll-up over the ten stored subsidiary plans (see Supported) — derived on read, so it still stores nothing that would restate what it binds |
| Quality metrics and audits | `quality_metrics`, `quality_control_measurements`, `test_and_evaluation_documents` | Quality enters as a dated measurement against a target. No audit record, no cost of quality, no control charts |
| Solicitation and source selection | `bid_documents`, `seller_proposals`, `source_selection_criteria`, `selected_sellers`, `procurement_statement_of_work`, `procurement_strategy`, `procurement_documentation`, `closed_procurements` | Procurement enters the store at signature. Everything before it happens elsewhere |
| Assigning anything that is not a person | `physical_resource_assignments` | People are the only tracked resource; equipment, materials and facilities have no record. Who is doing the work resolves above off `Task.assignee_id` — one assignee per task, so there is still no RACI matrix behind it |
| Deliverable verification and acceptance | `deliverables`, `verified_deliverables`, `accepted_deliverables` | Done-ness is a task status and a percent complete, not an accepted artifact with a signature on it |
| Closing documents | `final_report`, `final_product_service_result`, `closed_procurements` | There is no closeout document. A finished project is one whose processes are signed off |
| Business case and benefits realisation | `business_case`, `benefits_management_plan`, `agreements_initial` | The store begins at the project. Pre-authorisation value analysis is somebody else's tool |
| Work performance data as a stored artifact | `work_performance_data` | The dated rows themselves are the data. The information, the reports and the communications derived from them are supported above — computed on read, never stored, which is the duplication the design forbids |
| The charter as a stored document | `project_charter` | Develop Project Charter is supported above — as the Charter Report, generated on read from live rows. Storing a copy of the output is the same duplication the design forbids |
| Funding requirements as a stored document | `project_funding_requirements` | Arithmetic over the cost baseline's budget lines, computed on read — the budget lines are the record |
| Risk report, RBS, decision trees, sensitivity analysis | `risk_report` | The register is per-risk and the only quantitative technique is the Monte Carlo above. No risk breakdown structure, no tornado diagram |
| Configuration and change management plans | `configuration_management_plan`, `change_management_plan`, `change_requests`, `approved_change_requests` | Change control is enforced structurally — an approved baseline is frozen, and a change request causes a new version — rather than described in a plan and hoped for |

Two more boundaries worth stating plainly: driftless is **not a scheduler** (it records an
approved plan and measures against it; it does not build one), and it is **not a document
editor** (every report is regenerated from the store, so an edit to the output is lost by
design — human narrative goes in a record field instead).

## Keeping this true

`tests/test_docs_pmbok_mapping.py` reads this file and checks four things: every `path:line
symbol` citation resolves to that symbol defined at that line; the counts above match the live
catalog; every artifact kind named in the supported half really does resolve against the store;
and every kind named under **Not implemented** really does not. Implementing one of the rows
above turns the test red until this document is updated with it.
