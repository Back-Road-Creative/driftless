# svc-driftless

## Purpose

Business, portfolio, program and project management for Back Road Creative —
built so information is entered **once** and everything else is computed.

There is a single normalized store. Dashboards, rollups and generated
documents are *queries over it*, never stored copies, so they cannot drift out
of step with each other. If a "reconciliation" or "sync check" job ever looks
necessary, the schema is wrong — fix the schema instead.

Two consequences worth knowing before you add anything:

- **Generated documents are never hand-edited.** Any report can be deleted and
  regenerated identically from live data. Human narrative is a first-class
  field on the record (e.g. a project's `status_note`), so it survives
  regeneration.
- **Every report takes an explicit as-of date.** Templates never read the wall
  clock; that is what makes "generate twice, get byte-identical output" a
  property we can test.

## Owner

@joepetjr — see `LIFECYCLE.md` for the service state declaration and review date.

## Status

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
  old one, so plan history is additive by construction.
- **ChangeLog** — an append-only audit trail written by a SQLAlchemy flush
  listener rather than by calls at each write site, so no path that writes
  through a session can skip it. It records table, row id, operation, actor
  and the old/new values that actually moved; `actor` names the signed-in user,
  so a write authorised by the shared `DRIFTLESS_API_TOKEN` stays unattributed.
  Activation is explicit (`register_changelog`); importing the module
  instruments nothing.
- **RAID and money records** — per-project risks, issues, change requests,
  budget lines and dated cost entries; risk exposure is derived, never stored.
- **Org, sign-off and the last knowledge-area records** — departments and
  people (with a `capacity_hours` the Resource maths measures allocation
  against and a `cost_rate` labour cost multiplies by); an append-only
  `sign_off` ledger the threat feed suppresses against (severity-independent
  `subject_ref` plus the `signal` at sign-off, so a regression cannot be
  buried); and `narrative_artifact`, `quality_measurement` and
  `procurement_agreement` records that make the Quality, Procurement and the
  narrative PMBOK inputs first-class. A task names its `assignee` and a project
  its `responsible_department`.
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
  audited on the ChangeLog.
- **Calculation core** — earned value, forecasting and rollups as pure
  functions over plain value objects, wired to stored rows by the dashboard.
- **Web surface** (`driftless/web/`, mounted on the API app) — a server-rendered
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
  track at 0%), a business-wide **process map** (`/process-map`, the same grid rolled up across every project, each cell washed by its share of applicable projects produced-or-better, pooling `state.completeness`'s own exclusion — `driftless/pmbok/rollup.py` — topped by a per-knowledge-area completion ring row pooled the same way, and a click on any cell (`?process={id}`) lists that process's applicable projects with their own state and a link back to each project's own map), a **department surface** (`/org/departments` — the list rendering from the SAME
  `department_rows` the Department Report does; `/org/departments/{id}` drilling into
  one department's accountable projects and each person's capacity through those same
  engines, scoped to that one department), a business-wide **capacity heatmap** (`/org/heatmap`, in the nav — person × week, each cell the hours that person's open, hour-estimated tasks put in that week against their weekly `capacity_hours`. ONE definition of allocation: it imports the Resource evaluator's task filter and its over/tight thresholds rather than restating them, so a row total is what `person_task_loads` returns for the same store; the evaluator has no *when*, so each estimate is spread evenly over the days of the planned window its newest APPROVED baseline line gives it. Every cell prints its hours, and an over or tight one prints that word, so the grid reads in greyscale — hue is never the only carrier. Columns are the as-of's own week and the five after it, never a wall clock, so a pinned as-of regenerates byte-identically. How far ahead is the reader's to set: `?weeks=N` moves the far edge, offered on the page as 4 / 6 / 13 / 26 links that carry the as-of they were rendered with, and reachable at any N in between. Six stays the answer when the parameter is absent, so every address and the nav entry render exactly what they always did. **26 is the ceiling** — half a year, past which an approved baseline plans almost nothing, so the extra columns are zeros bought at the full render price, and that price is the reason for a bound at all: a column is a `<th>` plus one `<td>` per person, so an unbounded `N` is a denial of service written into our own address bar. Out of range is **refused, not clamped**: 0, 27 or 5000 answer the designed 404 page holding no grid, because a caller who asked for a page this one cannot be is owed a refusal — quietly serving six instead is how a horizon nobody asked for gets read as the answer. One constant carries the bound, and `weeks_from` raises on a horizon outside it, so there is no second, looser way in. Hours with no approved window, or one past the horizon in force, are **unplaced** — in the total, claimed by no week, in their own column — so no hour is invented or lost; and a non-positive `capacity_hours` (impossible past `ck_person_capacity_hours`) reads `no capacity` and takes no ratio, never `0%`, where a person with capacity and no work reads `0`. Two queries whatever the store size, and the shared empty state when nobody is assigned anything), a project-independent
  **PMBOK reference** (`/pmbok`, the 49 processes as a stateless knowledge-area ×
  process-group grid straight from the frozen catalog, and `/pmbok/{id}` for one
  process's ITTO detail), an agent-and-human **wizard** page, and a **weekly-status**
  edit form that stamps the computed percent (never typed), draws an inline-SVG
  trend line of percent-complete from the project's append-only StatusSnapshot
  series — with the shared empty state in its place until there are readings, naming
  the form at the foot of the page and `POST /status-snapshots`: the two chart slots
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
  person names a thing by, and only where a hit has a page to link to. Case-insensitive; bounded at
  one statement and 10 hits per kind; the empty query and no-match render the shared empty state.
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
  — same seed, same percentiles.
- **Migrations** — an Alembic chain building the whole schema, proven against
  Postgres 16 and asserted byte-for-byte against the models (CHECK constraints
  included) by the suite.
- **PMBOK ITTO catalog** — a versioned-in-code reference model of all 49 PMBOK-6
  predictive processes across the five process groups and ten knowledge areas,
  each naming its Inputs, Tools & Techniques and Outputs by reference into a
  closed `ARTIFACT_KINDS` / `TT_CATALOG` vocabulary. Property tests pin the
  counts and referential integrity. Query it with `driftless pmbok processes
  [--area A] [--group G]` and `driftless pmbok show <id>`.
- **Process state (computed, never stored)** — `driftless/pmbok/mapping.py` resolves
  each artifact kind to live rows (is a `scope_baseline` present? a
  `status_report` fresh within cadence? an `agreements` disputed?), and
  `driftless/pmbok/state.py` derives each project's state on each of the 49
  processes from those artifacts plus the append-only sign-off ledger:
  not-started → in-progress → produced, or signed-off / waived. There is no
  ProcessInstance table — a tailored-out process is a `SignOff` with decision
  `waived`, so state cannot drift, and completeness excludes waived and
  untrackable processes.
- **Assessment engine (`driftless/assess/`)** — a pure evaluator per knowledge area
  turns calc/records signals into an `Assessment` (risk score, RAG status,
  threats, and recommended actions drawn from the PMBOK tools & techniques):
  Cost (CPI/VAC), Schedule (SPI/slip), Scope (approved-but-unbaselined changes),
  Risk (exposure vs contingency), Stakeholder (disengaged power players),
  Communications (stale reporting), Resource (over-allocation vs capacity),
  Quality (out-of-tolerance/stale), Procurement (disputes/lapses/over-budget),
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
  groups in lifecycle order and, for the next incomplete process the store can
  help with, reports its PMBOK inputs (and whether each exists), its tools &
  techniques, and the outputs it can produce. It is agent-drivable: `driftless
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
- **Demo store** (`driftless/demo/`) — `driftless demo seed --base-url URL [--token T]
  [--anchor YYYY-MM-DD] [--force]` populates a running instance with a small,
  deterministic demo store (2 businesses, a program, 4 projects with a mix of task
  statuses, one clearly-worst risk, one slipped milestone, approved baselines/budget
  lines/cost entries on the **statused three** so the dashboard's S-curve, burn
  sparklines and portfolio treemap render with real shape, and one project with no
  baseline or status data at all) through the same validated API the wizard and
  importer use. A store that already holds rows is **refused** unless `--force` says
  to seed on top of it, so a demo cannot be poured into real data by habit.
  `driftless.demo.data.demo_payload` is a pure builder — every date derives from the
  anchor by a fixed offset, so calling it twice returns an identical structure.

Building on this foundation: the PMBOK ITTO catalog, the per-output assessment
engine, the onboarding wizard and the threat/process web surface. The ITTO
build-out plan those were scoped against lived in the workspace monorepo's
`.data/` and did not come with this repo when it was extracted; there is no
`.data/` here. `CHANGELOG.md` plus the fragments in `changelog.d/` are the
record of what actually shipped.

## Users and roles

Logins live in `app_user` (`driftless/models/auth.py`), apart from `person`: a
user is a credential, not a resource. After `alembic upgrade head`:

```bash
printf '%s' "$ADMIN_PW" | driftless user add --username jp --role admin
driftless user list   # username, role, state, created — never the digest
driftless user disable jp   # deactivate AND revoke every cookie already issued
driftless user enable  jp   # reactivate; the cookies disable revoked stay revoked
```

Roles are `admin`, `contributor`, `viewer`; passwords are stdlib-scrypt digests
read from stdin, never argv (`driftless/auth/passwords.py`). One shorter than **12
characters is refused** before it is hashed or stored (`MIN_PASSWORD_LENGTH`,
`driftless/auth/cli.py`) — lower than the 24 `deploy/entrypoint.sh` demands of a
machine secret, because a person has to remember this one, but not absent: scrypt
only buys time against a stolen digest, and a password short enough to guess is
guessed before the KDF costs anyone anything. `disable` clears
`is_active` **and** increments `app_user.session_epoch`, the counter every cookie
carries a copy of; bumping it is what revokes a session nothing stores (details in
`OPERATIONS.md`, *Revoking a session*). `enable` never lowers it back.

`/login` remembers a user in an HMAC-signed `HttpOnly`, `SameSite=Lax`, `Secure`
cookie (`driftless/auth/sessions.py`) stamped with that epoch, so a revoked cookie
stops resolving without waiting to expire; the form is CSRF-bound and every refusal
reads the same. `DRIFTLESS_SESSION_SECRET` signs it — **unset means nobody can sign
in**, and it warns: unlike `DRIFTLESS_API_TOKEN` (open when unset) this one grants
identity, so falling open would mean forgeable logins. `DRIFTLESS_COOKIE_SECURE=0`
develops over plain HTTP. Five failures for one username from one client inside 15
minutes are answered `429` for the rest of that window (an in-process counter, no
new dependency; a correct password clears it) — keyed on both halves so no one can
lock a colleague out, and counted for absent usernames too so the `429` never
reveals that a login exists. A second cap counts every failure from one client
**whatever username it named**, so cycling usernames no longer buys a fresh five
each time. `POST /logout` **revokes as well**: it bumps the epoch,
so signing out ends the session on every device, not just this browser.

A signed-out browser is **sent to that form**: the gate answers `303 /login` when a
request presented no credential at all *and* its address is one of the app's page
routes. Everything else keeps `401 {"detail":"missing or invalid bearer token"}` byte
for byte — the JSON API, `/health/ready`, and every request that *did* present
something and was rejected (a wrong token, a forged cookie, a cookie `user disable`
revoked), because a form cannot fix a bad credential and a disabled account redirected
to one would loop. Ordinary expiry still lands on the form: the cookie's `max-age` is
the session TTL, so the browser has dropped it before the signature goes stale. The
target is the fixed string `/login` — no `?next=`, which would be an open redirect.

**API tokens** are the non-browser half of the same identity — one per user, per holder,
so an agent's writes carry a name rather than the shared `DRIFTLESS_API_TOKEN`'s anonymity:

```bash
driftless token add --username jp --label ci  # printed ONCE, to stdout alone
driftless token list      # id, user, label, live/revoked, created — never the digest
driftless token revoke 3  # by the id `list` prints
```

`user add` first — a token belongs to a login. Only a SHA-256 digest is stored
(`api_token`, `driftless/auth/tokens.py`), so a lost token is re-minted, never
recovered; not scrypt, because 256 bits of `secrets` randomness needs no slow KDF.
Both revocations bite: `token revoke` stops that one, `user disable` stops every token
its owner holds, because resolving reads the owner's row back. Present it as
`Authorization: Bearer dfl_…`: the gate resolves it to the **same** `Principal` a cookie
yields, so the role table below and the per-user audit actor apply to it unchanged.

**What a role may do** is enforced in exactly one place — `TokenGate` in
`driftless/api/secure.py`, not per route, so a write route added later is gated
whether or not anyone remembers to ask:

| Role | Reads (`GET`, `HEAD`, `OPTIONS`) | Writes (`POST`, `PUT`, `PATCH`, `DELETE`, anything else) |
|---|---|---|
| `admin` | yes | yes |
| `contributor` | yes | yes |
| `viewer` | yes — every surface | **403 before the route runs**, so no row is ever written |

The split is by method, never by path, and a method outside the read set counts as a
write: unknown fails closed. The role check runs **after** `/health`, `/static…`,
`/login` and `/logout` are decided, so a viewer can always sign in, sign out and load
the CSS. A request carrying only the shared `DRIFTLESS_API_TOKEN` resolves no user and
is therefore *not* role-gated — that token is the bootstrap/admin credential. A
signed-in viewer is refused even with no token configured; no credential and no token
stays open, as in development today. `tests/test_secure.py` pins both the method set
and that ordering.

Every web form POST is CSRF-bound the same way, minted and checked in one place
(`driftless/web/csrf.py`): a random token into a hidden `csrf_token` field and into
the `driftless_csrf` cookie, both required back, compared constant-time. It covers
`POST /sign-off`, `POST /projects/{id}/wizard/apply` and `POST /projects/{id}/status`
— unpaired is refused **403 before any read or write** — and the token is reused
from the cookie the browser holds, so two tabs never invalidate each other. **Signing
out is bound too**, because it revokes every device — and no router has to remember: all
seven render through the one `Jinja2Templates` in `driftless/web/templating.py`, whose
context processor puts the token in every context and whose `TemplateResponse` attaches
the cookie half, so the sign-out form in every nav carries a pair. That one environment
is also **strict** (`undefined=StrictUndefined`, the same setting `report/engine.py`
carries): a name no route passed — a misspelt `{{ as_off }}`, a field only an
empty-state branch mentions — raises at render time instead of printing the empty
string, so a figure cannot quietly leave a page while the page still answers 200.
A body not matching the cookie half is a forgery on a live pair: **403
before the store**; a POST carrying no `driftless_csrf` cookie was never handed a pair
and gets only the half that grants an attacker nothing — its own cookie dropped, **no
epoch bump**. `tests/test_web_csrf.py` walks the real app, so a POST with no check, a
form with no field, or a page rendering no token, fails there.

The pair is required **only where forgery is possible**: a cookie is *ambient* — a browser
attaches it to whatever another origin causes — while a bearer token is attached
deliberately and no cross-origin page can make a browser send one. So the gate stamps which
credential authenticated the request, and `POST /projects/{id}/wizard/apply` skips the pair
for a bearer one. That is what lets an agent drive the wizard loop end to end
(`docs/agent-guide.md`); the other two form POSTs already have JSON API routes
(`/sign-offs`, `/status-snapshots`) and keep the pair either way. A cookie **wins when both
arrive**, so a browser that also sends a header still pairs — otherwise one added header
would bypass CSRF — and role gating is untouched: a viewer's token is refused the write.

## Releases

`CHANGELOG.md` is the record of what shipped, in Keep-a-Changelog shape. Every
user-visible change ships its entry **in the same PR** as the change — never
"later", because an entry written from memory is written wrong — but as a
fragment file `changelog.d/<PR#>.<type>.md` (see `changelog.d/README.md`), never
as a direct edit to `CHANGELOG.md`, so two open PRs cannot collide on the same
changelog lines. At release time `bin/assemble-changelog.py --release <version>`
folds the fragments into `CHANGELOG.md` under the new version heading and
deletes them. That is the whole of what the tool does: the version it stamps is
read off the argument, so `pyproject.toml` and `driftless/__init__.py` are the
files that decide it and are bumped by hand before the fold. Once the fold has
merged, tag the merge commit `v<version>` — the changelog says what shipped and
the tag says which commit it shipped from, and a release with only one of the two
cannot be checked out. Pushing that tag is also what publishes the release:
`.github/workflows/release.yml` reads the dated section for that version out of
`CHANGELOG.md` and creates the GitHub release from it, failing without publishing
anything if there is no such section. `OPERATIONS.md` covers upgrading a running
deployment (back up, pull, rebuild; the container migrates before it serves) and
the request log.

## Exit Condition

This service is retired when Back Road Creative no longer runs its portfolio,
program and project management from it — either because the business stops
needing centralized PM, or because the store is migrated to a replacement that
takes over the same single-source-of-truth role. Until then it stays ACTIVE;
there is no fixed end date.

## Layout

| Path | What lives there |
|---|---|
| `driftless/` | The service package |
| `driftless/cli.py` | The `driftless` command — dispatches `report`, `pmbok`, `assess`, `wizard` and `demo`, each registered by its own domain |
| `driftless/api/` | FastAPI app and the Pydantic schemas that validate every write |
| `driftless/demo/` | `driftless demo seed` — a deterministic demo store through the validated API |
| `driftless/calc/` | Pure calculation core — EVM, rollups, forecasts. No I/O. |
| `driftless/db/` | Declarative base, engines, sessions, SQLite FK pragma, and the ChangeLog audit trail (`changelog.py`) |
| `driftless/models/` | ORM models — `hierarchy.py` (business → … → task), `delivery.py` (baselines, milestones, sprints), `records.py` (RAID + cost), `people.py` (departments, people), `governance.py` (`sign_off`), and `narrative.py` / `quality.py` / `procurement.py` |
| `driftless/web/` | Server-rendered dashboard — a router plus Jinja2 templates. Each project row carries a small inline-SVG burn sparkline: cumulative actual cost `AC(t)` climbing against the flat budget `BAC`, swept in-memory from one grouped cost query (drift-free, stores nothing new), plus a **status-freshness** column showing the date of each project's most recent `StatusSnapshot` (or `never`), from one grouped max query — no N+1 |
| `tests/` | Test suite |

`driftless/calc/` is imported by both the dashboard and the report engine, which
is why a number on a screen and the same number in a document cannot disagree.

## Development

A clone builds its own venv — none is committed:

```bash
python3 -m venv .venv
.venv/bin/pip install ".[dev]"
.venv/bin/python -m pytest
```

Invoke through `python -m` rather than the console scripts in the venv's `bin/`:
a venv that has been moved or copied leaves their shebangs pointing at a path
that no longer exists and they exit 127, which reads like a missing dependency
and is not one.

Keeping the venv **outside** the checkout is a supported second setup, and the
right one wherever this repo is mounted inside a larger tree as a submodule — a
venv inside it does not survive the parent's next `submodule update --init`.
There is then no `.venv/` here to find, and every `.venv/bin/…` line in this
README reads as that interpreter's own path instead.

### Continuous integration

CI enforces ruff (lint + format), mypy in strict mode, detect-secrets,
pip-audit, and the coverage floor `pyproject.toml` sets in
`[tool.pytest.ini_options] addopts` — read `--cov-fail-under` there rather than
here, which is how this line came to name a floor CI had already left behind.
Runtime dependencies are declared by the phase that first imports them, so an
unused dependency never becomes CVE surface.

Three workflows, on pull requests to `master` plus a nightly re-validation of
`master` (there is no per-merge push trigger — the pull-request gate is the gate,
and the nightly bounds post-merge drift at 24h):

| Workflow | Runs when | What it does |
|---|---|---|
| `.github/workflows/ci.yml` | every PR, nightly, manual | **Quality** (ruff, detect-secrets, mypy strict), **Tests**, and **Migrations** — the alembic chain run against a real Postgres service container, so the schema is proven where it ships and not only on SQLite — as three independent jobs, none waiting on another |
| `.github/workflows/pip-audit.yml` | PRs that touch `pyproject.toml`, `requirements.lock` or `.pip-audit-ignore`; nightly; manual | audits a clean venv holding exactly the shipped dependency set |
| `.github/workflows/scheduled-failure-alert.yml` | called by the two above, on a failed **scheduled** run | opens one deduped GitHub issue and comments on it thereafter |

Every job runs on a **GitHub-hosted** runner, and that is a security property
rather than a preference: a pull request is code anyone may submit, and a
self-hosted runner would execute it on a machine the maintainer owns.
`tests/test_deploy_hardening.py` fails the suite if a job started by an untrusted
event names `self-hosted` again.

The suite runs under `pytest -n auto` (pytest-xdist), which takes the runner's own
core count. It is xdist-safe as a property of the suite, not an assumption: every
test builds its own store, and the serial and parallel runs are checked to give
the same count at the same coverage.

`requirements.lock` is the resolved version of every dependency, used by both the
Tests job and the audit as a **constraint** file — pyproject.toml still decides
*what* is installed, the lock decides *which version*. Without it the two jobs and
the Docker image each resolved "latest" independently, so a green audit was not a
statement about the shipped image. Regenerate it whenever a dependency changes;
the command is in the file's own header. Dependabot does not maintain it (see
`.github/dependabot.yml`), so a dependency bump has to carry the regenerated lock
in the same pull request.

**Merging.** A pull request lands only on a **complete green** CI run — red,
pending and incomplete all refuse, and nothing merges an unfinished run. Merging
is a human decision: no workflow and no bot here merges anything, which is also
why `.github/dependabot.yml` configures no automerge.

### Page snapshots

`bin/driftless-snapshot-pages.py` writes every page the app serves to
`docs/page-snapshots/` as rendered HTML — one file per page it finds, from the
demo store seeded through the validated API at a pinned `--anchor`. How many that
is moves whenever a page is mounted, so the count is not written down here. Every chart is inline
SVG rendered server-side and nothing renders in the browser, so the response is
the whole visual truth and no headless browser is involved. The page list is
discovered from the router, so a page mounted tomorrow is captured without anyone
editing a list. The bundle is regenerable output like `reports/` — git-ignored,
never committed — and it regenerates byte-identically:
`tests/test_page_snapshot_bundle.py` runs the generator twice and fails on any
byte that moves, which is what lets a design review diff one bundle against the
next and see only what the design changed. Regenerating means clearing the
directory first, so `--out` is **refused** unless the directory is empty or
carries the `.driftless-page-snapshots` marker the tool writes there — `--out
docs` or `--out .` can no longer glob away HTML it did not create. A
`docs/page-snapshots/` left from before that change carries no marker: delete it
once, and the tool manages it normally from then on.

```bash
.venv/bin/python bin/driftless-snapshot-pages.py --anchor 2026-07-01
```

### Performance floor

The release gate on page performance is a **statement count, never a wall-clock
budget**. How many SQL statements a page issues is a property of the code;
milliseconds are a property of whichever machine ran the suite — and in-process
SQLite hides the per-statement round trip a networked Postgres charges, so a
green stopwatch there proves nothing about production.

The floor is therefore *invariance in the row count*: the same page rendered
over a commercial-volume store (5 portfolios, 6 projects, 300 tasks, 300
baseline lines, 60 risks) must issue **exactly** the number of statements it
issues over a store a tenth the size. Both stores share one topology and one set
of aggregate signals — only the row counts differ — so the expected difference
is zero and any extra statement is a per-row query, i.e. an N+1. The measured
counts are deliberately **not** restated here: one moves whenever an honest read
lands, so a number retyped into prose is stale within the week — this paragraph
claimed counts several times the ceilings CI was enforcing. The ceilings are
stated, because a ceiling is a decision rather than a reading, and each is
derived from a measurement the suite re-takes on every run: `/` 132,
`/process-map` 19, `/threats` 56
(`MAX_HOME_STMTS`, `MAX_BUSINESS_MAP_STMTS`, `MAX_THREATS_STMTS` in
`tests/test_perf_commercial_volume.py`). `tests/test_docs_numbers_are_measured.py`
reads those three constants and checks this sentence against them, so moving a
ceiling edits this line in the same commit. A regression that inflates both
volumes equally still fails, and each page must render seeded content (not an
empty state) to count. Cost per *project* is a different, bounded thing with its
own ceilings in `tests/test_perf_n1.py`.

```bash
.venv/bin/python -m pytest tests/test_perf_commercial_volume.py tests/test_perf_n1.py
```

### Accessibility floor

Every rendered page is usable by keyboard and screen reader: one `<h1>` and a
`lang`, a skip link ahead of the nav with a focus ring nothing removes,
`aria-current` on the active nav link, a programmatic name on every control (a
placeholder is not a label), `<th scope>` plus a caption on every data table, and
status never on colour alone. `tests/test_web_a11y.py` enforces both halves: it
*computes* the WCAG contrast ratio of every text token pair in `base.html`, light
set and dark, and walks every GET page the app registers — so a page added later
is checked the day it is mounted, and a token with no dark twin fails.

A walk is worth only what it renders, so the fixture behind it is asserted
non-empty: every page it requests must come back with seeded content, and the
pages empty **by design** are pinned as an exact set (`EMPTY_BY_DESIGN`,
currently empty), so a page that quietly goes blank fails rather than passes.
`/org/heatmap` and `/search` were being walked on their empty states — nobody
assigned an hour-estimated task, and no search term — which left every rule both
walks apply passing on markup that held nothing; the fixture now assigns the
seeded task in hours to a person with capacity and carries a matching `q` on
every request. The weekly-status trend was the quietest case of the same hole and
invisible to that assertion: its empty branch carried no `empty-state` class, so the
page never read as blank while the chart's own markup — line, axis ends, table twin —
had never been walked once. The fixture seeds two dated snapshots a quarter apart, so
it is. `tests/test_web_responsive.py` walks the same pages through the
same helper, so its twelve wrapped tables are covered by the same assertion.

That ratio gate is **total**, because the palette is closed. `base.html`'s two
`:root` blocks are the only place in `driftless/web/templates/` where a colour
literal may be written — every other template says `var(--token)`, and the gate
fails any file that spells a hex or an `rgb()`, naming the file and the literal.
A second check pairs the two: every declared token must carry a contrast floor
(4.5:1 text, 3:1 for the focus ring and for a chart line the legend names) or sit
in an explicit `DECORATIVE` list. So a colour cannot reach a page without a
computed ratio, and cannot be tokenised out of the gate's reach either. This
closed two defects page-local hexes had hidden: chart labels and the PV line at
3.54:1 in light mode, and tile labels at 3.18:1 in dark mode — both page-local
colours with no dark twin.

`base.html` owns the shared *shape* on the same terms it owns the palette:
layout (`tests/test_web_responsive.py` fails a page-local `<style>` declaring
`display:flex/grid`, `flex`, `overflow` or a `min-`/`max-width`) and, since that
gate reaches containment only, the rollup table's alignment and indents as
`.rollup`. The dashboard and the portfolio/program drill render the same rollup,
so they apply that one class rather than keeping a copy of the rules each — the
drill page now carries no `<style>` at all.

### Responsive floor

The surface holds together down to a tablet on **one** width breakpoint —
`@media (max-width: 60rem)`, 960px, declared once in `base.html` and argued
there. That width was measured off the dashboard's own content rather than
picked off a device list: the command split is 36rem of heatmap + 18rem of rail
+ a 1.5rem gap = 55.5rem, which stops fitting inside the 2rem body gutters at
59.5rem of viewport, so 60rem is where the desktop reading genuinely ends. A
landscape tablet (1024px) still gets the two-column desktop layout; a portrait
one (768px) gets the wrapped layout, with the gutters narrowed and reclaimed for
content. A second breakpoint would need its own argument; the test pins there
being one.

Below it every wide surface has an answer, and **none of them is hiding
something**. A table too wide for the viewport scrolls sideways instead of
clipping (`.scroll-x` — a table narrower than the box still fills it, so the
desktop rendering is untouched, while a wider one keeps readable columns and
moves). The flex rows wrap rather than clip: board columns break to the next
line, a card still reading at 12rem, and so do the KPI tiles, the chart pair and
the command split. The inline-SVG charts scale on their `viewBox`, and their
figures stay text at any width — the Gantt repeats every bar and mark as a row
of the table beneath it, the curves print their own end figures. Dropping a
column is how someone ends up deciding without the number that mattered, so no
width drops one.

A scroll box is written one way and one way only — `_scroll.html`'s
`wide(label)` macro — so it always carries `tabindex="0"` (a keyboard can scroll
it) and a named `role="region"` (a reader announces both that it scrolls and
which surface it holds). Mouse-only is not something review has to catch,
because it cannot be written.

**What the tests prove is structure, not appearance.**
`tests/test_web_responsive.py` walks every GET page the app registers for the
viewport meta tag (without it a tablet renders at a lied-about ~980px and every
breakpoint below is inert) and for every `<table>` sitting in a scroll container
that takes focus and carries a name; statically, it pins exactly one width
breakpoint and no page-local re-declaration of a layout property. No test here
renders a viewport, so column widths, where the flex rows choose to wrap,
whether a scrolled table reads well under a thumb, and whether the Gantt's bars
stay legible once the SVG scales are **eye checks nothing covers**.
