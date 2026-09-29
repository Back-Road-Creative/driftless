# Architecture and invariants

What Driftless is built out of, and the properties each part guarantees. This
was the README's `## Status` section: a 270-line capability inventory sitting
between "who owns this" and "who uses it", which is the wrong place for it —
a reader arriving at the front door wants to know what the service is and how
to run it, not to read the whole model before reaching the quick start.

Nothing here is new. The wording is the README's, moved; `CHANGELOG.md` and the
fragments in `changelog.d/` remain the record of what actually shipped, and the
decision records in this directory (`temporal-model.md`,
`decisions-superseded.md`, `balanced-scorecard.md`) remain the record of what
was decided and why. Symbol citations below are checked by
`tests/test_docs_readme_citations.py`, which reads this file for the same
reason it reads the README: a citation nothing verifies is how a true claim
quietly becomes a false address.

## Pages

Every page this service serves, one per line, address first. The **Web surface**
bullet below explains what they do and how they hang together; this list exists so
that "every page" is a claim a machine can settle rather than a promise the prose
makes about itself. `tests/test_docs_numbers_are_measured.py` reads it both ways
against the live router: a page mounted with no line here fails, and a line here
naming an address nothing serves fails too — so the list can neither fall behind
the app nor invent a page that does not exist. Parameter names are the reader's
to pick (`{id}`, `{slug}`); only the shape is compared. Pages reachable from the
primary nav say so, checked against `web/templates/base.html`'s own `nav_link`
calls; everything else is reached from a link on another page.

- `GET /` — command center: the global KPI strip, the RAG heatmap, the cost
  S-curve and portfolio treemap, and the attention rail. **Primary nav.**
- `GET /login` — the sign-in form a signed-out browser asking for a page is sent to.
- `GET /scorecard` — the balanced scorecard, all four perspectives. **Primary nav.**
- `GET /threats` — the ranked threat board, grouped by project and paginated. **Primary nav.**
- `GET /search` — one term over the hierarchy, hits grouped by kind. **Primary nav.**
- `GET /process-map` — the business-wide process grid rolled up across every project. **Primary nav.**
- `GET /method` — the Method section's landing page: one card per surface, each saying
  what it is for and its own size, measured off the registry. **Primary nav.**
- `GET /pmbok` — the 49 processes as a stateless knowledge-area × process-group grid. **Primary nav.**
- `GET /pmbok/{id}` — one process's ITTO detail.
- `GET /pmbok/proof` — the totality proof: every count `pmbok.proof.build_proof()`
  reports over the whole catalog — orphan, unexplained, unlaunchable, uncrosswalked,
  wizard-skipped-for-no-documented-reason — plain-worded, with the offending members
  named for any that is not zero. Every row also says what it checked and what a
  count above zero would mean, from `pmbok.proof.GAP_SHAPES` — one entry per `Proof`
  member, so a count added to the dataclass cannot render as a bare label.
- `GET /map` — the method map: every process, technique and artifact drawn from
  `pmbok.graph_layout.LAYOUT`; `?project=&as_of=` washes process nodes with that
  project's own reading, `?focus=` highlights one node and its neighbours,
  `?from=&to=` draws the shortest `feeds` path between two processes, and
  `?group=`/`?area=` draws one process group or knowledge area on its own.
  **Primary nav.**
- `GET /techniques` — the technique library, grouped by family. **Primary nav.**
- `GET /techniques/{slug}` — one technique in full, addressed by its readable slug.
- `GET /methods` — the Scrum and Kanban method profiles. **Primary nav.**
- `GET /methods/{key}` — one method's practices in full, each crosswalked to PMBOK-6.
- `GET /artifacts` — the artifact-kind catalog, grouped by family. **Primary nav.**
- `GET /artifacts/{slug}` — one artifact kind in full, addressed by its readable slug: what
  it is, why it matters, what it looks like here, which processes make and read it, and
  whether this product's store tracks it.
- `GET /glossary` — the terms of art every page links to, each defined in plain words first. **Primary nav.**
- `GET /org/configuration` — live counts per hierarchy layer and the API path that creates each. **Primary nav.**
- `GET /org/departments` — the department list, ending in a totals row (departments, headcount, weekly capacity) summed from the same rows. **Primary nav.**
- `GET /org/departments/{id}` — one department's accountable projects, its people's capacity, and the operating records it keeps (services, work queue, recurring work, service levels, controls, incidents, improvements).
- `GET /org/departments/{id}/assist` — the department workspace: objectives its accountable
  projects contribute to, an operating plan (services, recurring work), a RACI matrix
  assembled from a service's owner, the department itself, stakeholder-proxy project roles
  and work-request requesters, demand versus capacity (reusing the capacity heatmap's own
  leveling rule), service levels measured by a plain average cycle time over done work
  requests, controls and incidents, improvements, the department's own budget lines rolled
  up beside the run rate of spend on its accountable projects, vendor agreements and project
  stakeholders — every section links its closest technique for reading only, since the
  techniques that would fit best (`resource_optimization`, `stakeholder_analysis`) are
  already claimed by a project-scoped action elsewhere.
- `GET /org/heatmap` — the capacity heatmap, person × week. **Primary nav.**
- `GET /business/{id}` — one business's portfolio → program → project hierarchy.
- `GET /portfolios/{id}/rollup` — that portfolio's rollup KPIs and its children's rows.
- `GET /programs/{id}/rollup` — the same drill for one program.
- `GET /projects/{id}/hub` — one project's EVM figures, live threats, RAID counts and milestones.
- `GET /projects/{id}/hub/costs` — the read-only provenance page behind the hub and
  weekly-status EVM figures: every `CostEntry` the actual cost is swept from, filtered
  to the same `incurred_on <= as-of` bound the EVM calculation itself applies.
- `GET /projects/{id}/assist/earned-value` — the earned-value calculator: BAC, PV, EV, AC,
  CPI, SPI, EAC, ETC, VAC and TCPI (both forms), each with its formula in plain words, plus
  a no-write what-if on the remaining cost. The first two techniques `assess.model.ASSISTANT_ROUTES`
  actually launches, `earned_value_analysis` and `to_complete_performance_index`.
- `GET /projects/{id}/assist/risk-responses` — the risk-response planner: the open register
  with strategy, owner, trigger and residual read against each risk, a no-write what-if on the
  residual exposure, and the one POST this page allows — filing a response. Routes the four
  response-strategy techniques: `strategies_for_threats`, `strategies_for_opportunities`,
  `contingent_response_strategies` and `strategies_for_overall_project_risk`.
- `GET /projects/{id}/assist/decision-tree` — the decision-tree/EMV calculator: a no-write
  what-if computing expected monetary value per option. Routes `decision_tree_analysis`.
- `GET /projects/{id}/assist/risk-pi` — read-only: every open risk placed on the standard
  5×5 P×I matrix, ranked by score and band. Routes `risk_probability_and_impact_assessment`.
- `GET /projects/{id}/assist/requirements` — the requirements/WBS worksheet: the
  traceability matrix, untraced requirements and orphan deliverables named in words, the
  WBS as an indented list plus a plain-text twin, the acceptance ledger, and the three
  writes this page allows — file a requirement, file a trace, record acceptance. Routes
  `decomposition`, 5.4 Create WBS's own technique.
- `GET /projects/{id}/assist/team` — the team assist page: the RBS as an indented list
  plus a plain-text twin, the stored RACI matrix, who lacks what (open acquisitions and
  untrained people), the team-assessment trend, open conflicts with their actions, and
  the three writes this page allows — file an assignment, record an assessment, log a
  conflict/action. `?preview_person_id=&preview_task_id=` previews the resource-clash
  the proposed assignment would cause on the org heatmap before it is filed — never a
  write, no auto-levelling. Routes nine Resource Management techniques: `organizational_theory`,
  `pre_assignment`, `virtual_teams`, `colocation`, `training`, `team_building`,
  `recognition_and_rewards`, `individual_and_team_assessments` and `conflict_management`.
- `GET /projects/{id}/assist/scope` — the scope worksheet: product analysis, context diagram,
  prototypes, benchmarking and inspection, each reading straight off the project's narrative
  prose, stakeholders and milestones. The five WORKSHEET-mode techniques
  `assess.model.ASSISTANT_ROUTES` launches here rather than only explaining.
- `GET /projects/{id}/assist/procurement` — the procurement calculators: make-or-buy break-even,
  weighted bid scoring with its ranking's sensitivity to each weight, and contract-type guidance,
  beside the project's signed agreements and a closure checklist derived from their status. Routes
  `make_or_buy_analysis`, `proposal_evaluation` and `source_selection_analysis`.
- `GET /projects/{id}/assist/closeout` — deliverable acceptance (milestone status), the lessons
  learned register (`LessonLearned` rows) and a final-report summary drawn from the same figures
  the hub already computes.
- `GET /projects/{id}/assist/decisions` — decisions and meetings: a vote tally, weighted-criteria
  scoring, an autocratic-decision preview and a fixed facilitation agenda, all no-write what-ifs
  off GET params, plus the project's meeting evidence log with the one write the page allows —
  filing a meeting as a `TechniqueRun`. Routes `voting`, `multicriteria_decision_analysis`,
  `autocratic_decision_making`, `focus_groups` and `meetings`.
- `GET /projects/{id}/assist/cost` — the cost workbench: `BudgetLine` rolled up by category
  and cost baseline/management reserves, the cash-flow S-curve sampled off the same accrual
  `assist/earned-value` reads, funding-limit reconciliation against it, financing cost, run
  rate off `CostEntry`, other projects' actual spend as a historical reference figure, and
  the four estimating techniques, plus the stored `EstimateScenario` rows (target `cost`)
  filed for the project as of the date and the one POST this page allows — filing the last
  what-if computed as one of those rows (`/assist/cost/estimate`). The budget itself still
  only changes through the change boundary the page links (a change request against 7.3).
  Routes `cost_aggregation`, `reserve_analysis`, `funding_limit_reconciliation`, `financing`,
  `historical_information_review`, `analogous_estimating`, `parametric_estimating`,
  `three_point_estimating` and `bottom_up_estimating`.
- `GET /projects/{id}/assist/quality` — the quality workbench: a control chart per metric with
  two or more dated readings, a Pareto of out-of-tolerance readings by metric, a no-write
  statistical-sampling what-if, a fishbone/five-whys root-cause worksheet over one issue, a
  no-write cost-of-quality what-if and an audit checklist read off the quality management plan
  narrative. Routes `root_cause_analysis`, `cost_of_quality` and `audits`; control charts, the
  Pareto split and statistical sampling name no `TT_CATALOG` member of their own.
- `GET /projects/{id}/assist/schedule` — the schedule-network calculator: the critical
  path(s) and float per task, drawn as an inline network diagram plus its text twin;
  `?crash=<task_id>:<days>`/`?fast_track=<predecessor_id>:<successor_id>` each preview one
  scenario (never a write), shown beside the current plan's own finish, critical path, total
  cost and EAC (at today's cost-performance index) for a side-by-side what-if comparison;
  a critical-chain buffer view labelled as the Driftless
  extension it is; and `POST /projects/{id}/assist/schedule/propose`, the one write, which
  files the active preview as a draft `Baseline` plus a `ChangeRequest` describing it —
  approving the change and promoting the draft is the existing generic
  `PATCH /baselines/{id}` / `PATCH /change-requests/{id}` step, never done here. Routes six
  more of `assess.model.ASSISTANT_ROUTES`: `critical_path_method`,
  `precedence_diagramming_method`, `leads_and_lags`, `schedule_network_analysis`,
  `resource_optimization`, `schedule_compression`, plus the extension `critical_chain_method`.
- `GET /projects/{id}/gantt` — the newest approved baseline drawn as a schedule.
- `GET /projects/{id}/schedule-health` (`?format=csv` for the same rows as a download) — the newest approved baseline's network
  run through `calc.dcma.assess_full`: one row per check, thresholds following the commonly
  used DCMA 14-point assessment (never reported as "compliant"/"certified"), with the
  offending tasks named. This schema tracks no actual/forecast/baseline-finish date distinct
  from the plan's own windows, so checks 9, 11 and 14 always render "not assessable" rather
  than inventing an offender. Linked from the project hub.
- `GET /projects/{id}/gates` — the project's stage gates in order, each with its readiness
  (which required controls and sign-offs are still missing as of the requested date) and
  whether it has passed. Read-only and computed; linked from the project hub.
- `GET /projects/{id}/baselines/diff` (optionally `?versions={v1}...{v2}`, else the two
  most recent approved baselines) — the per-line delta in dates, cost and
  scope between two approved baseline versions, each baseline's own approval record,
  and the change request that produced the later version, when one exists. Read-only
  and computed; on the hub strip, and linked from the schedule-network page once a
  project has more than one baseline version. Fewer than two approved baselines on
  the project renders its own empty state (200), never a 404.
- `GET /projects/{id}/flow` — WIP, throughput, cycle/lead time, the release forecast band,
  and (for a sprint whose window contains the as-of) burndown, burnup and cumulative flow.
  The `agile_release_planning` technique's routed assistant.
- `GET /projects/{id}/board` — every task in the column its status names.
- `GET /projects/{id}/process-map` — that project's process grid with a completion ring per area.
- `GET /projects/{id}/raid` — that project's risks, issues and change requests.
- `GET /projects/{id}/status` — the weekly-status edit form, with its trend line and S-curve.
- `GET /projects/{id}/status/inputs` — the read-only provenance page behind the status
  trend: every `StatusSnapshot` row for this project, in the same recording order the
  trend consumes them in.
- `GET /projects/{id}/wizard` — the agent-and-human onboarding wizard.
- `GET /projects/{id}/assist/stakeholders` — the power/interest grid, engagement matrix and communications matrix.

## What is in place

In place:

- **Hierarchy models** — business → portfolio → program → project →
  workstream → task, with the vocabularies as CHECK constraints. A project
  also navigates down to its own delivery records (`baselines`, `milestones`,
  `sprints`), read-only: records are attached by setting the record's
  `project`, never through those collections.
- **Delivery records** — per-project baselines, milestones and sprints. A
  baseline is a versioned header plus one line per task carrying that task's
  planned window and planned cost, because earned value needs the curve and
  not a total. Re-baselining inserts a new version rather than editing the
  old one, so plan history is additive by construction. A `Sprint` **is** an
  agile iteration — it also carries a `goal`, an optional `release` it
  belongs to, and the review/retrospective evidence (`review_held_on`/
  `review_notes`, `retrospective_held_on`/`retrospective_notes`) that closes
  it out, rather than a parallel iteration table.
- **Agile records** (`driftless.models.agile`) — `ProjectRole` (who holds
  product owner / Scrum master / developer / stakeholder-proxy, by name, not
  a `Person` foreign key — the same "who, in words" choice `Risk.owner`
  already makes), `BacklogItem` (agile demand ordered and estimated in
  `story_points`, carrying the `created_on`/`started_on`/`done_on` flow reads), `Release` (a named
  grouping of sprints), `DefinitionOfDoneItem` (a project-wide "done means"
  checklist) and `Impediment` (a blocker, dated like `Issue`). Current state
  like `Risk`/`Issue`, not as-of tracked (`docs/temporal-model.md`).
- **Department operations records** (`driftless.models.operations`) — what a
  department runs day to day, distinct from the projects it is merely
  accountable for: `DepartmentService` (its service catalog), `WorkRequest`
  (the demand queue against that catalog, carrying the same three-date shape
  `driftless.calc.flow.WorkItem` reads — `raised_on`/`started_on`/`done_on`
  — so flow metrics apply to a department's queue with no second
  definition), `RecurringWork` and `ServiceLevel` (sharing one cadence
  vocabulary — a recurring task's cadence and an SLA's measurement window are
  the same kind of fact), `OperatingControl` plus `Incident` (a dated
  operating-risk event, its `control_id` a nullable link like `Issue.risk_id`,
  not a parent), and `Improvement` (a proposed operating change: what, why,
  owner, status). Current state like `Risk`/`Issue`, not as-of tracked.
  `OperatingControl` carries no status column of its own: its RAG state is
  computed, never stored, by `driftless.calc.control_state.control_state` from
  its linked incidents and their evidence age — red for an open high/critical
  incident, amber for a lower-severity open incident or evidence older than
  `STALE_AFTER_DAYS`, green otherwise — the same computed-RAG philosophy
  `assess.scorecard.evaluate_metric` applies to a scorecard metric. Shown on
  the department workspace page's controls table
  (`driftless.web.assist_department`).
  `BudgetLine` (below) scopes to a department the same way it scopes to a
  project, rather than a twin table.
- **Schedule records** (`driftless.models.schedule`) — the network and
  duration-estimation layer: `TaskDependency` (a typed precedence edge
  between two of a project's own tasks — `kind` one of the four PMBOK
  relationship types FS/SS/FF/SF, `lag_days` signed, a negative value a
  lead; project scoping and cycle refusal are cross-row rules enforced at
  the API boundary and `driftless.services.schedule_writes`, since neither
  fits a CHECK), `ProjectCalendar` plus `CalendarException` (a project's
  default working-day pattern and its dated exceptions), and
  `EstimateScenario` (one estimate a PM ran — method, value/low/high,
  actor/as-of provenance — the stored form of a sibling PR's
  `calc.estimating.EstimateScenario`, field names mirrored rather than
  imported). The gantt page draws every dependency as a table beside the
  bars and a calendar note; the task board names how many tasks a card
  waits for.
- **ChangeLog** — an append-only audit trail written by a SQLAlchemy flush
  listener rather than by calls at each write site, so no path that writes
  through a session can skip it. It records table, row id, operation, actor
  and the old/new values that actually moved; `actor` names the signed-in user,
  so a write authorised by the shared `DRIFTLESS_API_TOKEN` stays unattributed.
  Activation is explicit (`register_changelog`); importing the module
  instruments nothing.
- **RAID and money records** — per-project risks, issues, change requests,
  budget lines and dated cost entries; risk exposure is derived, never
  stored. A `BudgetLine` scopes to EITHER a project or a department, never
  both and never neither (`ck_budget_line_one_scope`) — a department runs its
  own operating budget through the same table. `Risk.kind` (`threat` or
  `opportunity`, default `threat`) decides which half of `RiskResponse`'s
  strategy vocabulary a response filed against it may draw from (avoid,
  mitigate, transfer, accept, escalate for a threat; exploit, enhance,
  share, accept, escalate for an opportunity) — a cross-row rule, since a
  CHECK on `risk_response` alone cannot see the risk it belongs to.
  `driftless.pmbok.risk_facts.gather` is the one adapter that turns a
  project's filed responses into residual exposure, response schedule days
  and response cost — read by the risk-response planner page, the project
  hub's reserve line, the gantt page's schedule note and an "open risk with
  no response" tie-break in the risk evaluator's ranking, so none of them
  can disagree.
- **Org, sign-off and the last knowledge-area records** — departments and
  people (with a `capacity_hours` the Resource maths measures allocation
  against and a `cost_rate` labour cost multiplies by); an append-only
  `sign_off` ledger the threat feed suppresses against (severity-independent
  `subject_ref` plus the `signal` at sign-off, so a regression cannot be
  buried); and `narrative_artifact`, direction-aware `quality_metric` plus
  `quality_measurement`, and
  `procurement_agreement` records that make the Quality, Procurement and the
  narrative PMBOK inputs first-class. A task names its `assignee` and a project
  its `responsible_department`.
- **TechniqueRun** — an append-only provenance row for every technique a
  project runs: technique key and process id (both checked against the closed
  catalogs), the actor who ran it (required), the as-of date, a `method`
  context (predictive/scrum/kanban/department), the technique definition's
  `source_version`, and JSON snapshots of what it read and produced.
  `driftless.services.technique_runs.record_run` is the only writer — the
  decisions page's meeting form and `POST /technique-runs` (append-only like
  `/sign-offs`: create, read and list, never PATCH or DELETE; a JSON body
  naming an unknown technique or process is a 422) both go through it; a
  frozen `Provenance` dataclass (`driftless.pmbok.provenance`) is the shape
  any calculator returns before a run is recorded. The technique library and
  the PMBOK reference pages list a project's runs when read with `?project=`.
- **API** — one validated write path over the whole store: create, read, list,
  update and delete for the hierarchy **and** every per-project record (delivery,
  RAID, cost, stakeholders), the org tables, and the narrative / quality /
  procurement records. A partial update touches only the fields sent and can
  never re-parent a row across projects — the parent-scoping foreign keys
  (`project_id`, a line's `baseline_id`/`task_id`) are absent from every
  generated patch twin by construction, so a misfiled record is corrected by
  delete+recreate, not silently relocated. Two parents genuinely move and keep
  their field, each behind a boundary check that answers rather than ignores: a
  task is refiled between its **own project's** workstreams — a target workstream
  owned by another project is refused (409), never dropped from the patch, so a
  client can tell a refusal from a move that landed — and a workstream changes
  project only while it carries no tasks, since moving it is a batched task move
  (409, naming the tasks that hold it; empty it and the move goes through, still
  unit-checked). The two secondary links a patch twin keeps are scoped the same
  way on create *and* update: an issue's `risk_id` and a change request's
  `resulting_baseline_id` must name a row in the record's own project (409), the
  same-project link every reader assumes. A meta-test drives a real cross-scope
  write for each movable foreign key, so an allowlist entry proves its guard runs
  rather than claiming one. A delete refuses to
  orphan and names the child that blocks it (**every** foreign key in the schema
  has a parent-side relationship the guard reads off the mapper, so the refusal
  reads "still has risks" or "still has departments" rather than an opaque
  constraint 409 — a test enumerates the FK edges and fails on the first one a
  new model leaves uncovered); a constraint violation answers 409, never a 500. The
  hierarchy backbone stays inside its business: a portfolio with programs or
  projects, and a department with people or responsible projects, cannot change
  `business_id` (409, naming what holds it — empty either one and the move goes
  through); a project may be re-filed between portfolios of its own business but
  never across businesses, program or no program; and its
  `responsible_department` must belong to that same business, on create and on
  update (409). A
  project's program must live in the project's own portfolio — create and
  update both refuse a cross-portfolio pairing (422); a program with projects
  cannot change portfolio (409); a sprint must end strictly after it starts
  (422); a mode flip or workstream move that would strand a task's units is
  refused (409). A baseline's `status == "approved"` and `approved_at` can only
  move together (approval is one atomic transition) — on create the request type
  itself refuses the half-approved body (422), so no route can be registered
  without the rule, and on update the row is checked as the patch will leave it.
  Any write to an approved baseline or its lines is refused, and an approved
  baseline cannot be deleted — it is the plan of record (409/422); the freeze
  reads *either* approval signal, so a row carrying only one is still frozen.
  Two
  records carry their own rule: a **StatusSnapshot** stamps its percent complete
  from calc and never accepts it from the request, and a **SignOff** is
  append-only (create and read only — a reversal is a new row). Every write is
  audited on the ChangeLog. Every table but the ones named below also carries
  `row_revision` (int, from 1, bumped on every successful write — not
  CostEntry, ScorecardMetricObservation, QualityMeasurement, StatusSnapshot,
  SignOff or auth's User/ApiToken, since nothing ever PATCHes or DELETEs
  them), and every response for one of them returns it too — create, read,
  list and patch alike — so a client never has to lose a race just to learn
  the number to send back. A PATCH or DELETE stating `If-Match: <row_revision>`
  is refused with 409 the instant it disagrees with the row's current value
  (`{"detail": "<Model> <id> is at revision <n>, not <stated> -- re-read and
  retry"}`, the current revision named right there so a client can retry with
  it); a non-integer header is a 400, not a 409, since it never reaches the
  comparison. The header stays optional — a write that omits it lands
  unconditionally, exactly as it did before the check existed, so nothing
  that has not adopted the precondition breaks. The check itself
  (`driftless.services.concurrency.check_revision`) lives in `driftless.services`
  rather than in `driftless.api.crud`, which imports it — one rule, reusable by
  anything the store grows that patches an existing row.
- **One write boundary for the wizard, the status page and sign-off**
  (`driftless.services.wizard_writes`, `.status_snapshots`, `.sign_offs`) — CLI,
  browser form and JSON route all go through the same `driftless.services`
  function, and every one requires a named actor rather than an optional one
  (`create_status_snapshot`/`wizard_writes.produce`'s `actor`, `create_sign_off`'s
  `signed_by`). `driftless.api.deps.resolved_actor` hands the JSON route and the
  status page the same identity `get_session` already resolved, falling back to
  `"system"` for no principal; `wizard apply` takes `--actor` (default `cli`) since
  the CLI never sat behind that dependency. Nothing here writes to an existing
  row, so `check_revision` has no stale-write race to guard.
- **Calculation core** — earned value, forecasting, rollups and the cost
  workbench (`driftless/calc/cost.py:cost_aggregation`, `reserve_analysis`,
  `funding_limit_reconciliation`, `financing_cost`, `cash_flow_s_curve`) as
  pure functions over plain value objects, wired to stored rows by the
  dashboard. The S-curve reads `calc.evm.planned_value` — one accrual rule.
  Estimating (`driftless/calc/estimating.py`) joins them: analogous, parametric
  (single- and multi-driver), three-point (triangular and beta/PERT, with a
  confidence range at +/-sigma) and bottom-up, each returning a frozen
  `EstimateScenario` — value, low/high range and a plain-words basis — so a
  later page or the basis-of-estimates artifact can show the derivation
  without re-deriving it. Not wired to a task or baseline line yet; a task
  still carries one estimate and a baseline line one planned cost.
  `driftless/calc/flow.py` adds the kanban/flow side over a plain `WorkItem`
  (created/started/done dates plus points): `wip`, `throughput`, `cycle_time`
  and `lead_time` (both `DurationStats` — count, median, p85, over one shared
  percentile helper), `burndown` (fixed scope to zero) and `burnup` (scope
  line allowed to grow) and `cumulative_flow` (per-day state counts), plus
  `release_forecast` — a pass-through to `calc.forecast.forecast_completion`
  rather than a second velocity rule. `pmbok/flow_facts.py` wires it to stored
  rows for the flow page, the hub's Flow tile and the forecast report.
- **Web surface** (`driftless/web/`, mounted on the API app; every address it serves is
  listed under **Pages** above, which is the machine-checked inventory — this bullet is
  the explanation, not the list). Every page shares one shell (`web/templates/base.html`):
  a masthead — a full-width bar with a bottom rule — naming the product (the wordmark,
  never underlined) and the currently open project on the left, with Search, Sign in/out
  and the as-of chip (where a page carries one) right-aligned on the same row; a primary
  nav grouped into three screen-reader-named clusters — Work, Method, Organization —
  each a caption above its own links, one row on a desktop-width viewport; below the
  60rem breakpoint the clusters sit behind a checkbox-driven "Menu" toggle rather than
  rendering stacked and open, so a narrow viewport is not forced to draw all 13 links
  before a reader picks one — every route stays a real link in the markup either way,
  and every destination marks `aria-current="page"` when it or a page nested under it
  is open; and a small token set in `static/driftless.css` (a four-step type
  scale, an 8-pt spacing scale, `.card`/`.tile`/table primitives, a 72ch cap on prose, one
  accent reserved for the focus ring) that every page inherits rather than restating. Every
  `assist_*.html` (and `assist_department.html`)
  shares a second, narrower shell of its own, `web/templates/_assist.html`: a `.tiles`
  summary strip of the 3-5 headline figures a reader would otherwise hunt for further down
  the page, and every PMBOK technique rendered as its own `.card`, titled, with a small
  `.tech-chip` linking the technique library where the page already computed that link —
  never a bare `<h2>` sitting over prose with nothing under it. A server-rendered
  `GET /` **command center**: a global KPI strip (budget, actual, complete, on-track
  share, open high risks, open threats, process completeness — every figure from the
  engines, as-of resolved per request, each tile's value complete and final with
  JavaScript off and only count-up-animated to that same figure with it on), the RAG heatmap over each real business →
  portfolio → program → project tree, two inline-SVG charts computed from the same
  engine functions with nothing stored — a business-wide cost S-curve (planned vs
  actual) and a portfolio treemap (area by BAC, coloured by RAG, linking each real
  portfolio id) — and an **attention rail** rendering
  `attention_feed`'s order verbatim, each item also marked with its own
  week-over-week trend (the same ▲/▼/–/`new` idiom the threat board uses,
  annotation only, never a re-rank) — threats carry the inline `/sign-off` form, data
  signals link their fix surface, one line links the process map, a per-project
  **hub** (`/projects/{id}/hub`, linked from every dashboard project row — EVM figures,
  the project's own live threats, open RAID counts, milestones with slips marked, and
  links to that project's process map, wizard and weekly status), a per-project
  **schedule** (`/projects/{id}/gantt` — the newest APPROVED baseline as bars on a timeline, server-rendered inline SVG like the status charts so it draws with JavaScript off: each bar positioned and sized from its line's planned window, progress as the filled LENGTH plus a printed percentage (greyscale-legible — hue is never the only carrier), each milestone a mark at its `target_date` on the same scale, and a dashed rule at the as-of, which is where "today" comes from — never a wall clock, so a pinned as-of regenerates byte-identically. Every bar and mark repeats as a row of the table beneath, the chart's text alternative for a screen reader; a project with no approved baseline renders the shared empty state, never an empty grid. Linked from the project hub), a per-project
  **flow calculator** (`/projects/{id}/flow` — WIP, throughput, cycle/lead time and the
  velocity release-forecast band, plus burndown/burnup as the same inline-SVG-with-text-twin
  idiom for the sprint whose window contains the as-of, and cumulative flow as a data
  table; the same `pmbok.flow_facts.flow_snapshot` adapter feeds the hub's Flow tile, so
  the two figures can never disagree. Linked from the project hub), a per-project
  **task board** (`/projects/{id}/board` — every task in the column its `status` names. The columns ARE the model's `TASK_STATUSES` vocabulary, in its order, so a status added to the model becomes a column with no template edit and one removed stops rendering. Each card carries its task's workstream, assignee, percent complete and estimate — enough to pick the next thing up, with dates left to the schedule and money to the hub — and prints its own status as text, so **blocked** reads as blocked in greyscale and out of context; hue is never the only carrier. A column with no tasks says so, a project with no tasks at all renders the shared empty state rather than four empty boxes, and the whole board is one query with workstream and assignee joined in, flat in the task count. No as-of, and none threaded: a task carries no date, so nothing here is dated and regeneration is unconditionally byte-identical. Linked from the project hub), each
  portfolio and program name linking to its own **drill page** by REAL DB id (`/portfolios/{id}/rollup`,
  `/programs/{id}/rollup`) — that node's rollup KPIs plus its children's rows, read
  through the identical `gather` walk so a drill figure can never disagree with the
  dashboard, a **threat board**
  (`/threats`) that groups its ranked cards under per-project headings and
  paginates long lists (`?page=N`), marks each card with its week-over-week trend
  (▲ worsening / ▼ improving / – unchanged, or `new`) vs the same threat a week
  ago, and whose one-click sign-off removes a threat through the validated
  boundary and re-ranks the feed, a **process map** grid per project
  (`/projects/{id}/process-map`, knowledge-area × process-group, each cell
  coloured by state — a five-state legend renders from the same `st-*` classes as
  the cells, with `signed_off` its own colour distinct from `produced` and
  `not_started` reading neutral, and every **state** cell and legend chip also
  prints a state mark (`● ✓ ◐ — ○`, the legend's own order) from one shared table,
  so the grid stays readable in greyscale and `waived` never looks like
  `not_started`; a cell for a process the store tracks no output of reads
  *Not Tracked* in words instead of borrowing a state it is not in — and
  drilling into its
  process reference; each
  knowledge-area row also carries a small inline-SVG completion ring — that area's
  completeness computed with the same rule as `state.completeness`, per area, so
  it cannot drift from the cells, `n/a` when nothing is assessable and a bare grey
  track at 0%), a business-wide **process map** (`/process-map`, the same grid rolled up across every project, each cell washed by its share of applicable projects produced-or-better, pooling `state.completeness`'s own exclusion — `driftless/pmbok/rollup.py` — topped by a per-knowledge-area completion ring row pooled the same way, and a click on any cell (`?process={id}`) lists that process's applicable projects with their own state and a link back to each project's own map. Both headings freeze the way the heatmap's do: the knowledge-area column is `position: sticky` at the left edge of the shared `.scroll-x` box and the process-group headings at its top, so a figure in the middle of a grid too wide and too tall for one screen keeps both of the words that say what it counts — the vertical half needs a scrollport to freeze against, which is the box's own `max-height`. That box is also `position: relative`, and that is not decoration: `.sr-only` is `position: absolute`, so with no positioned ancestor the grid's off-screen spans laid out against the initial containing block, escaped the scroll box's clip and pushed the *document* 475px sideways at 1280 while the box itself measured correctly — found by `tests/browser`, which is the only tier that lays a page out), a **department surface** (`/org/departments` — the list rendering from the SAME
  `department_rows` the Department Report does; an **organization configuration** surface (`/org/configuration` — live counts for the business → portfolio → program → project hierarchy, departments, people and quality metrics, followed by the validated API path that creates each layer; it distinguishes setup from health rather than turning the dashboard into a finance-only setup page); `/org/departments/{id}` drilling into
  one department's accountable projects and each person's capacity through those same
  engines, scoped to that one department), a business-wide **capacity heatmap** (`/org/heatmap`, in the nav — person × week, each cell the hours that person's open, hour-estimated tasks put in that week against their weekly `capacity_hours`. ONE definition of allocation: it imports the Resource evaluator's task filter and its over/tight thresholds rather than restating them, so a row total is what `person_task_loads` returns for the same store; the evaluator has no *when*, so each estimate is spread evenly over the days of the planned window its newest APPROVED baseline line gives it. Every cell prints its hours, the share of that person's week they take, and — over or tight — that word, and draws the share again as a bar whose LENGTH is the ratio (clamped at the cell, so 150% cannot run past its own box), so the grid reads in greyscale, in forced-colours and in print: hue is never the only carrier, and neither is the fill. Person and Capacity are `position: sticky` inside the shared `.scroll-x` box, `.hm-cap`'s offset being `.hm-who`'s own width, so the two columns that say WHICH row you are reading stay put while twenty-six week columns pass under them. The legend is BUILT by `heatmap.legend` from `_WASHES` and the evaluator's ratios rather than written out — as written prose it had drifted to a 120% threshold the code never had. Columns are the as-of's own week and the five after it, never a wall clock, so a pinned as-of regenerates byte-identically. How far ahead is the reader's to set: `?weeks=N` moves the far edge, offered on the page as 4 / 6 / 13 / 26 links that carry the as-of they were rendered with, and reachable at any N in between. Six stays the answer when the parameter is absent, so every address and the nav entry render exactly what they always did. **26 is the ceiling** — half a year, past which an approved baseline plans almost nothing, so the extra columns are zeros bought at the full render price, and that price is the reason for a bound at all: a column is a `<th>` plus one `<td>` per person, so an unbounded `N` is a denial of service written into our own address bar. Out of range is **refused, not clamped**: 0, 27 or 5000 answer the designed 404 page holding no grid, because a caller who asked for a page this one cannot be is owed a refusal — quietly serving six instead is how a horizon nobody asked for gets read as the answer. One constant carries the bound, and `weeks_from` raises on a horizon outside it, so there is no second, looser way in. Hours with no approved window, or one past the horizon in force, are **unplaced** — in the total, claimed by no week, in their own column — so no hour is invented or lost; and a non-positive `capacity_hours` (impossible past `ck_person_capacity_hours`) reads `no capacity` and takes no ratio, never `0%`, where a person with capacity and no work reads `0`. Two queries whatever the store size, and the shared empty state when nobody is assigned anything), a project-independent
  **PMBOK reference** (`/pmbok`, the 49 processes as a stateless knowledge-area ×
  process-group grid straight from the frozen catalog, and `/pmbok/{id}` for one
  process's ITTO detail), a project-independent **technique library** (`/techniques`, its
  own primary-nav entry — every `TT_CATALOG` member grouped by family with a one-line
  summary, and `/techniques/{slug}` for one technique in full: when to use it, when to
  avoid it, ordered steps, outputs, pitfalls, a worked example and, where PMBOK-6 defines
  one, the clause it comes from. Addressed by the readable slug the ITTO page already
  prints as its anchor, from the one `naming.technique_slug` formula, so the raw
  registry key never reaches a URL and there is no second vocabulary; a slug naming no
  technique gets the designed 404. Reads no store and no clock, so every request renders
  the frozen registry identically), a per-project **RAID log**
  (`/projects/{id}/raid` — that project's risks, issues and change requests, each ordered
  by id so a refetch is byte-identical), a **business detail** page
  (`/business/{id}` — one business's portfolio → program → project hierarchy with the
  business-wide completeness `pmbok.rollup` computes, `n/a` rather than 0% when there are
  no cells yet), the **balanced scorecard** (`/scorecard`, in the nav — all four
  perspectives kept visible, missing strategy or evidence rendering as `unknown` rather
  than as a green number; `docs/balanced-scorecard.md` is its decision record), an
  agent-and-human **wizard** page (`/projects/{id}/wizard`), and a **weekly-status**
  edit form (`/projects/{id}/status`) that stamps the computed percent (never typed), draws an inline-SVG
  trend line of percent-complete from the project's append-only StatusSnapshot
  series — with the shared empty state in its place until there are readings, naming
  the form at the foot of the page and `POST /api/v1/status-snapshots`: the two chart slots
  empty independently and are filled by different actions, so each names its own next
  step — and plots a planned-vs-actual cost **S-curve** — time-phased `PV(t)` and
  `AC(t)` swept in-memory from the newest baseline and the dated costs against a flat
  `BAC`, plus `EV`/`CPI`/`SPI`/`EAC` at the as-of as text (a position, not a swept
  line — though the per-task readings behind it *are* dated: `progress_history` in
  `driftless/assess/adapters.py` replays each task's percentage out of the
  append-only ChangeLog, so an as-of is answered with the percentages that held
  then rather than today's number stamped with an old date) — all
  drift-free (stores nothing new — the stored rows are the source of truth). A store with nothing in it is a designed state, not a blank table: every list-shaped surface renders the one shared empty state (`web/templates/_empty.html`) naming what the surface is for and the command or link that creates the missing thing, and a refusal on a page path renders a designed HTML shell rather than a JSON dump (`web/errors.py`): an unknown or unparseable address is a **404** ("that address does not match anything in this store" — `/projects/abc/hub` answers 404, not the API's 422, because an address that does not parse names no page that exists), a form left open until its CSRF pair went stale is a **403** saying so and to reload, a request the page's own validation refuses is a **422** carrying its own wording rather than the API's `detail`, and anything else is the **500** shell. The shell is keyed on the page route, never on `Accept`, so every JSON API error body — 403, 404 and 422 alike — is byte-for-byte unchanged; no page shows anything about the exception. Every write goes
  through the same Pydantic-validated, ChangeLog-audited path the API uses. A
  tiny self-authored `static/driftless.js` makes the swaps feel instant; the pages
  work without it. Served behind a bearer-token gate (`DRIFTLESS_API_TOKEN`,
  `driftless.api.secure:secured` — the container's entrypoint); `/health` and
  `/static` stay open regardless so an orchestrator can probe without a
  credential, and a signed-out browser asking for a **page** is sent to `/login`
  (`303`) rather than handed the JSON `401` every other address still answers. **Readiness** is a separate, gated route — `/health/ready` compares
  the database's stamped Alembic revision against the one this code requires
  (`driftless/db/schema_version.py`) and answers 503 `schema behind` / `schema
  ahead` / `database unreachable`, and nothing more (`OPERATIONS.md`).
- **Calendar feed** (`driftless/api/calendar.py`) — the store's dates as RFC 5545 iCalendar,
  subscribable from Outlook, Google or Apple: `GET /calendar.ics` is every project and
  `GET /projects/{id}/calendar.ics` is one, the scope in the path so a subscription URL can never
  change meaning. Milestones and sprints are all-day events; a task is not one, carrying no date
  of its own (its window belongs to a baseline *version*). Each `UID` is the row's own key, so a
  rename updates an event rather than duplicating it, and nothing reads a clock, so an unchanged
  store re-serves the same bytes. Escaping and 75-octet folding are stdlib, not a dependency.
- **Search** (`driftless/api/search.py`) — one term over the whole hierarchy on two surfaces:
  `GET /search/results?q=…` answers JSON (and CSV, like every list route), each hit naming its
  `kind`, `id`, `label` and the `path` that shows it, so a caller links with no second round trip;
  `GET /search?q=…` is the page, grouped by kind and linked from the primary nav. Searched:
  portfolio, program, project, workstream and task `name` plus risk and issue `description` — what a
  person names a thing by, and only where a hit has a page to link to; plus the frozen Method
  registries, scanned in memory rather than by SQL and needing no project — PMBOK process id, name
  and summary, technique and artifact name and summary, glossary term and definition, and
  Scrum/Kanban practice name. Case-insensitive; bounded at one statement and 10 hits per kind (the
  registry scan runs no statement at all); the empty query and no-match render the shared empty
  state.
- **Reports** — generated documents (`driftless report all`) computed from the live
  store, each byte-identical on regeneration from an explicit as-of: cost/EVM,
  weekly status, risk register, schedule, scope baseline, charter, forecast, the
  business Portfolio Rollup, the **Department Report** (projects rolled up by the
  department accountable for them, with labour capacity and rate), the
  **Assessment Report** (every knowledge area's threats and recommended actions)
  and the **Process Map** (the 49-process grid with each process's computed
  state). Templates are **strict** (`report/engine.py` sets Jinja's
  `undefined=StrictUndefined`): a name no document passed — a misspelt
  `{{ completness }}`, a field a render path forgot — raises at render time
  instead of printing the empty string, so a figure cannot quietly leave a
  document while the suite stays green. The forecast core also offers a seeded
  **Monte Carlo** completion simulation (`calc/forecast.monte_carlo_completion`)
  — same seed, same percentiles. A separate **risk analysis** core
  (`driftless/calc/risk.py`) computes the P x I matrix, RBS categories, EMV,
  decision trees, tornado sensitivity ordering, and a seeded Monte Carlo over a
  risk register's own Bernoulli-trial exposure — none of it wired into a
  rendered document yet. **Quality tools** (`calc/quality.py`) are a
  second pure calculator core alongside EVM and forecast: a control chart
  (±3σ limits, out-of-control points, the rule-of-seven run signal), a
  Pareto split with an 80% "vital few" cut, a statistical sampling-plan
  formula, cost of quality (conformance vs non-conformance), an
  Ishikawa/fishbone shape with a five-whys chain helper, and a checklist
  pass/fail that names its failing items.
- **Migrations** — an Alembic chain building the whole schema, proven against
  Postgres 16 and asserted byte-for-byte against the models (CHECK constraints
  included) by the suite.
- **PMBOK ITTO catalog** — a versioned-in-code reference model of all 49 PMBOK-6
  predictive processes across the five process groups and ten knowledge areas,
  each naming its Inputs, Tools & Techniques and Outputs by reference into a
  closed `ARTIFACT_KINDS` / `TT_CATALOG` vocabulary. Property tests pin the
  counts and referential integrity. Query it with `driftless pmbok processes
  [--area A] [--group G]`, `driftless pmbok show <id>`, `driftless pmbok support`
  for the store-wide coverage summary below, and `driftless pmbok proof` (also
  `GET /pmbok/proof`) for the totality proof one level up from coverage: not "how
  much is explained" but "is anything left unaccounted for at all" — see
  `driftless/pmbok/proof.py` and `docs/testing-and-quality-gates.md`.
- **Method graph** (`driftless/pmbok/graph.py`) — every process, technique and artifact
  as one graph, `driftless.pmbok.graph.GRAPH`, built once at import from the catalog
  alone: `reads`/`produces` off a process's inputs/outputs, `used_by` off its tools and
  techniques, and a derived `process -feeds-> process` wherever one process's output is
  another's input. `.neighbours`, `.by_kind`, `.size` and `.to_dict` read it; pure and
  clock-free, so two builds are equal.
- **Method graph layout** (`driftless/pmbok/graph_layout.py`) — a deterministic 2-D
  placement for every `GRAPH` node, `driftless.pmbok.graph_layout.LAYOUT`, built once
  at import (no randomness, no physics library, no clock — two builds are always
  equal, the same pattern as `web/techniques.py`'s `BY_SLUG`). Five horizontal BANDS,
  one per `ProcessGroup` (Initiating..Closing, the enum's own lifecycle order) top to
  bottom; within a band, processes shelf-pack left to right in PMBOK-number order
  (`"4.1"` before `"4.2"` before `"5.1"`). Every technique and artifact is a SATELLITE
  of the processes that reach it — `used_by`/`reads`/`produces` edges off `GRAPH`
  alone, plus `part_of` (a component artifact inherits the processes of the artifact
  it is part of), never a second list — placed in the earliest band any of its
  processes belongs to, ordered within that band's own artifact/technique row by the
  x centroid of its own connected processes so it lands near the process(es) that use
  it rather than in family or alphabetical order. A member no tie reaches at all
  (`graph_layout.unconnected_member_ids()`, four of them today, each accounted for by
  a disposition or an extension) gets no band: it goes on one row in a TRAY below all
  five, `TRAY_GAP` clear of the last, which `web/templates/method_map.html` captions
  in words. There is deliberately no "fall back to the last band" rule any more — it
  made the map assert a Closing home the catalog never claims, and the tray's exact
  membership is pinned as a contract in `tests/test_graph_layout.py` so a fifth member
  cannot appear silently. `LAYOUT.positions`, `.label_boxes` and `.edge_paths(edge)` are
  all a later SVG renderer needs; an over-full row wraps onto another rather than
  shrinking a label. `.edge_paths` starts/ends on a node's own box edge, not its
  centre: a same-row tie steps above (left-to-right) or below (right-to-left) its
  row by a small fixed clearance, clearing every box shelved between its two
  endpoints instead of running straight through them; a tie between rows exits and
  enters at the box's top or bottom edge with one smooth curve.
- **Method graph views** (`driftless/pmbok/graph_views.py`) — two readable slices of
  `GRAPH`, for a map that shows one readable part of the graph rather than every node at once.
  `overview()` is every process node in lifecycle order (the `ProcessGroup` enum's own
  order, then PMBOK number sorted numerically so `"4.2"` precedes `"4.10"`) with the
  `feeds` ties between them; `neighbourhood(node_id)` is one node's ego network — the
  node, its direct `GRAPH.neighbours`, and ONLY the edges with both ends inside that
  set, so no line dangles off the view. A node the catalog leaves unconnected returns
  itself with zero ties; an unknown id raises `KeyError` rather than reading as
  "connected to nothing". Both return a `GraphView` whose `.counts()` measures the
  slice against `GRAPH.size()` — four numbers (`nodes`, `edges`, `total_nodes`,
  `total_edges`), never a sentence, so the wording stays the caller's. Every node and
  edge is an object taken straight out of `GRAPH`, never copied or re-derived from the
  catalog; pure, deterministic and clock-free, the same contract `graph_layout` keeps.
- **Method map page** (`driftless/web/method_map.py`, `GET /map`) — the renderer
  `LAYOUT` was built for, the last link in one derivation chain: the frozen PMBOK
  catalog decides `GRAPH`, `GRAPH` decides `LAYOUT`, and `GRAPH`/`LAYOUT` together
  decide this page — plus, off the same `GRAPH`, `.to_dict`'s JSON shape for a
  later machine-readable route, so the picture and that shape can never disagree
  about what the graph contains. One inline SVG drawn straight from `GRAPH`/`LAYOUT`,
  no graph library and no client-side layout pass, so the page is readable with no
  JS at all — the same `static/driftless.js` contract every other page keeps: the
  script makes it feel instant, but nothing here depends on it running.
  What it draws is one slice, chosen by `graph_slice()`: `graph_views.overview()`
  by default (all 217 nodes at once came out thumbnail-sized and mostly unlabelled),
  `graph_views.neighbourhood()` when `?focus={id-or-slug}` resolves to a node, and the whole
  graph only under `?view=all`, kept for exhaustive reading. `?from=&to=`'s breadth-first
  `feeds` path and `?group=`/`?area=`'s process set resolve BEFORE that seam and hand it a
  slice, so a word none of them answers to is noticed rather than 404ing or drawing nothing. A sentence above the drawing
  states the slice against the whole (`GraphView.counts()` hands over four numbers; the
  wording is the page's), links move between the three reads, and `Escape` returns to the
  overview off `data-overview`, never an address `map.js` builds.
  `?project=&as_of=` washes each process node with the SAME reading
  `/projects/{id}/process-map` computes (`views.state_word`/`CELL_RANK`/`CELL_MARK`
  — never a second state rule); `?focus=` also keeps the `focus`/`focus-neighbour`
  marking the "See it on the map" line every process/technique page links to. The
  washed legend also gains a State row, straight off `views.LEGEND` (the same rows
  `/projects/{id}/process-map` legends), so a state mark on the picture is
  explained wherever it appears. The longer shapes/lines explainer is folded
  under its own collapsed "How to read this map" `<details>`, so the drawing
  is not pushed below five paragraphs, 28 chips and 19 legend rows of prose
  first (MP29); an always-present "How to read this page" `<details>` still
  orients a first-time reader, and a Related block
  (`web.related.for_map`) anchors the picture back to `/pmbok`, `/techniques`,
  `/artifacts`, `/process-map` and the washed project's own process map. The
  per-node panels and the `<details>` per node kind below the SVG are rendered for EVERY
  graph node whatever the slice — the no-JS alternative stays exhaustive, and each entry
  links to that node's own neighbourhood, so the picture is never the only way in.
  Each node is a filled shape — process a rounded square, technique a circle,
  artifact a diamond — tinted by `data-area`/`data-family` (`static/map.css`); a
  process label is visible at rest, a technique/artifact label stays hidden until
  its own shape is hovered/focused (plain `:hover`/`:focus-within`, so this still
  works with `static/map.js` stripped), or the drawing is a narrow one — every slice but
  `?view=all` carries `.map-narrow` from the server, so a slice labels every shape it
  draws with no script running. The `<svg>` carries its own `width`/`height` from
  `LAYOUT.viewbox`: a viewBox alone scaled it to the column, so it read as a thumbnail
  and `_scroll.wide`'s box never moved sideways. A `focus` slice is the one exception:
  `graph_layout.focus_layout` builds a wholly LOCAL layout for that one process's
  neighbourhood, packing each technique/artifact satellite (and any `feeds` process
  neighbour) at its own label's width rather than a satellite's small dot/diamond,
  so a `.map-narrow` view — which reveals every label at once — never overlaps two of
  them; that local layout carries its own `viewBox`/`width`/`height`, independent of
  `LAYOUT`, so widening one process's satellites never grows every other slice's
  drawing (`tests/test_graph_layout.py`).
  `static/map.css` and `static/map.js` (loaded only here, via
  `base.html`'s `scripts` block) are progressive enhancement on that same markup:
  `map.js` may only toggle classes and `hidden` on elements the template already
  rendered — hover/pin off `data-node`/`data-from`/`data-to`, the pill filters off
  `data-kind`/`data-group`/`data-area`/`data-family`, search off a shape's own
  `data-label` (never its `<title>`, which also carries its kind and, once
  washed, its state word), the reset control clearing them back to "every node",
  and the per-node `<aside data-panel-for>` panel
  already in the DOM -- opened by the same hover/focus that lights the ties, so it
  is reachable with a mouse alone, and held open by Space on the focused shape.
  It binds no click handler at all: a shape is an `<a href>`, so a click -- plain,
  modified or middle -- is the browser's to answer, and `preventDefault()` is
  reached only by the pin key. It may never fetch, store, or
  leave the page unusable with it absent.
  `GET /map/graph.json` (`driftless/web/method_map_json.py`,
  registered directly on the app like `/calendar.ics` and `/search/results` above, not
  mounted as a page) serves `.to_dict()` read-only, plus a top-level `source_version`
  and, per node, the redraw fields the SVG above uses: `x`/`y` off `graph_layout.LAYOUT`,
  `group`/`area` (process nodes) or `family` (technique/artifact nodes), and `href`:
  the registry is now reachable from the JSON API, resolving the earlier decision that
  it was not, and an external renderer can draw the same map from this route alone.
- **Schedule network** (`driftless/calc/network.py`) — the critical path method over
  plain `Activity`/`Dependency` objects: forward/backward pass, total and free float,
  every zero-float path (`critical_path`), all four dependency kinds with lag and
  lead, a `network_diagram` shaped like the method graph's nodes/edges for a later
  SVG renderer, and non-mutating `schedule_compression_preview` /
  `resource_levelling_preview` scenarios. Not wired to a stored task — see
  `docs/pmbok-mapping.md`.
- **Related index** (`driftless/web/related.py`) — one shared "Related" block, starting
  with `for_process`, built purely over `GRAPH`/`TECHNIQUES`/`ARTIFACTS`/`METHODS`/
  `GLOSSARY` rather than a second copy of any of them. `_related.html` renders the result
  as one `aria-labelledby`'d `<section class="related">`. `for_artifact` is adopted on
  `/artifacts/{slug}`: the foot of the page carries the kind's making and reading
  processes, the bundle it is a named part of and its own parts (`artifacts.COMPONENT_OF`),
  the agile evidence that can stand in for it (`crosswalk.EQUIVALENCES`), the rest of its
  family, the techniques its producing processes use, and the map focused on it.
  `for_technique` is adopted the same way on `/techniques/{slug}`: the processes that use
  the technique, the rest of its family, the artifacts those processes produce, and any
  method practice that crosswalks to it, so even a technique no process names still
  reaches the map. `for_practice` and `for_term` render one block per practice on
  `/methods/{key}` and one per term on `/glossary`; the term block reads a reverse index
  of the glossary over every registry field, built once at import rather than per request.
  Only `for_process`'s own page is still a follow-up over the same shape.
- **Technique registry and its written explanations** — `driftless/pmbok/definitions.py`
  gives every `TT_CATALOG` member a `TechniqueDefinition`: key, display name, family,
  source, and the edition string only where the edition actually names it, so a technique
  Driftless added itself cites no clause rather than a false one. The registry is built
  from the same family sets as `TT_CATALOG`, so the two cannot diverge — there is no second
  list. The explanations themselves (summary, when to use, when to avoid, ordered steps,
  outputs, pitfalls, a worked example, the clause) live in one module per family under
  `driftless/pmbok/technique_content/`, discovered rather than imported by name, so a
  family can be written in a single new file; a module claiming a key outside its family,
  outside the catalog, or already claimed fails at collection. Every word is ours — no
  standard prose is reproduced — and a citation nobody could confirm is left blank, with
  the reason recorded in the gate (`docs/testing-and-quality-gates.md`).
- **Documented gaps** — `driftless/pmbok/reasons.py` holds one `Reason` (a `kind` enum plus
  one sentence) for every technique with no assistant route, every artifact kind the wizard
  cannot produce, and every technique that carries no citation. Each of the three dicts is
  asserted *equal* to the gap it covers (`tests/test_launcher_totality.py`,
  `tests/test_technique_totality.py`), so the dicts shrinking as assistants and producers
  land is the product's support progress, derived rather than remembered; `NOT_YET_BUILT` is
  the only kind that names work still owed — a worksheet that ships moves its technique off it
  to `WORKSHEET_ONLY`, which `tests/test_launcher_totality.py` walks `WORKSHEETS` to enforce.
- **Printable worksheets** — `driftless/pmbok/worksheets.py` holds `WORKSHEETS`, built
  the discovered-module way `technique_content` is: a sibling `worksheets_*.py` file
  exports `ENTRIES`, a claimed key fails at collection, every key is a real
  `TT_CATALOG` member. The guide-only techniques of the schedule, quality and resource
  families each carry one, asserted family by family in
  `tests/test_worksheets_knowledge_areas.py`; the integration family is still owed its own. `_worksheet.html` renders one as a no-JS printable form, plus a
  `steps_checklist` macro for a technique's `steps` (TQ08); `_help.html`'s
  `how_to_read` wraps a page's copy in `<details>`. Neither macro is adopted yet.
  The general, integration, procurement, risk and stakeholder families' guide-only
  techniques each carry one (`worksheets_general.py`, `worksheets_integration.py`,
  `worksheets_procurement.py`, `worksheets_risk.py`, `worksheets_stakeholder.py`):
  for procurement, the tooling an organisation runs rather than a calculation
  Driftless could do — the advertised purchase, the bidder conference, the claims
  log, inspections and audits and supplier performance reviews, none of which a
  calculator could honestly serve. Each is checked against `FAMILIES` and
  `GUIDE_ONLY_REASONS` rather than counted by hand; `worksheets_general.py` also
  holds the schedule family's `rolling_wave_planning`, the one sheet that proved
  the registry before any family was finished. Scope and cost have no guide-only
  technique at all, so neither is owed a worksheet; quality, resource and the
  rest of schedule still follow, and the catalogue-wide assertion belongs to
  whichever change serves the last of them.
  `tests/test_worksheets_integration.py` asserts totality over the integration family
  alone — the catalogue-wide version belongs to whichever change serves the last family,
  so a family still being worked cannot redden another's suite.
- **Artifact registry and its plain-language explanations** — `driftless/pmbok/artifact_definitions.py`
  gives every `ARTIFACT_KINDS` member an `ArtifactDefinition`: key, display name, family, and a
  plain-language explanation aimed at a reader who has never heard of project management.
  `produced_by`/`read_by` are derived by walking `catalog.PROCESSES` rather than typed, and
  `tracked_by` is derived from `mapping.is_tracked`, so none of the three can drift from the
  tables they describe. The explanations live in one module per family under
  `driftless/pmbok/artifact_content/`, discovered the same way `technique_content` is.
  `driftless/web/artifacts.py` is where the registry becomes reachable: `GET /artifacts`
  and `GET /artifacts/{slug}`, addressed by the same collision-refusing slug pattern
  `web/techniques.py` uses for the technique library, and `pmbok_detail.html`'s ITTO
  table links every input and output there instead of printing the raw key.
- **Support coverage** — `driftless/pmbok/support.py` answers "how much of the methodology
  can this product actually help with, and where are the holes?" by walking the catalog and
  the registry together: per process, whether the store can judge it and which of its
  outputs the wizard can produce; per technique, whether it is explained and what help it
  will eventually offer. Store-independent and clock-free by construction — it takes no
  session, project or as-of, because these are properties of the product rather than of any
  one project's history. Three surfaces read it rather than restate its rules: `driftless
  pmbok support` prints the store-wide counts; the `/pmbok` reference grid names each
  process's tier in a newcomer's words ("You can fill this in here" / "We can judge this
  step" / "Read-only for now"); and every `/techniques/{slug}` page says its technique's
  tier ("Runnable here", once routed, or "Guide only — " plus its `reasons.GUIDE_ONLY_REASONS`
  sentence).
- **Process state (computed, never stored)** — `driftless/pmbok/mapping.py` resolves
  each artifact kind to live rows (is a `scope_baseline` present? a
  `status_report` fresh within cadence? an `agreements` disputed?), and
  `driftless/pmbok/state.py` derives each project's state on each of the 49
  processes from those artifacts plus the append-only sign-off ledger:
  not-started → in-progress → produced, or signed-off / waived. There is no
  ProcessInstance table — a tailored-out process is a `SignOff` with decision
  `waived`, so state cannot drift, and completeness excludes waived and
  untrackable processes.
- **Agile/operations crosswalk (`driftless/pmbok/crosswalk.py`)** — for nine artifact
  kinds a Scrum/Kanban or an operations-cadence project's evidence does not sit in
  `mapping.py`'s predictive-shaped rows at all; it sits in `models/agile.py`'s roles,
  backlog items, releases, definition-of-done items and impediments, plus the
  review/retrospective fields `Sprint` carries — or, for an operations-cadence
  project (`Project.delivery_mode == "operations"`), in `models/operations.py`'s
  service levels, incidents and recurring work, read off
  `Project.responsible_department_id`. `crosswalk.EQUIVALENCES` names, per kind,
  where that evidence lives and the plain-English rule that reads it — a
  `native_source` and a `rule_in_plain_words`, rendered verbatim on the process
  page; a resolver that covers both branches reads `project.delivery_mode` itself,
  never a second dispatch table. `mapping.resolve` consults it only when its own
  resolver (or the absence of one) finds nothing AND the caller allows it
  (`allow_crosswalk`, `driftless.pmbok.state`'s per-control gate below), so a
  native row always outranks an equivalence and neither module writes; see
  `docs/pmbok-mapping.md`'s **Agile equivalences** table for the full list.
- **Hybrid tailoring (`driftless/pmbok/tailoring.py`)** — a `TailoringProfile` per
  `Project.delivery_mode` (predictive / agile / hybrid / operations) says whether
  each Monitoring & Controlling process reads on a `PREDICTIVE_BASELINE`, an
  `ADAPTIVE_COMMITMENT` or an `OPERATIONS_CADENCE`, with a one-sentence plain
  reason; totality (every Monitoring & Controlling process, every profile, exactly
  once) is pinned by `tests/test_pmbok_tailoring.py`. Monitor and Control Project
  Work (4.5) and Perform Integrated Change Control (4.6) are always
  `PREDICTIVE_BASELINE` — the one change and approval boundary, `ChangeRequest` →
  `Baseline`, never moves, whatever the rest of the project's controls are
  tailored to. There is no separate `Department.delivery_mode`: an operations
  project is a project whose OWN `delivery_mode` is `"operations"`, read through
  `Project.responsible_department_id`. This is presentation-only no longer:
  `driftless.pmbok.state.process_state` reads each Monitoring & Controlling
  control's own mode and only lets `mapping.resolve` fall back off a control's
  native rows when that mode is not `PREDICTIVE_BASELINE` — a hybrid project's
  cost control stays pinned to its baseline even though the SAME project's scope
  control reads agile evidence (`tests/test_pmbok_mode_aware_state.py`). Pure data
  over the frozen catalog, no store read: the process map and the PMBOK reference
  detail page show the mode beside each control, and `/org/configuration` lists
  the profiles in plain words. `driftless/web/change_boundary.py` is the one place
  a what-if assistant (the earned-value calculator's cost scenarios today) links
  back to raising a change request, so a hypothetical never grows its own second
  way to become the real plan.
- **Assessment engine (`driftless/assess/`)** — a pure evaluator per knowledge area
  turns calc/records signals into an `Assessment` (risk score, RAG status,
  evidence coverage — measured, stale, missing, or not applicable — threats,
  and recommended actions drawn from the PMBOK tools & techniques). Coverage
  stays separate from RAG, so green never quietly means an unmeasured control:
  Cost (CPI/VAC), Schedule (SPI/slip), Scope (approved-but-unbaselined changes),
  Risk (exposure vs contingency), Stakeholder (disengaged power players),
  Communications (stale reporting), Resource (over-allocation vs capacity),
  Quality (direction-aware threshold breach/stale), Procurement (disputes/lapses/over-budget),
  and Integration (worst-of the rest). Every threat's id is its sign-off subject —
  built by the one `pmbok/state.threat_subject_ref(kind, project_id)`
  (`"{kind}:project:{id}"`, mirroring `process_subject_ref`), never by hand — so
  suppression matches by byte equality without a format drifting per evaluator.
  Threats rank into a feed and a sign-off
  suppresses one **only while its score stays no worse than at sign-off** — a
  regression re-surfaces it, so a sign-off cannot bury a slide. Computed, never
  stored; `driftless assess <project> --as-of D` prints the ranked result.
  `driftless/assess/feed.py` folds those threats together with incomplete-data
  signals (no status ever filed, stale status past 14 days, low process
  completeness — each at a fixed score below the red band, wizard-enriched with
  the next process to run) into one attention feed sorted red-threats-first,
  then by (score desc, id asc) — every red threat outranks every data signal
  regardless of raw score. That order is the contract: the web renders it
  verbatim, never re-ranks.
- **Onboarding wizard (`driftless/wizard/`)** — walks a project through the process
  groups in lifecycle order and, for the next incomplete process, reports its
  PMBOK inputs (whether each exists, and — for a missing one — the earlier process
  that produces it), its tools & techniques, and the outputs it can produce.
  `WizardStep.kind` names what this step actually is: `form` when the wizard can
  produce an output, `derived` when the output only resolves on read from inputs
  already in the store, `reference` when nothing about the process is tracked at
  all — no process is skipped as a dead end any more, each renders honestly
  instead. It is agent-drivable: `driftless
  wizard next --project X` returns the next step as JSON, `driftless wizard status
  --project X` the whole process-state map, and `driftless wizard apply --project X --kind K`
  produces an output **through the same validated API boundary** the HTTP
  endpoints use (Pydantic validation, parent checks, ChangeLog audit) — so a
  loop can stand a project up end to end with no human, and the ChangeLog proves
  every write went through the boundary. Each kind is produced from the fields it is made of
  (`--field name=… `, `--field planned_cost=…`): a producer **refuses** rather than
  substituting one, since the presence checks only count rows and a placeholder would mark
  that output produced for good — unattended drivers pass `seed_fields(kind, as_of)`.
  Baseline kinds stand the first plan up
  only: while an approved baseline exists the wizard refuses rather than laying a
  second one beside it, and the baseline's four rows land on one commit.
- **Preview/apply/confirm** (`driftless/services/changes.py`) — a status snapshot
  and a sign-off (the two native writes a wizard or a form can make today) each get
  a `preview` (what would be written, no write made), an `apply` (through
  `create_status_snapshot`/`create_sign_off` — never `session.add` directly) and a
  `confirm` (a sign-off-shaped, actor-stamped acknowledgement of an applied change;
  append-only — a second look is a new record, never an edit of the first). The
  **propagation manifest** (`driftless/pmbok/consumers.py:CONSUMERS`) names five
  families that read a project — process state, the rollups, the report
  documents, the assessment engine and the export/import surface — and
  `tests/test_propagation_manifest.py` proves each native change alters every
  family the manifest declares reachable, or that family is named in
  `driftless/pmbok/consumers.py:UNAFFECTED_BY_CHANGE` with the reason it cannot be:
  a family missing from both is a silent gap the test catches rather than a
  consumer nobody thought to check.
- **Demo store** (`driftless/demo/`) — `driftless demo seed --base-url URL [--token T]
  [--anchor YYYY-MM-DD] [--force]` populates a running instance with a small,
  deterministic demo store (2 businesses, a program, 4 projects with a mix of task
  statuses, one clearly-worst risk, one slipped milestone, approved baselines/budget
  lines/cost entries on the **statused three** so the dashboard's S-curve, burn
  sparklines and portfolio treemap render with real shape, five strategic objectives
  across all four scorecard perspectives with measured and missing evidence, and one
  project with no baseline or status data at all; one project runs **hybrid** delivery —
  four iterations, a release, a board whose cards carry their own
  `created_on`/`started_on`/`done_on`, impediments, a definition of done — so the flow
  calculator, the hub's flow tile and the rollup's flow columns render real figures
  rather than their empty state, durations and trailing-week throughput included, at the
  anchor rather than only at the wall clock; the **predictive** one carries a nine-task
  post-production plan wired by ten typed dependencies — a start-to-start pair among
  them — so the gantt page draws a network with a critical path and two tasks holding
  real float, rather than a pair of bars in one corner) through the same validated
  API the wizard and importer use. A store that already holds rows is **refused**
  unless `--force` says to seed on top of it, so a demo cannot be poured into real
  data by habit.
  `driftless.demo.data.demo_payload` is a pure builder — every date derives from the
  anchor by a fixed offset, so calling it twice returns an identical structure.

Building on this foundation: the PMBOK ITTO catalog, the per-output assessment
engine, the onboarding wizard and the threat/process web surface. The ITTO
build-out plan those were scoped against lived in the workspace monorepo's
`.data/` and did not come with this repo when it was extracted; there is no
`.data/` here. `CHANGELOG.md` plus the fragments in `changelog.d/` are the
record of what actually shipped.
