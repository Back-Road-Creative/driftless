# driftless — Competitor Analysis

**As of 2026-08-02.** The driftless side of every row below cites this repo at
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
| Percent complete computed from evidence, not typeable | ✓ the create body has no percent field; the route stamps it from calc — `driftless/api/schemas.py:494`, `driftless/api/app.py:918 stamped_percent` | — editable field | — a cell someone types | ~ rolls up from issues; the summary colour is still chosen | ~ rolls up from tasks; the on-track badge is chosen | ? | ~ a field; newer versions can derive it |
| Overall health (RAG) derived, not declared | ✓ worst-child-wins over computed evaluators — `driftless/calc/rollup.py`, `driftless/assess/engine.py` | — | — | — | — status is picked in the update form | ? | — |
| Plan history additive — approved baseline frozen, re-baseline inserts a version | ✓ `(project_id, version)` unique, writes to an approved baseline refused — `driftless/models/delivery.py:46` | ~ up to 11 baseline slots, overwritable | ~ baseline start/finish variance | ? saved plans / scenarios | — | ? | ? baseline comparison view |
| Earned value (EV, CPI, SPI, EAC) off a time-phased baseline | ✓ `driftless/calc/evm.py`, `driftless/report/documents/cost_evm.py` | ✓ built-in EVM fields | — build it in formulas | — | — | ? financial planning; EVM unverified | — budgets and cost reporting, not EVM |
| Generated documents regenerate byte-identically from an explicit as-of | ✓ `driftless/report/engine.py:54`, proven by `tests/test_report_engine.py:22` | ? | ? | ? | ? | ? | ? |
| No wall clock anywhere in a rendered surface | ✓ every page and report takes `?as_of=`; the Gantt's "today" is the as-of — `driftless/web/gantt.py`, `docs/user-guide.md:43` | ? | ? | ? | ? | ? | ? |
| Portfolio → program → project rollup | ✓ one `gather` walk behind dashboard and drill alike — `driftless/calc/rollup.py`, `driftless/web/drills.py` | ~ per-plan on desktop; portfolio in the hosted tiers | ~ portfolio dashboards, higher tier | ~ Advanced Roadmaps (Premium) | ✓ Portfolios and Goals | ✓ core | ~ project hierarchy |
| PMBOK 49-process map with computed per-project state | ✓ no ProcessInstance table; state derived from artifacts + sign-offs — `driftless/pmbok/catalog.py`, `driftless/pmbok/state.py:145` | — | — | — | — | ? methodology templates | — |
| Append-only audit of every write, with the actor | ✓ a flush listener no write path can skip — `driftless/db/changelog.py` | ? | ~ cell history and activity log | ✓ issue history and audit log | ~ activity feed; audit API on the top tier | ? | ✓ work-package journals |
| A signed-off problem re-surfaces if it gets worse | ✓ suppression holds only while the live score stays no worse than at sign-off — `driftless/assess/engine.py:131 is_suppressed` | — | — | — | — | ? | — |
| Dependencies, critical path, schedule computation | — records an approved plan, never builds one — `docs/pmbok-mapping.md:133` | ✓ strongest in this set | ✓ dependencies and critical path | ~ dependencies, no CPM | ~ dependencies, no CPM | ~ | ~ dependencies and Gantt |
| Resource levelling | ~ names who is over capacity, never moves the work — `driftless/web/heatmap.py` | ✓ | ~ Resource Management add-on | ~ capacity in Advanced Roadmaps | ~ Workload | ✓ capacity planning is core | ~ |
| Runs entirely on hardware you control | ✓ two containers, loopback by default — `docker-compose.yml`, `OPERATIONS.md` | ~ desktop files; Project for the web is hosted | — hosted only | ~ Data Center self-hosts | — hosted only | ? | ✓ self-hostable community edition |
| Third-party integrations, notifications, mobile apps | — none: no email, webhook or mobile path exists; one outbound iCal feed — `driftless/api/calendar.py` | ✓ | ✓ | ✓ large marketplace | ✓ | ✓ | ✓ |
| Attachments, comments, discussion on a record | — no such table; narrative is a field on the record | ✓ | ✓ | ✓ | ✓ | ? | ✓ |
| Bulk CSV in and out through the validated write path | ✓ import posts through the API, every list route answers `?format=csv` — `bin/driftless-import.py`, `driftless/api/export.py` | ✓ | ✓ | ✓ | ✓ | ? | ✓ |
| Drivable end to end by an agent through one validated boundary | ✓ `driftless wizard apply` writes through the same API as the UI — `driftless/wizard/`, `docs/agent-guide.md` | ~ REST API | ~ REST API | ~ REST API | ~ REST API | ~ REST API | ~ REST API |

Two rows are `?` across the board — byte-identical regeneration and no-wall-clock.
Not one of these vendors states either as a product property, so there is nothing
to cite; that is not the same as having verified they lack it, and it is written
as `?` rather than `—` for that reason.

## 2. Gap register

Everything a competitor has that driftless does not, with the decision. No
silent gaps.

| Gap (who has it) | Decision |
|---|---|
| Schedule computation — dependencies, critical path, float (MSP, Smartsheet, OpenProject) | **Boundary, stated** (`docs/pmbok-mapping.md:133`). driftless measures against an approved plan; it does not build one. This is the largest single gap and the one most likely to end an evaluation. |
| Resource levelling (MSP, Planview) | **Boundary.** The heatmap names the over-allocated person and week; a human moves the work. |
| Integrations, notifications, email (everyone) | **Absent, open.** No email or webhook path exists at all — the iCal feed is the only outbound surface. A team that expects a message when something slips will not get one. |
| Mobile apps (everyone) | **Absent.** The surface reflows to a tablet on one breakpoint (`tests/test_web_responsive.py`); there is no native app and no offline mode. |
| Attachments, comments, threaded discussion (everyone) | **Absent.** Human narrative is a first-class field on the record so it survives regeneration; conversation lives wherever the team already talks. |
| Ecosystem — marketplace, templates, connectors, trained contractors (Jira, Smartsheet, Asana, MSP) | **Not a target,** and not something a single service can answer. |
| Support, SLAs, training, certification (every commercial product here) | **Absent.** There is no support organisation. |
| Multi-tenant hosted service (all but OpenProject) | **Not built.** One instance, one organisation. |
| WBS, requirements traceability, deliverable acceptance, closeout documents | **Boundaries, each stated with the artifact kinds it would have produced** — `docs/pmbok-mapping.md:131`, `:132`, `:142`, `:143`. |
| Maturity — years of production use across many organisations (all of them) | **Real, and not closable by a feature.** driftless runs one business's portfolio (`README.md`, *Exit Condition*). |

## 3. Pain-point register

Complaints commonly made about tools in this class. **These are not sourced
here** — no review corpus was read for this document, so read the left column as
a hypothesis to test with a real prospect, not as a citation. The right column
is grounded and checkable.

| Complaint | The structural answer |
|---|---|
| "Status is whatever the PM types the night before the steering meeting." | The status form has no percent field; the route stamps it from calc at the snapshot's own date — `driftless/api/app.py:918`, `docs/user-guide.md:102`. |
| "The plan got quietly rebaselined and the original is gone." | An approved baseline is frozen and re-baselining inserts a new version; both are schema-level — `driftless/models/delivery.py:46`. |
| "The dashboard and the board deck disagree." | One store; every figure is a query over it, and `driftless/calc/` is imported by both the web surface and the report engine, so a number on a screen and the same number in a document share one implementation. |
| "Nobody can say who changed that number." | Every write through a session is logged with actor and the values that moved, by a flush listener rather than by calls at each write site — `driftless/db/changelog.py`. |
| "Re-run last month's report and the numbers have moved." | The as-of is threaded explicitly and nothing reads a clock; identical regeneration is a test, not an intention — `tests/test_report_engine.py:22`. |
| "Our portfolio data lives in a vendor's cloud and leaving is a project." | It runs on your own hardware, the store is Postgres, and every list route exports CSV — `docker-compose.yml`, `driftless/api/export.py`. |
| "A process was tailored out and now nobody remembers it existed." | A waiver is a signed row in an append-only ledger, and completeness excludes it explicitly — `driftless/pmbok/state.py`. |
| "That risk was signed off and then quietly got worse." | Suppression holds only while the score stays no worse than it was at sign-off — `driftless/assess/engine.py:131`. |

## 4. Positioning verdict

The set splits three ways: **schedulers** (Microsoft Project, OpenProject) that
compute a plan; **work-management surfaces** (Asana, Smartsheet, Jira) that track
what people are doing; and **enterprise PPM** (Planview) that plans capacity and
money across a portfolio. Every one of them is better than driftless at
something a buyer will ask about on the first call — scheduling, levelling,
integrations, mobile, ecosystem, support, and the plain fact of maturity.

What none of them does is refuse a dishonest status. In all of them, percent
complete and overall health are ultimately **inputs**: a field a person edits, or
a badge a person picks, whatever the underlying work looks like. In driftless
they are **outputs** — the status form has no percent field at all, so the number
cannot be typed low or high; RAG rolls up worst-child from computed evaluators;
an approved baseline cannot be edited, so plan history is additive by
construction; and a signed-off threat re-surfaces the moment its score regresses.
That is the wedge, and it is a wedge only for a buyer who has to be able to
*prove* a figure rather than assert it — an audit, a regulated or contractual
report, a portfolio review where the deck must reconcile to the system. For a
team that just wants to see who is doing what this week, Asana or Jira is the
better answer and it is not close.

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
