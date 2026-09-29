# driftless — Competitor Analysis

**As of 2026-09-22.** The driftless side of every row below cites this repo at
`path` or `path:line`, so it can be checked in a minute. The competitor side is
**point-in-time and unverified**: written from general knowledge of these
products, not from a documentation pass, and these vendors ship monthly. Treat
every competitor cell as a claim to re-check before it is repeated to anyone
outside. **Unknown is written as `?` and is a real answer** — a wrong confident
claim about a named product is a liability, an honest gap is not. No pricing is
quoted for anyone: it moves constantly and none of it was verified here.

## 1. Feature matrix

`✓` has it · `~` partial · `—` absent · `?` not verified. Columns: **MSP** =
Microsoft Project (desktop + Project for the web), **SS** = Smartsheet, **Jira**
= Jira with Advanced Roadmaps, **Asana**, **PV** = Planview Portfolios,
**OP** = OpenProject.

| Capability | driftless (evidence) | MSP | SS | Jira | Asana | PV | OP |
|---|---|---|---|---|---|---|---|
| Percent complete computed from evidence, not typeable | ✓ the create body has no percent field; the route stamps it from calc — `driftless/api/schemas.py:StatusSnapshotIn`, `driftless/assess/percent.py:stamped_percent` | — editable field | — a cell someone types | ~ rolls up from issues; the summary colour is still chosen | ~ rolls up from tasks; the on-track badge is chosen | ? | ~ a field; newer versions can derive it |
| Overall health (RAG) derived, not declared | ✓ worst-child-wins over computed evaluators — `driftless/calc/rollup.py`, `driftless/assess/engine.py` | — | — | — | — status is picked in the update form | ? | — |
| Plan history additive — approved baseline frozen, re-baseline inserts a version | ✓ `(project_id, version)` unique, writes to an approved baseline refused — `driftless/models/delivery.py:Baseline` | ~ up to 11 baseline slots, overwritable | ~ baseline start/finish variance | ? saved plans / scenarios | — | ? | ? baseline comparison view |
| Earned value (EV, CPI, SPI, EAC) off a time-phased baseline | ✓ `driftless/calc/evm.py`, `driftless/report/documents/cost_evm.py` | ✓ built-in EVM fields | — build it in formulas | — | — | ? financial planning; EVM unverified | — budgets and cost reporting, not EVM |
| Generated documents regenerate byte-identically from an explicit as-of | ✓ `driftless/report/engine.py:render_document`, proven by `tests/test_report_engine.py:test_the_same_inputs_render_byte_identically` | ? | ? | ? | ? | ? | ? |
| No wall clock anywhere in a rendered surface | ✓ every page and report takes `?as_of=`; the Gantt's "today" is the as-of — `driftless/web/gantt.py`, `docs/user-guide.md` (*Every page takes `?as_of=`*) | ? | ? | ? | ? | ? | ? |
| Portfolio → program → project rollup | ✓ one `gather` walk behind dashboard and drill alike — `driftless/calc/rollup.py`, `driftless/web/drills.py` | ~ per-plan on desktop; portfolio in the hosted tiers | ~ portfolio dashboards, higher tier | ~ Advanced Roadmaps (Premium) | ✓ Portfolios and Goals | ✓ core | ~ project hierarchy |
| PMBOK 49-process map with computed per-project state | ✓ no ProcessInstance table; state derived from artifacts + sign-offs — `driftless/pmbok/catalog.py`, `driftless/pmbok/state.py:process_state` | — | — | — | — | ? methodology templates | — |
| Append-only audit of every write, with the actor | ✓ a flush listener no write path can skip — `driftless/db/changelog.py` | ? | ~ cell history and activity log | ✓ issue history and audit log | ~ activity feed; audit API on the top tier | ? | ✓ work-package journals |
| A signed-off problem re-surfaces if it gets worse | ✓ suppression holds only while the live score stays no worse than at sign-off — `driftless/assess/engine.py:is_suppressed` | — | — | — | — | ? | — |
| Dependencies, critical path, schedule computation | ✓ forward/backward pass, float and critical path over a calendar — `driftless/calc/network.py:critical_path`, `driftless/models/schedule.py:TaskDependency`, `:ProjectCalendar` | ✓ strongest in this set | ✓ dependencies and critical path | ~ dependencies, no CPM | ~ dependencies, no CPM | ~ | ~ dependencies and Gantt |
| Resource levelling | ~ names who is over capacity, never moves the work — `driftless/web/heatmap.py` | ✓ | ~ Resource Management add-on | ~ capacity in Advanced Roadmaps | ~ Workload | ✓ capacity planning is core | ~ |
| Runs entirely on hardware you control | ✓ two containers, loopback by default — `docker-compose.yml`, `OPERATIONS.md` | ~ desktop files; Project for the web is hosted | — hosted only | ~ Data Center self-hosts | — hosted only | ? | ✓ self-hostable community edition |
| Third-party integrations, notifications, mobile apps | — none: no email, webhook or mobile path exists; one outbound iCal feed — `driftless/api/calendar.py` | ✓ | ✓ | ✓ large marketplace | ✓ | ✓ | ✓ |
| Attachments, comments, discussion on a record | — no such table; narrative is a field on the record | ✓ | ✓ | ✓ | ✓ | ? | ✓ |
| Bulk CSV in and out through the validated write path | ✓ import posts through the API, every list route answers `?format=csv` — `bin/driftless-import.py`, `driftless/api/export.py` | ✓ | ✓ | ✓ | ✓ | ? | ✓ |
| Drivable end to end by an agent through one validated boundary | ✓ `driftless wizard apply` writes through the same API as the UI — `driftless/wizard/`, `docs/agent-guide.md` | ~ REST API | ~ REST API | ~ REST API | ~ REST API | ~ REST API | ~ REST API |
| The whole method drawn as one picture — every process, technique and artifact, joined by how each reads, produces, uses or feeds another | ✓ one graph built once from the frozen catalog, no client-side layout — `driftless/pmbok/graph.py:GRAPH`, `driftless/web/method_map.py` | — | — | — | — | ? methodology templates | — |
| A technique's help is tiered and says so: explained only, a worksheet, or a calculator that runs its own formula | ✓ every technique names its tier in plain words on its own page — `driftless/pmbok/definitions.py:AssistanceMode`, `driftless/assess/model.py:ASSISTANT_ROUTES` | — | — | — | — | ? | — |
| An agile or a department-operations project satisfies the same controls as a predictive one, read from its own kind of evidence | ✓ a crosswalk names, per control, which agile row stands in for the predictive one and the rule that reads it — `driftless/pmbok/crosswalk.py:EQUIVALENCES` | — | — | ~ Advanced Roadmaps reframes some fields, not a stated crosswalk | — | ? | — |
| Which controls read against a fixed plan versus the team's own current commitment is a stated, per-project setting | ✓ `driftless/pmbok/tailoring.py:PROFILES`, shown beside every control on the process map | — | ~ project settings, not stated as ITTO tailoring | ~ Predictive vs. Agile-Advanced Roadmaps are separate products, not one project's setting | — | ? | — |
| Running a technique is itself a recorded fact, not only its output | ✓ an append-only row per run — technique, process, actor, as-of and what it read and produced — `driftless/models/technique_runs.py:TechniqueRun`, `driftless/services/technique_runs.py:record_run` | ? | ? | ? | ? | ? | ? |
| Support coverage is a number the product computes about itself, not a claim in a deck | ✓ every technique and artifact kind is either supported (and how) or unsupported (and why), asserted as a total set — `tests/test_launcher_totality.py`, `driftless pmbok support` | ? | ? | ? | ? | ? | ? |

Several rows are `?` across the board — byte-identical regeneration, no-wall-clock, per-run
provenance and computed support coverage among them. Not one of these vendors states any of
those as a product property, so there is nothing to cite; that is not the same as having
verified they lack it, and it is written
as `?` rather than `—` for that reason.

## 2. Gap register

Everything a competitor has that driftless does not, with the decision. No
silent gaps. Rows that used to live here and have since shipped are gone from
this table and listed as strengths below instead — that move, not a fresh
read of the competitors, is what changed since the 2026-08-02 refresh.

**Landed since the last refresh, now strengths, not gaps:**

- Dependencies, critical path, schedule computation and calendars — `driftless/calc/network.py:critical_path`, `driftless/models/schedule.py:TaskDependency`, `:ProjectCalendar`.
- WBS, requirements traceability, deliverable acceptance, closeout — `driftless/web/assist_requirements.py:create_assist_requirements_router`, `driftless/web/assist_closeout.py:create_assist_closeout_router`.
- Gantt, kanban board, capacity heatmap, outbound iCal feed, search, bulk CSV export — `driftless/web/gantt.py`, `driftless/web/board.py`, `driftless/web/heatmap.py`, `driftless/api/calendar.py:feed`, `driftless/api/search.py:Searched`, `driftless/api/export.py:csv_response`.
- Baseline history is additive, never reset, unlike the Planview rebaseline pattern — `driftless/models/delivery.py:Baseline`.
- Field-level audit log is free and append-only on every tier, unlike the tools that paywall it — `driftless/db/changelog.py:ChangeLog`.

| Gap (who has it) | Decision |
|---|---|
| Resource levelling (MSP, Planview) | **Boundary.** The heatmap names the over-allocated person and week; a human moves the work. |
| Outbound webhooks and an email digest of the attention feed (every SaaS tier) | **Planned.** An in-app notification centre stays a **boundary** (no JS framework, no stored dashboard state); the subscription-plus-digest pair does not. |
| Attachments and comments (table stakes everywhere) | **Planned, narrower.** File storage stays a **boundary**; a URL/hash reference row and an append-only note row cover the actual need without a blob store. |
| OIDC login (paid-gated at most vendors) | **Planned**, free. SAML/LDAP/SCIM stay a **boundary** — OIDC covers the IdPs that matter; MFA is **revisit**, deferred to real customer need. |
| Print-to-PDF (everywhere) | **Planned** as a print stylesheet, not a PDF engine — that stays a **boundary**. |
| MS Project / Primavera import, DCMA 14-point check, earned schedule, IPMDAR-shaped export | **Planned.** All are pure functions or importers over data driftless already stores; none add a second write path. |
| Time tracking / timesheets (SaaS, Vikunja Pro) | **Boundary.** `CostEntry` is the actual-cost input; hours are one unit of cost, not a timer. |
| Mobile apps (everyone) | **Boundary** for offline write (a second write path); a responsive web manifest is **planned**. |
| i18n (Odoo, ERPNext, OpenProject) | **Revisit** — only if a non-English customer exists. |
| MCP server, an agent as a bookable resource (Asana, Jira, Wrike, Smartsheet, Planview, OpenProject) | **Planned**, over the existing validated API — no second write path. Every write still lands in the ChangeLog with the agent as actor. |
| Stage-gate object, KPI approval workflow, evidence-derived control state, resource clash preview, scenario/what-if | **Planned**, each a thin layer over data driftless already stores (`SignOff`, `OperatingControl`, the heatmap). |
| Multi-tenant hosted service (all but OpenProject) | **Boundary.** One instance, one organisation. |
| Automation rules engine, real-time collaboration, chat | **Boundary.** Webhooks let an external runner react; an in-product rules engine or chat is a second write path. |
| PMBOK 7/8, PRINCE2 crosswalk (Method Grid, Bubble) | **Planned**, as a reference crosswalk table only — no second process catalog. |
| Ecosystem — marketplace, templates, connectors, trained contractors (Jira, Smartsheet, Asana, MSP) | **Not a target,** and not something a single service can answer. |
| Support, SLAs, training, certification (every commercial product here) | **Absent.** There is no support organisation. |
| Maturity — years of production use across many organisations (all of them) | **Real, and not closable by a feature.** driftless runs one business's portfolio (`README.md`, *Exit Condition*). |

## 3. Pain-point register

Complaints commonly made about tools in this class. **These are not sourced
here** — no review corpus was read for this document, so read the left column as
a hypothesis to test with a real prospect, not as a citation. The right column
is grounded and checkable.

| Complaint | The structural answer |
|---|---|
| "Status is whatever the PM types the night before the steering meeting." | The status form has no percent field; the route stamps it from calc at the snapshot's own date — `driftless/assess/percent.py:stamped_percent`, `docs/user-guide.md`. |
| "The plan got quietly rebaselined and the original is gone." | An approved baseline is frozen and re-baselining inserts a new version; both are schema-level — `driftless/models/delivery.py:Baseline`. |
| "The dashboard and the board deck disagree." | One store; every figure is a query over it, and `driftless/calc/` is imported by both the web surface and the report engine, so a number on a screen and the same number in a document share one implementation. |
| "Nobody can say who changed that number." | Every write through a session is logged with actor and the values that moved, by a flush listener rather than by calls at each write site — `driftless/db/changelog.py`. |
| "Re-run last month's report and the numbers have moved." | The as-of is threaded explicitly and nothing reads a clock; identical regeneration is a test, not an intention — `tests/test_report_engine.py:test_the_same_inputs_render_byte_identically`. |
| "Our portfolio data lives in a vendor's cloud and leaving is a project." | It runs on your own hardware, the store is Postgres, and every list route exports CSV — `docker-compose.yml`, `driftless/api/export.py`. |
| "A process was tailored out and now nobody remembers it existed." | A waiver is a signed row in an append-only ledger, and completeness excludes it explicitly — `driftless/pmbok/state.py`. |
| "That risk was signed off and then quietly got worse." | Suppression holds only while the score stays no worse than it was at sign-off — `driftless/assess/engine.py:is_suppressed`. |

## 4. Positioning verdict

The set splits three ways: **schedulers** (Microsoft Project, OpenProject) that
compute a plan; **work-management surfaces** (Asana, Smartsheet, Jira) that track
what people are doing; and **enterprise PPM** (Planview) that plans capacity and
money across a portfolio. Every one of them is better than driftless at
something a buyer will ask about on the first call — levelling, integrations,
mobile, ecosystem, support, and the plain fact of maturity.

What none of them does is refuse a dishonest status. In all of them, percent
complete and overall health are ultimately **inputs**: a field a person edits, or
a badge a person picks, whatever the underlying work looks like. In driftless
they are **outputs** — the status form has no percent field at all, so the number
cannot be typed low or high (`driftless/assess/percent.py:stamped_percent`); RAG
rolls up worst-child from computed evaluators (`driftless/calc/rollup.py`); an
approved baseline cannot be edited, so plan history is additive by construction
(`driftless/models/delivery.py:Baseline`); every report regenerates
byte-identically from an explicit as-of, never a wall clock
(`driftless/report/engine.py:render_document`); every write is logged with its
actor by a flush listener no write path can skip
(`driftless/db/changelog.py:ChangeLog`); and a signed-off threat re-surfaces the
moment its score regresses. That is the wedge, and it is a wedge only for a
buyer who has to be able to *prove* a figure rather than assert it — an audit, a
regulated or contractual report, a portfolio review where the deck must
reconcile to the system. For a team that just wants to see who is doing what
this week, Asana or Jira is the better answer and it is not close.

Self-hosting is **not** the wedge, and claiming it as one will not survive a
technical evaluator: OpenProject self-hosts, and Jira Data Center self-hosts. It
is a supporting property — data on your hardware, one Postgres store, CSV out of
every list route — rather than a differentiator on its own.

The determinism claim (byte-identical regeneration from a pinned as-of) is
genuinely unusual and is the hardest thing here to copy, because it is a property
of how everything is computed rather than a feature that can be added. It is
also the hardest to *sell*, since nobody arrives asking for it. The honest
framing is the consequence, not the mechanism: last quarter's report still says
what it said, and the number in it can be traced to the rows behind it.

## Sources

**driftless:** this repository, at the `path:line` citations above. Every one is
checkable against the working tree; the process-map and PMBOK boundary claims are
additionally checked by `tests/test_docs_pmbok_mapping.py`, which fails if a
cited symbol moves.

**Competitors:** none. No vendor documentation, pricing page, review site or
analyst report was consulted for this document — the competitor columns are
recall as of the date at the top, which is why unknowns are marked rather than
filled in. Before any of this is quoted outside the business, each competitor
column needs a pass against that vendor's current documentation, and the date at
the top needs to move with it.
