# Changelog

All notable, user-visible changes to svc-driftless, newest first. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the version
is the one in `pyproject.toml` / `driftless.__version__`.

Every user-visible change still ships its entry **in the same PR** that makes
the change — an entry written later is an entry written from memory — but as a
fragment file in [`changelog.d/`](changelog.d/README.md), never as a direct edit
here: two open PRs appending to the same list collide on the same lines, two
fragment files cannot. `bin/assemble-changelog.py --release <version>` folds the
fragments into this file at release time.

## [Unreleased]

## [0.2.0] - 2026-08-02

### Added
- **A pushed version tag publishes the release notes the changelog already holds.** `v0.1.0` was
  tagged on 2026-07-31 and no GitHub release object ever appeared: every workflow here started on a
  pull request, a schedule, a dispatch or a workflow_call, so a tag started nothing and publishing
  was a manual step nobody took — the changelog said what shipped and the one place a reader looks
  said nothing. `.github/workflows/release.yml` now runs on `v[0-9]+.[0-9]+.[0-9]+`, reads the dated
  `## [x.y.z] - YYYY-MM-DD` section for that version out of `CHANGELOG.md`, and creates the release
  from it with the workflow's own `GITHUB_TOKEN` (`contents: write`, job-scoped; no secret added).
  The notes are read rather than re-assembled because the fragments are already folded and deleted
  by tag time. A tag whose version has no section — or whose section is empty — fails the run and
  writes no notes file, so an empty release cannot be published;
  `tests/test_release_workflow.py` runs that failure, not just the success.

### Security
- **The image installs only distributions whose sha256 this repo committed.** `requirements.lock`
  pinned exact versions, which decides which release the build asks for and says nothing about
  what the index returned; the build then `chmod`ed and ran whatever arrived. The runtime closure
  is now compiled into `requirements-runtime.txt` with a hash per distribution and installed
  `--require-hashes`, so a substituted artefact fails the build instead of shipping. The checkout
  itself installs on a second line with `--no-deps` — pip refuses to hash-verify a directory, and
  without `--no-deps` that line would re-resolve every dependency from the index unhashed and undo
  the first. The new file is compiled under `-c requirements.lock`, so the image, the Tests job and
  pip-audit stay on one version set, and `tests/test_image_dependency_parity.py` fails if they
  drift, if a pin loses its digest, or if the compiled-from name list stops matching
  `[project.dependencies]` plus uvicorn.

## [0.1.0] - 2026-07-31

The first deployable shape of the service:

- **One normalized store** — business → portfolio → program → project →
  workstream → task, plus per-project delivery, RAID, cost, org, sign-off,
  narrative, quality and procurement records, built by an Alembic chain that the
  suite asserts against the models.
- **One validated write path** — a FastAPI CRUD boundary enforcing the
  cross-row rules (parent scoping, approved-baseline freeze, unit/mode
  agreement, no orphaning delete), with every write recorded on the append-only
  ChangeLog.
- **Computed views, nothing stored twice** — the pure calc core (EVM, rollups,
  forecast incl. seeded Monte Carlo), the PMBOK 49-process catalog with derived
  process state, and the assessment engine's ranked attention feed.
- **Server-rendered web surface** — command center, threat board, process maps,
  department, portfolio/program drill and project-hub pages, the wizard and the
  weekly-status form, behind a bearer-token gate with `/health` open.
- **Generated reports** — `driftless report all` from an explicit as-of,
  byte-identical on regeneration, plus the Docker/SOPS deployment with
  restore-verified backups and an API-based import path.

The sections below are every change that landed before the stamp — the audit
campaign that hardened the shape above into a releasable one.

### Added
- **`docs/user-guide.md` — the guide for the person using the product**, the last audience with no
  document of its own: signing in, what each screen answers, filing a weekly status, reading
  RAG/EV/CPI/SPI (why `n/a` is never a zero), CSV and calendar exports, and what to do when a figure
  looks wrong. `tests/test_docs_user_guide.py` opens every address in it as a real signed-in browser
  — form, CSRF pair, cookie, no header — against the demo store, so a label that stops being true fails there.

- **The dashboard's cost S-curve carries its shape as text.** The SVG's `aria-label` named the
  endpoint pair and the two in-SVG end labels repeated it; everything between — where actual crossed
  planned, and how far above or below it sat at each sample — was reachable by eye alone. That is the
  argument that earned the Gantt its table twin, so this is the same answer in the same idiom: every
  plotted point becomes one row (sampled date, planned total, actual total) in plot order, under an
  `sr-only` caption, in the shared `scroll.wide` box. No arithmetic lands in the template —
  `report.gather.business_curve` already computed each sample's date to take the sample and threw it
  away, and now keeps it, so re-deriving the window in Jinja never becomes a second copy of
  `sample_dates` free to drift from the first. No baseline anywhere still means no points, so chart
  and table are absent together, never an empty table under a caption promising rows.

- **`docs/pmbok-mapping.md` — which PMBOK practices this tool implements, and which it deliberately
  does not.** The boundary a PMP-trained reader needs first lived only in reviewers' heads. It is now
  three tables: a vocabulary map (PMBOK's *work performance report* is this tool's *status snapshot*),
  the supported practices each naming the code behind it as `path:line symbol`, and the non-goals —
  WBS decomposition, requirements traceability, activity sequencing and critical path, resource
  levelling, estimating ranges, TCPI, subsidiary management plans, solicitation, closeout — each
  naming the artifact kinds it would have produced. `tests/test_docs_pmbok_mapping.py` makes it
  checked rather than merely written: every citation must resolve to that symbol at that line, the
  counts must be the live catalog's own, and a kind listed as absent that starts resolving turns the
  suite red until the document says so.

**Entered late**, both of the above: they shipped with no line here and are written off the source and
the tests as they stand, not from memory. They sit below the user guide because they landed before it.

- **Milestones and sprints as a calendar anyone can subscribe to** — `GET /calendar.ics` (the whole
  store) and `GET /projects/{id}/calendar.ics` (one project) serve RFC 5545 iCalendar, so dates that
  until now could only be read inside the product land in Outlook, Google or Apple Calendar. All-day
  events, each `UID` off the row's own key so a rename updates rather than duplicates, no clock read
  anywhere, and a hand-written escaper/folder rather than a new dependency.

- **The surface holds together down to a tablet.** Every wide surface — the RAG rollup, the
  person × week capacity grid, the PMBOK and process grids, the Gantt's text twin — assumed a
  desktop viewport and overflowed the page below it. There is now **one** width breakpoint,
  `@media (max-width: 60rem)` (960px), argued in `base.html`'s own comment rather than named after
  a device: the dashboard's command split is 36rem of heatmap + 18rem of rail + a 1.5rem gap =
  55.5rem, which stops fitting inside the 2rem body gutters at 59.5rem of viewport. Below it the
  gutters narrow and the SVG charts scale on their viewBox; the flex rows wrap at every width, so
  board columns wrap (a card still reads at 12rem) and a too-wide table scrolls sideways instead of
  clipping. Nothing is hidden or dropped at any width — a manager on a tablet must not decide
  without the column that mattered. `_scroll.html` is the only way a scroll box is written, so
  every one carries `tabindex="0"` and a named `role="region"`: the affordance cannot be mouse-only
  by construction rather than by review. Layout moved out of the page-local `<style>` blocks and
  `style=` attributes into `base.html`, so home.html and drill.html can no longer lay the same
  rollup out differently. `tests/test_web_responsive.py` walks the real routes for the viewport
  meta tag and for every table sitting in a reachable, named scroll container, and pins the
  breakpoint at exactly one; its docstring states what it does not prove — nothing here renders a
  viewport, so how it *looks* at 768px is still an eye check. **Entered late**: this shipped with
  no line here, so it is written off that source and that test as they stand, not from memory of
  what was intended. It sits below the calendar entry because it landed just before it, and moving
  it to the top would say it shipped last.

- **The demo store now shows every surface with something real on it.** Walking the seeded store
  page by page found what a screenshot would have: no task carried a percent complete, so EV, CPI
  and SPI read `0.00` and EAC `n/a` on *every* project — a portfolio that had spent money and
  delivered nothing — and every RAG token on the dashboard was `red` in consequence. Both department
  pages were empty (no project named a department), no task had an assignee, RAID read `0` issues
  and `0` changes everywhere, and three of four milestone statuses and three of four risk statuses
  never appeared. The seeder now carries task progress, assignees, department ownership, RAID and
  quality rows and a fourth project, so the statused three read one red, one amber, one green
  against the deliberate no-data one. Same door as before: every row posts through the validated
  API and every date hangs off `--anchor`, no clock read. `tests/test_demo_web.py` pins it by
  rendering every page and reading the vocabularies off the model's own tuples. 70 rows, not 44.

- **A task board at `/projects/{id}/board`** — `Task.status` has always been a closed vocabulary
  and no view laid a project's work out by it. The columns ARE that vocabulary, not a list written
  into the page, so a status added to the model becomes a column with nobody editing markup (the
  test asserts the rendered set against the tuple, never against four names). A card carries
  workstream, assignee, percent and estimate; dates stay on the schedule and money on the hub. Every
  card prints its status as text, so **blocked** reads as blocked in greyscale. An empty column says
  which one it is, a project with no tasks renders the shared empty state, and the whole board is two
  statements at any task count. Linked from the project hub, beside Schedule.

- **`docs/admin-guide.md` — bare host to trusted instance in one walk**, which until now meant
  assembling `OPERATIONS.md`, `deploy/` and `bin/` in the right order: install, two users and their
  roles, per-user credentials, demo data, the readiness answers for a store current, behind and
  ahead, a verified backup, and rollback written as what it is — *restore the pre-upgrade dump*,
  since an image older than the applied migration refuses to start. `tests/test_docs_admin_guide.py`
  executes its blocks against a real app; the three no unit test can run (a host, TLS, `pg_dump`) are
  marked `manual` with **why**, counted rather than faked, and an unmarked fence still fails.

- **An agent can now drive the wizard's write side with its own token.**
  `POST /projects/{id}/wizard/apply` demanded a CSRF pair from a cookie session, so a client
  holding a per-user bearer token had no path to it — the documented workaround was
  `driftless wizard apply`, whose `change_log` row carries `actor=null`. The pair is now
  required only where forgery is possible: a cookie is *ambient* (a browser attaches it to
  whatever another origin causes), while a bearer token is attached deliberately and no
  cross-origin page can make a browser send one. The gate stamps which credential
  authenticated the request; a cookie still wins when both arrive, so a browser that also
  sends a header still pairs, every other form POST is unchanged, and a viewer's token is
  still refused the write. The guide now runs the token-driven apply and reads the
  `change_log` row back naming its owner.

- **`docs/agent-guide.md` — the loop a non-human client drives**, where integrating meant
  reading source: mint a per-user token, `wizard next`, write the output it names through the
  JSON API, export CSV, read the `change_log` row naming the token's owner. Every fenced
  block is extracted and run by `tests/test_docs_agent_guide.py` against a real app and a
  throwaway store, and an unmarked fence fails too, so no command reaches the guide unrun.
  Rough edge named: a CLI `wizard apply` writes `actor=null` (the entry above closed the other).

- **Signing out is now CSRF-protected**, closing the risk logged when sign-out began
  revoking every device: a forged `POST /logout` could sign a colleague out of every
  browser they used, not just drop one cookie. Protecting it meant a token on every
  page, since the sign-out form sits in every nav — so the seven per-router template
  environments became one (`driftless/web/templating.py`) rendering the token into every
  page and the cookie half onto every response, with no router minting by hand.

- A viewer who submits a web form now sees the designed refusal page instead of a raw
  JSON body in the browser. The role gate sits outside the app, so its 403 reached none
  of the HTML error handlers: a signed-in viewer posting the weekly status form was
  answered `{"detail":"writes need the contributor or admin role"}` on a blank page. The
  gate now decides from the app's own page routes — the same fact the error handlers key
  on, never an `Accept` header — and renders the shared refusal page, whose wording is
  its own: you are signed in as a viewer, ask an admin for contributor access. Every
  other surface is byte for byte unchanged, the JSON API refusal included, and a gate
  that cannot read the route table answers JSON rather than raising. The 401 is
  deliberately untouched on both surfaces.
- Audit rows now name the person: a write made by a signed-in user is recorded on the
  ChangeLog with their username as the `actor`, where every row previously carried
  `actor=None` and "who changed this?" had no answer. The credit is stamped at the one
  session dependency every route already takes, so no write site can forget it — the
  gate resolves the identity once per request and the flush listener reads it off the
  session. The gap is stated rather than papered over: a request authorized by the
  shared `DRIFTLESS_API_TOKEN` bearer resolves no user, so its writes stay
  unattributed, exactly like a CLI or migration write. That token is the bootstrap
  credential; per-user API tokens are their own unit, and nothing here invents a name
  for a row nobody signed.
- `OPERATIONS.md` now names the public paths of a gated deployment — `/health`,
  `/static/…`, `GET`/`POST /login`, `POST /logout`, and nothing else — which credential
  each surface takes, and that `DRIFTLESS_SESSION_SECRET` **must** be set or no session
  cookie ever authorizes (the cookie half fails closed; the bearer half runs open when
  its token is unset). The whole sign-in walk — refused, sign in, admitted by the cookie
  alone, sign out, the captured cookie refused — is now one suite test
  (`tests/test_auth_end_to_end.py`) instead of a hand check, because the gate and the
  login page each passed their own tests while the pair between them was broken.
- The request gate accepts a session cookie as well as a bearer token: with
  `DRIFTLESS_API_TOKEN` set, a signed-in browser is no longer refused 401 for
  carrying a cookie instead of an `Authorization` header. One gate, two credential
  kinds, and the resolved user is left on the request for role gating and per-user
  audit rows to read next. The two kinds default opposite ways on purpose — no token
  leaves the gate open (development), while no `DRIFTLESS_SESSION_SECRET` means no
  cookie can ever authorize, because an unsigned cookie is a forgeable login. A
  cookie whose user was deactivated, or whose session epoch has since been bumped,
  stops working immediately. `/health` and `/static` behave as before, and the login
  surface — `GET`/`POST /login`, `POST /logout` — joins them as public: a gate that
  hides the login page can never be signed into, so with a token set no cookie could
  otherwise come into being. Those paths are matched exactly, so a future
  `/login-admin` stays gated; nothing else opens, `/` included.
- CSV import: `bin/driftless-import.py rows.csv --csv tasks` (also `risks`, `costs`
  and `milestones`) posts one flat row per record through the same validated API
  the JSON mode uses — still never a second write path. Each kind's columns are
  declared once in the script, the parent is named by its id column
  (`workstream_id`, `project_id`), and an unknown column, a missing required
  column or a cell that will not coerce is refused with its row number *before*
  anything is posted; a blank optional cell is omitted rather than sent as `""`.
  `bin/sample-tasks.csv` is a worked example. JSON stays the default mode.
- Sign-in: `GET`/`POST /login` and `POST /logout` remember a user in an HMAC-signed
  `HttpOnly` cookie (`DRIFTLESS_SESSION_SECRET` is required to sign in;
  `DRIFTLESS_COOKIE_SECURE=0` for local HTTP), behind a CSRF-bound form with one
  message for every failure. The nav gains Sign in / Sign out; nothing is gated yet.
- Structured request log: one JSON line per HTTP request (timestamp, method,
  path, status, `duration_ms`, client host) on the `driftless.request` logger.
  Silent until an operator raises that logger to `INFO` — see "Request log" in
  `OPERATIONS.md`. Query strings, bodies and `Authorization` headers are never
  logged.
- `OPERATIONS.md` gained an **Upgrading** section: back up, pull, rebuild; the
  container migrates before it serves.
- Test-only hardening from the audit (no behaviour change): the guard refusing a
  baseline line a PATCH would slide into a *different* approved baseline is now
  executed directly, so deleting it can no longer ship silently; the two
  free-moving FK allowlist entries (`Person.department_id`, `Task.assignee_id`)
  now prove the move lands and persists instead of asserting nothing; and the
  CSV export/import round trip POSTs the importer's payloads through the real
  `/milestones` route, re-exports, and compares every column field by field.
- Three fallbacks the suite never walked are now pinned by tests, each through the
  surface it protects. The token gate answers a refusal in JSON, and warns, when it
  cannot read the app's page routes — a shape it does not recognise must not turn
  every later request into a 500, including the sign-in redirect a browser needs to
  recover. `render_document` raises and names a slug no document claims, so the CLI
  cannot write an empty report and exit 0. And an edit that does not move a program
  — a rename, or restating the portfolio it already lives in — is allowed while the
  program still has projects; only a genuine move is refused.
- Tests pinning evaluator verdicts that were previously unasserted: the amber
  risk score is pinned to its computed value (a mutated formula now fails the
  suite instead of sailing through), and procurement, stakeholder and resource
  each prove their populated healthy path — rows present, none problematic —
  returns a clean green rather than earning it from the empty-register early
  return.
- Tests: the Monte Carlo forecast is pinned to literal p50/p80/p90 dates for a
  fixed seed (a run-twice self-comparison proved only within-process agreement),
  and `assess_contingency`'s refusal of a contingency rate outside 0..1 is now
  covered.
- Report-document tests now prove isolation and row identity: every document
  fixture seeds a second project whose rows must never bleed in (charter,
  scope & baseline, forecast, weekly status, schedule, risk register,
  department), and the Cost/EVM test seeds nine pairwise-distinct figures and
  pins each table row — label and value together — so swapped rows cannot pass.
- **Surface tests now read values, not presence.** The business map's 49 cells are
  checked cell-for-cell against the rollup's own shares and share-band washes (an
  under-half share must wash `warn`); the gantt "Schedule as text" rows are matched
  row-for-row to the drawn bars and marks; the capacity heatmap proves a four-week
  80 h task books 20/20/20/20 rather than 80 up front, and that only the newest
  approved baseline version windows a task's hours; the EVM and status-trend
  polylines are parsed and matched point-for-point to their computed series; and
  the wizard's 422 for a kind it cannot produce is pinned.
- A change request now records which PMBOK process raised it: `origin_process_id`
  (nullable, validated against the live catalog) on `POST /change-requests`, filled
  in automatically by the wizard form and by `wizard apply --process <id>`.
- **Per-PR changelog fragments** — a PR now records its entry as one file under
  `changelog.d/` (`<PR#>.<type>.md`) instead of editing `CHANGELOG.md`, so two open PRs
  can no longer conflict over the same changelog lines;
  `bin/assemble-changelog.py --release <version>` folds the fragments in at release time.
- The project hub's completeness is now pinned to **the engine's own answer**, not to a
  hardcoded percentage: `tests/test_project_hub_completeness.py` walks
  `state.completeness` and `pages.area_completeness` for the seeded store *outside* any
  prefetch scope and requires the rendered overall figure and all ten area rings to match
  it exactly. Narrowing the hub's `state.prefetched` scope to the wrong project set made
  `mapping._rows` serve every resolver an empty row list — completeness and every ring
  fell to 0% while the page still returned 200 with the rings in place, and the whole
  suite stayed green (only the query guard moved, and it moved *down*). Both tests first
  assert the seed is part-done and its areas disagree, so an all-zero page cannot satisfy
  the equality, and no expected percentage needs editing when the seed grows.
- The process-map legend's completeness is now **derived, not asserted**: a test
  enumerates the states straight off `ProcessState`, the enum the state engine
  computes against, and checks `pages._LEGEND` names exactly that set. A state
  added to the engine and forgotten in the legend now fails this test instead of
  shipping a legend that silently omits a state the grid can render.
- The ten subsidiary management plans resolve against the store and the wizard can
  produce each one (prose required by construction). Plan Scope/Schedule/Cost/Quality
  Management, Plan Communications/Risk/Procurement Management and Plan Stakeholder
  Engagement become assessable — 18 of the 49 processes now have no tracked output,
  down from 26 — and a written plan body is what moves each of them to produced.
- The narrative store and the API boundary accept the fifteen prose artifact kinds —
  the nine subsidiary management plans, the stakeholder engagement plan, the project
  scope statement, requirements documentation, the team charter, basis of estimates,
  and team performance assessments — each stored under its catalog artifact name.
  None is tracked yet: the process map reports them untracked until a resolver lands.
- The catalog now declares PMBOK's conditional outputs (`Process.optional_outputs`):
  `change_requests` on its 22 emitters, `project_management_plan` on its five updaters,
  `approved_change_requests` on 4.6 and `closed_procurements` on 12.3. The state engine
  judges PRODUCED on required tracked outputs alone — a present optional output counts as
  activity (IN_PROGRESS) but can never demote a process out of PRODUCED, and a process
  whose only tracked output is optional is not assessable. All four kinds are untracked
  today, so no completeness figure moves; the change makes a future resolver for a
  conditional kind safe by construction.
- `bin/driftless-snapshot-pages.py` captures every page the app serves as rendered HTML
  from the demo store at a pinned `--anchor`, byte-identically, so a design review can
  diff the whole surface (38 pages today, written to `docs/page-snapshots/`, git-ignored
  like `reports/`). The page list is discovered from the router rather than written down,
  which picked up `/pmbok/{process_id}` — a page the route probe had been dropping.
- The plan-of-plans and the communications record resolve against the store, closing artifact
  coverage at 49 of 49 processes. `project_management_plan` rolls up the ten subsidiary plans;
  `project_communications` reads the note a status snapshot carries, so a number filed is not
  mistaken for a communication made. Both derived, so neither gains a wizard button.
- `change_log` now carries an index on `(table_name, row_id, changed_at)`, the shape the
  dated progress replay filters on. Without it the planner read the ENTIRE audit log to
  answer one project — on a 5,466-row log, `SCAN change_log` at 9.7 ms per read, versus
  1.4 ms searching the index — so every dashboard got slower as the trail grew rather
  than as the plan grew. Declared on the model and added by migration `d1c84b7e0a92`,
  which reverses on its own: an existing store gains it with `alembic upgrade head`.
- The scope statement, requirements documentation, team charter, basis of estimates and
  team performance assessments resolve against the store, and the wizard can produce each
  one. Collect Requirements, Estimate Activity Durations, Estimate Costs, Estimate
  Activity Resources and Develop Team become assessable — 13 of the 49 processes now have
  no tracked output, down from 18 — and Define Scope and Plan Resource Management each
  owe a written body they did not before.
- The task register answers for two more PMBOK outputs, derived rather than stored: a task IS
  the scheduled activity (healthy only when every one carries an estimate — an unsized activity
  cannot be sequenced or weighed against capacity) and `Task.assignee_id` IS the team assignment
  (healthy only when no task is unowned). Sequence Activities and Acquire Resources become
  assessable — 2 of the 49 processes now have no tracked output, down from 4 — and the read
  batches through the same prefetch scope every other resolver uses, joining `Workstream` for
  the project id a task does not carry.
- Every artifact kind now carries its recorded disposition: the 65 vocabulary kinds
  without a resolver each state, in `driftless.pmbok.mapping.UNTRACKED_DISPOSITIONS`,
  why they stay untracked and what the store consults instead — and a partition test
  makes a silently undispositioned kind unrepresentable.
- The work-performance chain resolves from the store, derived rather than stored: the reports
  a project files are the status snapshot series under the catalog's own name, and work
  performance information is an approved plan plus dated actuals, healthy while the newest
  actual is inside the reporting cadence. Nine monitoring processes become assessable — 4 of
  the 49 now have no tracked output, down from 13 — and neither kind is producible, having
  nothing of its own to write.

### Changed
- **A project now costs the dashboard nothing.** The last three per-project reads
  batched too — the resource evaluator's tasks (grouped through their workstream,
  people loaded on the same pass) and the communications evaluator's status lookup
  (the mapping layer's cache fills lazily per model, so opening it for one read
  costs one query) — and the threat board's own assessment pass now runs inside the
  same scope. `/` and `/threats` are flat in the project count: 9 and 18 statements
  per extra project became 0. On the release-gate store `/` fell from 162 statements
  to 114 and `/threats` from 139 to 47 — every page byte for byte as before.

- **The dashboard stopped paying a query bill per project.** Each of the nine
  evaluators read its rows one project at a time, so `/` charged ~47 statements per
  extra project — a 50-project store rendering in ~2,300 round trips to the database.
  Those reads now batch across every project in one query each, as does the threat
  sign-off ledger: `/` fell from 370 statements to 162 on the release-gate store, and
  the marginal cost of a project from ~47 to 9. Same rows, same figures — every page
  renders byte for byte as before.

- Eight helpers three modules already shared lost their leading underscore, which was
  simply untrue: the API's `fetch` / `insert` / `stamped_percent` (imported by the web
  pages and the wizard CLI) and the pages layer's `STATE_RANK` / `pct` /
  `area_completeness` / `evm_curve` / `threat_cards` (imported by the business map and
  the project hub). A `_`-name reads as "mine, safe to change", so the next refactor of
  `api/app.py` would have silently broken the web layer. Names nothing else imports stay
  private, and a source-walking test now fails any future cross-module import of a
  private name. Rename only — every surface renders byte for byte as before.
- The commercial-volume statement-slope guard now asserts a project's marginal
  cost is **exactly zero** statements, not `<= 1`. Statement counts are integers,
  so the slope has no wobble to tolerate, and the old ceiling waved through the
  exact N+1 the file exists to catch — dropping
  `selectinload(Project.milestones)` from `adapters.eager_project()` put `/` at
  slope 1.0 and the suite stayed green. Proven by mutation both ways: the
  tightened guard fails against that mutation and is green without it.
- The coverage floor is a floor again: `--cov-fail-under` moves from 80 to **99.2**
  against a measured 99.64% (4935 statements, 18 missed). At 80 roughly 950
  statements could go dark with CI green — deleting every test touching
  `api/app.py`, `web/pages.py` and `api/secure.py` still measured 82.1% and passed.
- The built distribution now carries `driftless/py.typed` (declared in
  `[tool.setuptools.package-data]`), so PEP 561 lets a downstream importer see the
  annotations that `mypy strict` already enforces instead of discarding them.
- `psycopg[binary]` is a runtime dependency rather than a `[dev]` extra:
  `deploy/entrypoint.sh` builds a `postgresql+psycopg://` URL, so `pip install .`
  had been producing a container that could not open its own store.
- `tests/test_packaging_metadata.py` holds all three to the repo: the floor is
  compared with the measurement, the marker must exist *and* be packaged, and every
  `dialect+driver://` URL the shipped entrypoint builds must name a declared runtime
  dependency — so a second backend cannot repeat the psycopg omission.
- **The page-performance ceilings can fail again, and a baseline that drifts now says so.**
  Every whole-store ceiling was sized at "measured plus one statement per project the call
  walks" — at six projects exactly what the cheapest defect they name costs, so a relapse
  adding one statement per project landed *on* the `<=` boundary and passed. Each is
  re-derived at measured + 1 or 2: `portfolio_nodes` 26, `top_threats` 21, `attention_feed`
  39, `threat_cards` 56, the home render 132, the report documents 19/9/19, the same at
  commercial volume (132/19/56) and on the `driftless report all` path (100/134/19).
  Recorded numbers kept drifting while living only in a comment — the `report all` path's
  three were stale by 2, 2 and 3, and the project hub's had reached its own ceiling exactly,
  so the next honest read would have failed as a mystery breach rather than as the drift it
  was. Every baseline now lives in a `MEASURED` dict its ceiling test re-measures on every
  run, so drift fails naming both numbers, and a further test fails when a recorded number
  is never re-measured — it caught the `report all` counts falling 107 -> 98 and 151 -> 132
  when the sign-off prefetch stopped being scoped per project. The ceilings are priced
  against the regressions they name, not argued: deleting the eager options costs 66
  statements against the 56 ceiling, 60 against the scoped 59, 112 against `/threats`'s 56
  at commercial volume and 108/156 against the report path's 100/134; deleting the hub's
  prefetch scope costs 476 against 87, and re-opening the map's nested scope 66 against 19.
- **CI stops spending runner time on questions it already knows the answer to.** The suite
  runs under `pytest -n auto` (6 workers on the shared runner host) instead of serially —
  the `PYTEST_XDIST_AUTO_NUM_WORKERS` cap that was already in the workflow had been dead,
  because `pytest-xdist` was not a dev dependency and the step invoked a bare `pytest`. The
  test job no longer waits on the lint job, which shares no artifact with it. `pip-audit`
  moved to its own workflow with a dependency-file path filter, so it starts only when an
  input it audits moved rather than starting on every pull request to compute its own skip.
  Scheduled and manually dispatched runs now get distinct concurrency groups, so a nightly
  and a hand-triggered run on `master` stop cancelling each other. Every job has a
  `timeout-minutes`, replacing GitHub's six-hour default. Dependabot arrives grouped and
  weekly (`.github/dependabot.yml`), one pull request per ecosystem, never automerged.
- The wizard now works out a step's `producible` outputs from the producer registry
  (`wizard.cli`) rather than from "every tracked kind", and `next_step` skips a process it
  can produce nothing for the way it already skips an unassessable one. The two sets are
  identical today, so no step, no walk and no completeness figure moves — what changes is
  what happens next: a *derived* artifact kind (one resolved from stored inputs, with
  nothing of its own to write) can now gain a resolver without a producer, and simply never
  appears as a button. Before, it would have been offered and then refused with `422`, which
  is why every wave so far had to ship a producer per resolver just to keep that quiet.

### Fixed
- **The audit-actor test no longer breaks when FastAPI moves.** It imported
  `get_flat_dependant` from `fastapi.dependencies.utils` — a private module — to walk
  each route's dependency tree. That import stopped resolving in FastAPI 0.140, and
  because `pyproject` declares `fastapi>=0.110` with no upper bound, any fresh resolve
  picked up the break: the module failed to import and took the whole test session with
  it. The pinned lockfile added in this release is what surfaced it, having resolved
  0.140.7 where the development environment still had 0.139.2. The tree walk is four
  lines, so the test now owns it rather than pinning the framework backwards to keep a
  private helper reachable. Verified against both versions.
- An earned-value snapshot no longer invents a progress measurement for a date it
  cannot answer. `Task.percent_complete` is an undated *current* reading, and the EVM
  adapter used to hand it to calc stamped with the as-of being asked about — so
  `?as_of=2025-06-01` printed EV 500 and "50% complete" seven months before the
  project started, and an as-of in a month the plan had not begun printed an SPI in
  the tens. An as-of before the plan's earliest planned start now returns the same
  no-plan empty state the product already renders — BAC/PV/EV 0, spend still real,
  ratios `n/a` — instead of a number. PV and AC are genuinely time-phased and answer
  every as-of unchanged, so the planned-vs-actual S-curves and burn sparklines are
  untouched.
- **A backdated status snapshot records the percent that was true on its own date.**
  `stamped_percent` read earned value through `gather.project_evm`, which holds no
  session and so reads `Task.percent_complete` — one undated *current* number that
  answers every as-of. A snapshot filed for `taken_on=2026-02-15` therefore stamped
  TODAY's completion, and because the status series is append-only (no PATCH or
  DELETE exists for it), the wrong figure was permanent and the trend chart plotted
  it. The stamp now reads through `adapters.project_snapshot`, whose ChangeLog
  replay dates each progress reading — reached from `POST /status-snapshots`, the
  weekly status form and the wizard alike, since all three share the one stamp.
- **A constraint conflict answers in the surface's own language.** Refiling the
  weekly status for an already-snapshotted date hits
  `uq_status_snapshot_project_date` through the form (which has no pre-check — an
  everyday PM action), and the `IntegrityError` handler answered raw JSON with no
  navigation; the wizard hit the same trap on `uq_narrative_project_kind`. The
  handler now keys on the surface the request matched, exactly as every refusal in
  `driftless.web.errors` does: a page surface renders the designed HTML 409 shell,
  and every API error body stays byte-for-byte what it was.
- **The backup's restore-verify counts rows, and the drill is actually run.** It compared
  `information_schema.tables` between the source and the restored copy, so a `--schema-only`
  dump — every table, not one row — matched and printed `restore-verify OK`. It now compares
  the row count of every table, refuses a set whose totals are zero, and records
  `N tables / M rows` in the manifest. Nothing had ever executed the script: a new drill
  (`tests/test_backup_script_drill.py`) runs it against stub `pg_dump`/`pg_restore`/`psql`
  on PATH, so a full dump verifies and a schema-only one fails, offline and without Postgres.
- **The backup set is no longer world-readable, and the timestamp cannot choose where it
  lands.** The dump is the whole database in the clear and the manifest names where the age key
  is escrowed; under a scheduler's default umask both were `0644`. The script now sets
  `umask 077` before it writes anything, as `deploy/entrypoint.sh` does. The timestamp argument
  is sanitised for the three file names it builds — it already was for the verify database name
  — so a caller's `date` format string can no longer write outside `$DRIFTLESS_BACKUP_DIR`.
- A failed import is now recoverable instead of silently half-done. `bin/driftless-import.py`
  creates one row per POST with no transaction spanning them, so a failure on row 3 of 5 left
  rows 1-2 in the store and re-running the file duplicated them — exactly the asymmetry the
  importer refuses an `id` column over. A mid-file failure now raises `PartialImport` naming
  what landed, the CLI prints that record (`landed: {"tasks": 2}`) and `--skip 2` re-runs only
  the rest, so recovering from a half-import cannot double a row.
- A JSON task now carries every field a `--csv tasks` row does. `percent_complete`, `status`
  and `assignee_id` were read from the file and dropped on the way to the API — the same
  asymmetry the CSV path refuses out loud — because the JSON walk hand-wrote a subset of
  columns. Both paths read one column set now, and a task field that is not an importable
  column, or a `workstream_id` the file's own nesting already names, is refused naming the
  task rather than dropped.
- A missing file, a file that is not JSON, or an unknown CSV column now exits 2 with one line
  on stderr, matching the `driftless` subcommands, instead of a raw traceback at rc 1.
- The two operator-run tools in `bin/` no longer destroy files they did not make.
  `driftless-snapshot-pages.py` clears `*.html` out of `--out`, so it now writes only
  into a directory it created (marked `.driftless-page-snapshots`) or an empty one, and
  refuses anything else instead of deleting a hand-written page under `--out docs`.
  `assemble-changelog.py` parses `--date` as a real date at the command line, before a
  release stamps the log and unlinks every fragment, and reports a changelog it cannot
  fold into rather than raising over it. The repo's no-secrets-in-a-document guard now
  reads tracked shell scripts too — `deploy/entrypoint.sh` and `bin/*.sh` were unscanned.
- Audit-trail guard: a multi-column update must log every moved column with its
  old/new values, and a same-value rewrite mixed into the same flush stays out.
  The base changelog tests only ever moved one column, so a regression that
  thinned `detail["changed"]` would have passed the whole suite (F-T21).
- **The migration chain is proved on Postgres, not only on SQLite.** SQLite takes every
  schema change through Alembic's copy-and-swap batch mode, which is the one path a
  deployment never runs — so the parity proof was green on a topology production does not
  have. `tests/test_migrations.py` is now parametrised over both dialects: point
  `DRIFTLESS_TEST_DB_URL` at a server and the whole chain is built, compared against the
  models (CHECK constraints included) and reversed there too. A new **Migrations
  (Postgres 16)** CI job does exactly that against a health-checked `postgres:16` service
  container. Unset — a developer's plain `pytest` — the Postgres half skips rather than
  fails, so no local server is needed. A guard test asserts the dialect proved is the
  dialect asked for, because the failure that matters is a Postgres run that quietly
  proves SQLite a second time.
- **CI runs least-privileged, on pinned actions.** Both workflows declare a top-level
  `permissions: contents: read`, so every job inherits a read-only token and only the
  alert jobs re-grant themselves `issues: write`. `actions/checkout` and
  `actions/setup-python` are pinned to full commit SHAs with the release named beside
  each: a floating `@v7` is a mutable pointer to somebody else's code, running on a
  runner that holds this checkout and the workflow token.
- **A database the CLI cannot read is now a sentence, not a stack trace.** `driftless
  assess`, `report all`, `user list`, `token list` and `wizard next` pointed at a store
  with no driftless tables printed a 20-line SQLAlchemy traceback; they now print
  `no driftless tables in the database (…) — run \`alembic upgrade head\`` and exit 2.
  A SQLite URL naming a file that does not exist is refused *before* anything connects,
  so a typo no longer leaves a 0-byte database file behind.
- **Two projects of the same name are refused instead of guessed.** `Project.name` has no
  unique constraint, so `driftless assess "Website Rebuild"` silently acted on the lower
  id when two existed. Every CLI that resolves a project by name now names both ids and
  exits 2; pass the id to choose.
- **A failed request now appears in the request log.** A route that raised returned 500
  and produced no `driftless.request` line at all — the one class of request an operator
  goes to the log for was the one class missing. The line is emitted whether the route
  returned or raised, carrying the status actually served.
- The real (Postgres) engine pool now covers Starlette's 40-token sync threadpool (was 5+10, so the
  16th concurrent request waited 30s and then 500ed), pre-pings so the first request after a database
  restart reconnects, and recycles half-hourly.
- Every foreign-key column not already leading a unique constraint is indexed (23 columns, migration
  `c8f3a1d47e29`), so per-parent reads stop scanning the whole child table.
- `app_user.session_epoch` carries its `0` server default on the model as well as in the migration,
  so both store topologies accept the same omitted-column insert.
- *Rolling back in place* (OPERATIONS.md) dumps the current state before `pg_restore --clean` drops it.
- `driftless demo seed` refuses a store that already holds businesses unless
  `--force` is passed — a second seed used to duplicate the demo, and the API's
  delete-integrity guards (approved baselines, parents with children) made the
  copies unremovable (F-D1). It also refuses an empty `--token` before touching
  the network, and reports unreachable or refusing APIs as a one-line message
  with a non-zero exit instead of a raw traceback (F-X15).
- The admin guide's bare-host runbook clones `Back-Road-Creative/driftless.git`
  (it said `workspaces.git` and a directory this repo does not ship), and its
  seed one-liner carries the `--force` its own walkthrough now needs (F-X1).
- The admin-guide doc test holds `manual` blocks to an exact allowlist with a
  substantive `why=`, so an excused command can no longer drift unnoticed —
  which is how F-X1's wrong clone line slipped through (F-T20).
- The public listener now sets the headers a browser needs to be told — a year-long
  `Strict-Transport-Security`, `nosniff`, `X-Frame-Options: DENY` and a
  `Content-Security-Policy` that pins the origin, none of which Caddy added itself
  to pages that render stored text. The policy is pinned to the templates, so a page
  that would violate it fails the suite rather than only a browser.
- Every container declares a memory ceiling (the app a CPU one too), so a login storm
  hashing at ~16 MiB per password is that container's bad minute, not the host's.
- A scheduled uptime check probes the deployed `/health` from outside the host and
  opens (or appends to) an alert issue when it stops answering. Docker's `unhealthy`
  restarts nothing and tells nobody, and the existing alarm only watched CI.
- `.sops.yaml` says what it is: replacing the placeholder age recipient is required
  before the first deployment, not a working default, and no encrypted secrets file is
  committed here — a test fails if one exists while the placeholder stands. It and
  `.pip-audit-ignore` also drop their pre-rename `pmhub` naming, and the audit list no
  longer claims this project declares no runtime dependencies.
- `driftless user add` now refuses a password shorter than 12 characters, before it is
  hashed and before the row is written. `deploy/entrypoint.sh` has always refused a
  machine secret under 24, while the one credential a human types could be a single
  character — the weakest thing the service would accept, on the account most likely to
  be an admin.
- README corrections. The demo store is 4 projects with baselines on the statused
  **three**, not 3 with two statused (`OPERATIONS.md` already read correctly, so the two
  documents disagreed); *Development* now says out loud that the `python3 -m venv .venv`
  recipe is for a fresh clone while the workspace box uses the venv provisioned outside
  the tree, which is what `CLAUDE.md` meant by "there is no `.venv` — don't look"; the
  weekly-status note no longer claims per-task progress history is not retained, since
  `progress_history` replays it from the ChangeLog; and the department drill, the demo
  seed's `--force`, the wizard's re-baseline refusal, the per-client login cap and the
  error shell's 422 are described as they now behave. README and `LIFECYCLE.md` no
  longer point at a `.data/plans/…` build plan that stayed in the monorepo this repo was
  extracted from.
- The dated ChangeLog replay is the one source of truth for earned value. The
  assessment path already replayed task progress out of the log, but `snapshot_from`
  called without a progress series — every report and dashboard surface behind
  `gather.project_evm` — silently fell back to stamping today's percentage at
  `date.min`, so one store at one backdated as-of printed EV 800 / CPI 2.00 in
  `cost-evm.md` while the assessment said CPI 0.50 and rated the project red. An
  omitted series now resolves the replay through the project's own session, healing
  every caller at once; only a project attached to no session (no store, so no log
  to speak for it) keeps the undated current reading — the same answer the replay
  gives a task with no logged history. Three replay hardenings ride along: a logged
  delete truncates its row's replayed readings, so a SQLite rowid reused after a
  delete no longer hands a brand-new 0% task a dead task's earned value; the
  per-session replay memo is invalidated on the session's own flushes and rollbacks,
  so a session that writes progress and reads again is never served the pre-write
  replay; and a batched read for a project outside the open prefetch scope raises
  instead of fail-open answering "no rows", which read as green everywhere.
- The dashboard's swept charts no longer re-adapt every project's plan at every sample
  date: the baseline-to-value-object step (plan selection, line sort, list builds) is
  hoisted out of the per-sample loops behind the business S-curve and the burn
  sparklines, and runs once per project per request instead of once per sample — the
  request cost grew 12x as projects grew from 5 to 300 tasks. The rendered series are
  byte-identical, pinned against the canonical adapter at every date regime.
- A plan window shorter than the chart's sample count no longer repeats dates: 12
  samples over a 3-day span plotted 12 points on 4 distinct days, and the S-curve's
  accessible text twin repeated a row per duplicate. The shared sampling window now
  collapses duplicates — a short window sweeps one sample per calendar day, and the
  degenerate not-yet-started window is a single as-of sample rather than twelve copies
  of it.
- **The image installs the version set the audit scanned.** `requirements.lock` said it
  kept CI, `pip-audit` and the Docker image on one resolution, and two of the three were
  true: the `Dockerfile` passed no constraint and never copied the lock into the build, so
  with every dependency declared `>=` a green audit described whatever pip resolved on the
  runner that morning, not the artefact an operator runs. The image now installs under
  `--constraint requirements.lock`, and `tests/test_image_dependency_parity.py` fails if
  the constraint, the `COPY` that makes it resolvable, or a pin it relies on goes away.
- **No test tooling in the production image.** The install line asked for the `[dev]` extra,
  which put `pytest`, `pytest-xdist`, `coverage` and `httpx` in the shipped container as
  pure CVE surface with nothing to run them. It installs the runtime set instead, naming
  `psycopg[binary]` explicitly — the one runtime dependency the extra had been carrying.
- **The base image is pinned by digest.** `python:3.12-slim` moves on every upstream
  rebuild, so one commit built twice was two different images and the interpreter and
  system libraries the audit reasoned about were not the ones that shipped.
- **Login throttling survives the reverse proxy.** Behind `deploy/proxy.compose.yml`'s
  Caddy, uvicorn trusts `X-Forwarded-For` from `127.0.0.1` alone by default — which the
  proxy container never is — so every request arrived as one shared compose address and a
  per-address throttle would lock out every user at once. The `CMD` now passes
  `--proxy-headers --forwarded-allow-ips=172.16.0.0/12`: the private range compose
  allocates bridge networks from, never `*`, which would let a client forge an address.
- Sign-in throttling provably keys the client uvicorn *resolved* — the forwarded
  caller once the deploy passes `--proxy-headers`, never a raw header read — so one
  peer tripping lockout on a known username locks nobody else out, and a second
  per-client cap (30 failures per 15-minute window across all usernames) refuses a
  username-rotating flood *before* the scrypt verify instead of paying ~16.7 MiB
  and tens of milliseconds per free guess.
- A refused sign-in (400/401/429/503) re-renders the form with the typed username
  kept — escaped data, never markup — and focuses the field, instead of making the
  user retype it.
- The failure counter is mutation-proven to restart once its window rolls over, and
  the attempt store's expired-window eviction is now covered.
- Artifact resolvers now answer for the as-of date asked instead of "now". 14 of
  16 resolvers ignored `as_of`, so a baseline approved in 2026 read as present in
  2025 and the process map, per-area rings, business completeness, the
  low-completeness signal and `driftless report all` were byte-identical at every
  date. Every resolver over a dated row now filters by it — `Baseline.approved_at`,
  `ChangeRequest.raised_on`, `Issue.raised_on`, `NarrativeArtifact.updated_on` —
  while an undated row (a wizard-filed narrative) still counts.
- The batched-read cache refuses a project outside its open prefetch scope with a
  `LookupError` instead of answering "no rows" — an out-of-scope project used to
  read as "nothing to assess" and grade green.
- The wizard's apply form refuses to re-baseline a project that already holds an
  approved baseline (409, nothing written). One click — or one direct POST — naming
  `scope_baseline` or `schedule_baseline` used to file version N+1 as approved on the
  spot, irreversibly rewriting the BAC every EVM figure is measured against.
  Re-baselining is a change-control decision; first baselines still go through.
- A refused wizard apply re-renders the form with the typed prose still inside its
  textarea and names the refusal above it. A 422 used to answer with an error shell
  containing no form at all, destroying up to 100,000 typed characters with no
  history entry to go Back into.
- The weekly-status form validates through `StatusSnapshotIn` and files through the
  JSON route's own create, so a RAG outside the vocabulary or an oversize note
  answers 422 at the schema boundary — the posted values used to reach the ORM
  unvalidated, bouncing off a CHECK constraint as a 409 or slipping past a VARCHAR
  length SQLite never enforces.
- `earned_value` now builds a task-id → latest-fraction index in one pass over the
  progress readings instead of rescanning every reading once per baseline task. The
  per-task scan made EV quadratic — 0.34 ms at 100 tasks to 62.79 ms at 1,600 (185×) —
  and the dashboard computes EV for every project on every snapshot, so it was 23% of
  a 1.73 s five-project page. Per-task answers are byte-identical, ties included.
- `driftless report all` stops re-reading the store per document. The CLI's project
  query now carries the same `adapters.eager_project()` options every web route
  already applies — no more lazy `line.task` load per baseline line — and the whole
  document loop runs inside one `adapters.prefetched` + `state.prefetched` pair, so
  per-project evaluator and process-state reads batch across the store (measured on
  the guard's seed: 316 → 149 statements at four projects, bytes unchanged). The
  Process Map document now rides an already-open prefetch scope instead of re-scanning
  the whole sign-off ledger once per project, and both Jinja environments (web pages
  and report documents) set `auto_reload=False` — packaged templates change only with
  a deploy, so a warm render no longer pays an `os.stat` per template.
  `tests/test_perf_report_all.py` pins the ceilings and the byte-equality.
- The per-project document bodies stop re-reading the store. The Assessment Report
  computes its assessments once per render and derives both the knowledge-area rows
  and the top-threat feed (the nine evaluators used to run twice), the feed still
  filtered and ranked exactly as `assess.live_threats` answers. Charter, Schedule and
  Forecast batch milestone reads through `adapters.project_rows` — one IN-query per
  open scope, not one SELECT per (document, project) — bytes unchanged. The Department
  Report's blended labour rate is now capacity-weighted: the old head-average priced a
  5-hour specialist as a 40-hour supply (125.00 where the supplied hour costs 66.67).
- Rollup verdicts and scores stop lying at the edges (audit F-C5–F-C8): a
  childless branch rolls up `unknown`, so an empty portfolio or program no
  longer renders healthy on the heatmap; `on_track_share` excludes `unknown`
  projects from its denominator and returns `None` (rendered "n/a") when
  nothing is assessable, instead of printing "0% on track" for a store with no
  verdict at all; the schedule score expresses milestone slip as the slipped
  share of the milestone list — the same unit as 1 − SPI — so near-total
  schedule collapse no longer ranks below one slipped milestone; and the
  exposure engine carries the absolute contingency reserve through instead of
  a rate whose float round-trip read an exactly-covered reserve as a red
  breach at score 0.0 that a sign-off would suppress forever.
- **A CSV export can no longer carry a formula into a spreadsheet.** Cells were written
  verbatim, so a project named `=cmd|' /C calc'!A0` — or any name, description or vendor
  beginning `=`, `+`, `-`, `@`, a tab or a CR — ran as a formula the moment someone opened
  `?format=csv` from any list route or from search. Such a cell is now marked literal with
  a leading `'`; a value that parses as a number (`-42.5`) is untouched and still totals.
  A name that did start with one of those characters comes back through the CSV importer
  with the `'` still on it — drop it if you re-import that row.
- **A carriage return in a name can no longer break the calendar feed.** `/calendar.ics`
  escaped `\`, `;`, `,` and newline but not CR, so a CR inside a milestone or sprint name
  ended its `SUMMARY` line early and let the rest of the name become a property of its own
  in every subscriber's calendar. CR and CRLF now fold into the one line break RFC 5545
  can escape.
- The sign-off ledger is now bounded by the as-of being asked about: a decision
  recorded against a later assessment date no longer rewrites an earlier page, feed
  or trend point (a threat accepted this week used to vanish from
  `/threats?as_of=2020-01-01`; a row with no recorded assessment date still applies
  at every as-of). The process prefetch scope loads only the scope's projects'
  ledger rows, the threat scope is public (`assess.engine.threat_sign_offs`), and
  `completeness`'s nothing-to-assess-is-`None` contract is pinned mutation-proven.
- **The plan empty states name the order that actually works.** The schedule and
  weekly-status charts said "baseline the plan and approve it (`POST /baselines`,
  `POST /baseline-lines`)" — followed literally, that order hits the API's own 409,
  since an approved baseline refuses new lines by design. Each now walks draft →
  lines → approve and names `PATCH /baselines/<id>` for the approval, which no
  empty state did.
- **A page's 422 stops claiming an error was logged.** `web/errors.py` had no 422
  wording, so a refused form input fell back to "Something went wrong … the error
  has been logged" — nothing failed and nothing was logged. The page now says the
  input was refused and how to fix it, and still renders none of the detail.
- **The data-swap script does what its comment claimed.** No template set
  `data-target`, so every background submit rewrote the whole document with
  `document.write()`: focus destroyed, nothing announced, no history entry — and an
  offline fetch rejection had no `.catch`, leaving the page byte-identical with no
  word to anyone. The threat board's sign-off forms and the weekly-status form now
  name their fragment; the script lifts the fresh fragment out of the server's full
  response, moves focus to it, announces the outcome in a polite live region, and
  surfaces a failed fetch in that same region.
- **Threat trend badges read without hover or colour.** ▲/▼ were bare glyphs and
  "vs last week" lived only in `title=` — hover-only: no keyboard, no touch, no
  print. The glyphs are `aria-hidden` with their words in an `sr-only` span (the
  treatment the unchanged badge already had), and the threat board's pager landmark
  is named.
- **The treemap's verdict is no longer colour alone.** Each rectangle's RAG lived
  solely in its `--rag-*` fill; the `<title>` named the portfolio and budget but
  never the health, so greyscale, print and the accessibility tree all read "a
  portfolio worth N". The title now prints the RAG as a word (the rollup table's
  own vocabulary, "no data" for unknown), each SVG link takes `tabindex="0"`, and
  the home test that accepted base.html's own `<title>driftless</title>` as proof
  of rectangles now demands the real ones.
- **The home S-curve's two series survive greyscale.** Both polylines were
  `.s-line` with `stroke: currentColor` and no dash. The actual line now dashes —
  the EVM chart's own idiom — and the legend says "Planned (solid)" / "Actual
  (dashed)" in words.
- **The dashboard's plan empty states name the order that actually works.** Both
  chart slots said "baseline each project's plan and approve it (`POST /baselines`,
  `POST /baseline-lines`)" — followed literally, that order hits the API's own 409,
  since an approved baseline refuses new lines by design. Each now walks draft →
  lines → approve and names `PATCH /baselines/<id>`.
- **Rail trend badges read without hover or colour.** ▲/▼ were bare glyphs and
  "vs last week" lived only in `title=`. The glyphs are `aria-hidden` with their
  words in an `sr-only` span, the treatment the unchanged badge already had. The
  business jump nav is a named landmark, and a department page's two empty states
  carry distinct ids instead of rendering `id="empty-state"` twice.
- **The project hub and the department drill read their own scope.** Both are one-entity
  pages, but the hub's cost read was the store-wide `select(CostEntry)` grouped after the
  fact — every project's spend fetched to render one — and the department drill rebuilt
  the whole org's `department_rows` to find its own row: 53 statements at 8 departments
  where the scoped page costs 10, growing with every department the page never renders.
  The hub now reads `adapters.project_costs` scoped to its project; the drill computes its
  one row from the same engines the Department Report renders from (`gather.project_evm`,
  `adapters.eager_project`, costs batched across its own projects), with the agreement
  test still pinning screen to document. The guards now hold: the hub test fails on any
  other project's cost row in the session, and the drill's statement ceiling is re-derived
  on a store big enough (8 departments) that the org-wide walk can never again hide under
  it the way 23 statements hid under a ceiling of 24 at 3 departments.
- Three guard-holes in the same pages' tests are closed: the hub's SPI and EAC slots are
  pinned to their own computed values, pairwise-distinct by seed, so CPI printed into the
  SPI slot no longer passes; the department drill's People table is asserted as the
  rendered `<tr class="person">` row, which a table of zeros used to satisfy via the
  page header's own "40"; and both fixtures seed a SECOND project/department carrying its
  own RAID rows, milestones, people and projects, so a dropped `project_id ==` or
  department-scope clause fails loudly instead of passing against a store with nothing
  to bleed.
- The wizard refuses to produce a scope/schedule baseline while an approved one
  exists: the newest approved version IS the plan of record, so a wizard-seeded
  approved vN+1 silently replaced the plan every EVM figure reads and could not
  be repaired through the API. Re-baselining stays with change control; a draft
  does not refuse.
- A wizard baseline lands as one transaction — workstream, task, baseline and
  line on a single commit, ChangeLog rows included; a mid-write failure no
  longer leaves a committed partial approved baseline.
- **A list endpoint answers a bounded window, not the whole table.** Every generic list
  route loaded all of an entity's rows into memory, and `?format=csv` built the entire
  export as one string — so one ordinary request against a commercial store was an
  unbounded allocation. A list now answers at most 500 rows by primary key and takes
  `?limit`/`?offset`; `?limit` is clamped to 2000 rather than refused. Both
  encodings carry `X-Total-Count`, `X-Limit` and `X-Offset`, so a truncated list cannot
  be mistaken for a complete one. Single-row `/{id}` reads are unchanged.
- **Importing a `driftless.web` submodule first no longer fails.** `driftless.api.app`
  mounted the web routers at its own import and every web submodule imports helpers from
  it, so `import driftless.web.pages` in a fresh process raised a circular `ImportError`
  (eleven of the fourteen did), the suite staying green only because isort sorts
  `driftless.api` above `driftless.web`. The mount now stands down when it is reached
  from a web module still executing its own body, and the lifespan completes it before
  the first request. Every ordinary order still mounts at import, so the route table a
  bare import exposes is unchanged.
- The numbers in the prose are read back from the code that decides them.
  `tests/test_docs_numbers_are_measured.py` builds each stated figure from the live
  constant and fails naming the sentence to fix, so a moved constant can no longer
  leave a plausible wrong number in front of a reader. It caught four: README's
  performance floor claimed per-page statement counts several times the ceilings CI
  enforces (it now states the ceilings themselves, which are decisions rather than
  readings, and the measured counts are not restated at all); `CLAUDE.md` and the
  README each gave a coverage floor the setting had left behind, one of them at a line
  reference that had moved, and both now cite `--cov-fail-under` where it is set
  instead of copying it; `requirements.lock`'s header said pyproject declares neither
  uvicorn nor psycopg, when `[project.dependencies]` declares psycopg; and the user
  guide's sign-in throttle,
  capacity horizon and search cap are now checked against `driftless/web/login.py`,
  `driftless/web/heatmap.py` and `driftless/api/search.py`. The page-snapshot bundle's
  file count is deleted rather than corrected — no test can keep it honest, and every
  page mounted moves it. A list endpoint's query vocabulary is read off the router and
  looked for in the guides' prose, which caught `?limit`/`?offset` shipping
  undocumented — the user guide now gives the window, its default and its ceiling.
- `driftless report all` stops looking a threat sign-off up once per threat. The
  document loop already ran inside `adapters.prefetched` + `state.prefetched`, but
  `state.prefetched` caches PROCESS sign-offs only — so the Assessment Report's
  per-threat `assess.is_suppressed` calls each fell through to a
  `state.latest_sign_off` query, a cost that grew with the store (measured on the
  guard's seed: 10 lookups at 2 projects, 20 at 4, 40 at 8). The run now also opens
  `engine.threat_sign_offs`, the public scope that reads the THREAT ledger once,
  taking the render to 96 / 130 / 198 statements from 105 / 149 / 237. Pure cost:
  every rendered document is byte-identical, sign-offs included, and
  `tests/test_perf_report_signoff_scope.py` pins both — the per-threat lookups at
  zero and one ledger pass however many projects, plus byte equality against
  scope-free single renders with a real suppressing sign-off in the store.
- **`driftless pmbok show` sends its refusal to stderr, like every other command.** An
  unknown clause id printed `error: no process with id …` on *stdout*, so a caller
  redirecting the catalog to a file captured the error message as data instead of seeing
  it on the terminal. It now goes to stderr, leaving stdout empty on a refusal; the exit
  code was already 2 and is unchanged.
- A first `docker compose up` in a fresh checkout no longer creates a *directory* where
  the encrypted secrets file belongs. The app mounted `deploy/secrets.enc.env`, which no
  checkout carries — it is written on the deployment host — and Docker answers a missing
  bind source by creating an empty directory at it, after which the documented `cp` of
  the plaintext template lands inside that directory instead of failing. The mount is now
  `${DRIFTLESS_SECRETS_ENC:?…}`, so Compose refuses up front, names the variable and
  starts nothing. Export it beside `DRIFTLESS_AGE_KEY` before `docker compose up`; it is
  the same variable `bin/driftless-backup.sh` already reads, so one export serves both.
- `.gitignore` no longer tells readers an encrypted secrets file is committed here, which
  `git ls-files deploy/` refuted, nor that OPERATIONS.md has operators generate the age
  key in the checkout, when it puts it under `~/.config/driftless`. Both claims are now
  checked against the tracked file list rather than a pinned string, so a comment about a
  file this repository does not have fails the suite.
- OPERATIONS.md carries the export the run now needs, and no longer says the encrypted
  overlay is committed — `git ls-files deploy/` lists only the plaintext example, so a
  reader was told the file would be there and then had to make it anyway. The same claim
  is gone from `tests/test_docs_no_secrets_in_repo.py`'s docstring, which cited being
  committed as the reason the file needs no exemption; the actual reason is that no ignore
  file names it. A guard now reads each `${VAR:?}` out of the compose files and fails if
  this page does not hand the operator that export, so a new required variable cannot ship
  with Compose's error message as its only documentation.
- A **process** sign-off now has to carry the `as_of` it was judged at, refused with a
  422 naming the field when it does not. `as_of` is what bounds the ledger — a decision
  recorded against a later assessment date cannot rewrite an earlier page — and a row
  with no recorded date has nothing to compare, so it applied at *every* as-of. For a
  process that decision is the whole state of the cell, so one dateless JSON post
  silently re-scored every process map back to the store's first day, escaping the bound
  the previous release added. The browser form always stamped the date; the requirement
  now sits on `SignOffIn`, the one write path both routes go through. Threat sign-offs
  keep the field optional on purpose: theirs suppress only while the server-stamped
  `signal` holds, and a sign-off with no as-of to score at records no signal, so it
  suppresses nothing.
- **A sprint's length counts both of its endpoints, so the velocity band no longer
  finishes a day early per sprint.** The Forecast Report measured each completed sprint
  as `(end_date - start_date).days`, an exclusive difference: a 01-01 to 01-14 sprint
  reported thirteen days. Every other length in the product is inclusive — `calc.evm`
  accrues a baseline task over `(finish - start).days + 1`, and `calc.forecast.Sprint`
  itself defaults to a fourteen-day fortnight — so the band divided the remaining points
  by the right velocity and then multiplied by a window one day short, pulling best,
  likely and worst each one day earlier for every sprint still needed. Three 15-day
  sprints with 13 points left now finish 2026-04-15 / 2026-04-15 / 2026-04-30 rather than
  a day and two days sooner. The test that checked the band had copied the same
  arithmetic, so it agreed with the bug; it now states the seeded sprint length as a
  constant and pins the three dates literally, which is what an implementation change
  cannot carry along with it. A same-day legacy row is still skipped — one day carries no
  velocity information — and no stored figure changes.
- **The `sops` binary is verified before the image trusts it.** The build fetched the
  release binary over the network and `chmod`ed it unread, and `deploy/entrypoint.sh` runs
  exactly that binary to decrypt `DRIFTLESS_SESSION_SECRET`, `DRIFTLESS_API_TOKEN` and
  `POSTGRES_PASSWORD` at start — so a swapped release asset silently replaced the program
  holding every deployment secret. The build now pins the sha256 the release's own
  `sops-v<version>.checksums.txt` publishes and `sha256sum -c`s it *before* `chmod`: a
  mismatch fails the build instead of shipping, and a binary is never made executable
  ahead of being checked. `tests/test_image_dependency_parity.py` fails if the check goes
  away, moves after `chmod`, or the pinned digest becomes a placeholder.
- **No wizard producer invents a value its caller did not supply** — producing any
  non-prose kind used to substitute a hardcoded one: a stakeholder called `Sponsor`, a
  `Preferred Vendor` agreement, a `defect_rate` metric at 1.0/0.5, a `labour` budget line of
  1000, a `Wizard-seeded risk` at probability 0.2, a `Kickoff complete` milestone, a baseline
  whose planned cost — BAC, the figure every EVM number is measured against — was 1000. The
  presence checks are content-blind `bool(rows)`, so one substituted row marked that output
  produced for good and nothing asked for the real value again. Each producer now refuses
  instead (`MissingField`: `422` on the form, exit 2 on the CLI, no row written), as the
  narrative kinds already did for a missing body, and the browser's apply forwards the fields
  the chosen kind needs. Which fields those are is one table — `wizard.cli.required_fields`
  reads it for a form and `seed_fields(kind, as_of)` answers it for an unattended run.
- **The wizard's form collects the fields its outputs are made of** — the select offered a
  browser every kind the step could produce, but the only input under it was the prose
  textarea, so choosing a stakeholder register, a risk, a budget line or a milestone posted
  a body with no name, probability or amount in it. Now that the producers refuse rather
  than substituting a value, those clicks would each be a `422` a person could not answer.
  The form renders one input per field the offered kinds need, read off the same
  `required_fields` table the producers refuse against — a date input for a target date,
  a number for money and probability, a select drawn from the ORM's own vocabulary for a
  cost category or a RAG reading — and a refused post hands every typed value back, the
  contract the prose textarea already had.
- **An agent reading the API guide is told the list window exists.** `?limit`, `?offset` and
  `?q` reached the API without a line in the agent guide, and the guard that should have caught
  it was satisfied by either guide naming a parameter — so the user guide covered for it. The
  agent guide is the contract a machine reads and it has no other page to fall back to, which
  made this the one reader most likely to page through a list and least able to notice it had
  been truncated. Section 4 now states the window, the clamp and the `X-Total-Count` header to
  compare against, with both numbers derived from `LIST_LIMIT` and `LIST_LIMIT_MAX`; the guard
  now requires the agent guide specifically.
- **The shipped task sample exercises `actual_effort`.** `bin/sample-tasks.csv` omitted the
  column from its header, so the worked example never touched a field the importer has always
  accepted — one row now carries 52.5 hours against a 40-hour estimate and the others leave it
  blank, covering the "a blank optional cell is omitted, never posted as empty" path too.
- **The Dockerfile no longer claims psycopg comes from the `[dev]` extra.** It moved to
  `[project.dependencies]`, so `.` installs it and naming it on the install line is
  belt-and-braces rather than load-bearing. The line stays until an image build has actually
  been watched — no docker daemon has been available here, so nothing about the image has been
  proven against a real build.
- **The business map no longer teaches two vocabularies for one wash.** Its single
  legend explained the four `.st-*` washes as share buckets — `st-ok` is "half+" — while
  the project badges directly under it painted the same washes with a process *state*
  word, so `st-ok` read "Produced" a few lines below a legend saying it meant "half+".
  Each vocabulary now carries its own legend beside the badges it explains, and the
  listing's is built from the very predicate that filters its rows, so it can neither
  name a state no row can carry nor omit one that a row does.
- **An empty process listing says why it is empty.** "No applicable projects." bypassed
  the shared empty state and named no reason, no command and no link — yet it was equally
  true of three different causes a reader could not tell apart. The listing now names
  whichever one holds: no output of the process is a kind the store tracks (with a link
  to what it produces), every project has waived it (each waiver named and linked), or
  there are no projects yet (`POST /projects`). The three are exhaustive by construction,
  since an assessable process on an unwaived project is a listed row.
- **A person's capacity is theirs, not one project's slice of it.** The Resource evaluator
  summed a person's remaining hours *on this project* and divided by the whole of their
  `capacity_hours`, so nobody could ever be flagged over capacity: the demo seed's two
  people carry **150 %** and **135 %** of a capacity three surfaces label `Capacity
  (hrs/wk)`, and the project holding the only work one of them was assigned rendered green
  with "No live threats". Every project only ever saw its own slice. It now weighs the
  store-wide total `person_task_loads` already prints beside that capacity on the
  department page and the capacity heatmap — one summation, not a second one — and raises
  the threat on **every project holding some of those hours and on no other**: each of
  those is a cause and can level its own share, while a project the person holds no open
  work on is neither. The threat carries both figures, `peak ratio 1.50 — 60 h in all,
  40 h of it on this project`, so the ratio reconciles against the project's own board
  instead of reading as an error. Resource scores rise wherever someone's work spans
  projects, so a sign-off recorded against the old, smaller score stops suppressing its
  threat and needs re-signing — which is the point: it was signed against a figure that
  was never the person's real load.
- The demo seed spreads its work over two part-time contractors rather than putting
  everything on the two leads. One person over the line now turns every project they
  hold work on red, and with two people holding all eight tasks the demo dashboard
  folded to red-and-no-data — a rollup all one colour, which the seed exists to avoid.
  Theo (40 h against a 30 h week) and Nadia (24 h against 20 h) carry the over-capacity
  story on the two projects that can hold it; Dana and Priya come back under, so Archive
  reads amber on its own cost and change signals and Fleet reads green.
- The weekly-status S-curve no longer separates planned (PV) from actual (AC) by colour
  alone. The two solid strokes were a computed **1.14:1** apart in light and **1.08:1** in
  dark — about 1:1 in greyscale, so on a printed or photocopied status pack a reader could
  not tell which line went above which where they cross. AC is now a **dashed** `--ink`
  stroke against PV's solid `--muted-ink` (3.03:1 / 2.33:1), the budget reference keeps its
  own dash rhythm, each legend key is drawn exactly as its series is, and the whole curve is
  repeated as a **table** in plot order — the `scroll.wide` text-twin idiom the Gantt and the
  dashboard S-curve already use. AC also stops borrowing `--rag-red`, so a project under
  budget no longer draws its actual cost in the alarm colour.
- The Gantt's planned window is edged in `--gridline` (3.23:1 / 3.38:1) instead of `--rule`
  (1.45:1), so a task at 0% complete — which has no progress fill at all — is no longer a
  ghost. `--rule` is exempt from every contrast floor as a decorative box edge; a new gate
  keeps that exemption out of `<svg>`, where the geometry *is* the content.
- **The dashboard's charts stay legible, and say when they have nothing to draw.** The cost
  S-curve anchored both end labels at the same `x`, so two series finishing within a few
  percent of each other — the healthy case — printed their figures 7.1 units apart under an
  11.2px glyph box, on top of each other. The lower label is now pushed a full line height
  clear (the pair cannot invert or leave the box) and the actual-series label moved inside
  the RAG-tinted group, so each figure belongs to a line. With no approved baseline anywhere
  the curve's whole slot used to vanish while the treemap kept its own beside it; the shared
  empty state now takes it and names the next step, as the Gantt does. The portfolio treemap
  splits on weight across each rectangle's **longer** side instead of claiming a share of the
  remaining rect along an alternating axis: 20 equal portfolios ran to 30.7:1 with a 10.5-unit
  edge and 1 of 20 named, now under 3.5:1 with every rectangle named. `treemap_layout` places
  the labels itself against real geometry — name and budget, name, or a truncated name,
  whichever fits — so the landscape-only `w > 70 and h > 26` gate can no longer drop a name
  from a tall rectangle nor overflow a long one out of a narrow box. Each burn sparkline's
  budget reference buys the same 1.15 headroom the S-curve has: under budget it sat on `y = 0`
  with half its stroke clipped by the viewBox, reading as a box edge or as absent.
- **The attention rail prints its severity.** Each card's 6px stripe was the only carrier,
  and the four RAG tokens sit 1.01–1.44:1 apart from *each other* — red beside amber, green
  beside unknown — so the stripe said "a severity" and never which one. The rail now renders
  the same severity badge the threat board does, off the same closed vocabulary. A card whose
  class comes from the data must print that word: `login.html`'s literal `sev-red` error alert
  is outside the rule by construction, not by an exemption a fix could be added to.
- **The dashboard's "unchanged" trend badge says unchanged.** It shipped as a bare en dash with
  the whole meaning in a `title=` — hover only: no keyboard, no touch, no print, and not
  announced on a non-interactive span. The glyph is now `aria-hidden` with the words beside it
  in an `sr-only` span. The guard that already covered the threat board named `home.html` as
  owed and skipped it, so the one file still failing was the one file certified; the exemption
  is gone and the rule is total.
- **A figure is spelled the same way in the label as on the page.** The burn sparkline announced
  `Actual 800.0 of budget 1000.0` while its own row printed `800` and `1,000`, and the cost
  S-curve announced `1000`. Both go through `{:,.0f}` now, and the page walk reads every
  `aria-label` back, so a raw float or an unseparated thousand cannot reach a reader's ear.
- **The portfolio treemap's links are reachable.** The SVG claimed `role="img"`, which tells a
  reader it is a single graphic and prunes its subtree: both portfolio-rollup links inside it,
  and the `<title>` naming each one, were unreachable rather than merely unlabelled. The role is
  dropped — the `aria-label` still names the graphic — so the treemap reads as what it is, a set
  of named portfolio links. No `role="img"` SVG may hold a link.
- The department drill page's statement ceiling can **fail on the N+1 it names** again:
  `_MAX_DETAIL_STMTS` sat at 28 while the page measured 23, so the per-person regression the
  comment exists to catch — swapping the batched `person_task_loads` for one
  `person_task_load` per person shown — cost three statements, landed at 26, and the whole
  file stayed green with the N+1 live. Five statements of slack against a three-statement
  defect, the same shape as `MAX_PROJECT_HUB_STMTS` before it was re-derived. Both pages were
  re-measured rather than trusted (list 21, drill 23 — the recorded figures held) and the
  drill ceiling is now 24, measured + the one statement `tests/test_perf_n1.py` allows a call
  whose defect is priced in the unit it walks one of. Reintroducing the N+1 now fails it at 26
  against 24. The list ceiling is left at 27: its two named regressions were measured at 81
  (lazy baseline hierarchy) and 57 (per-project cost read), both an order of magnitude clear
  of it, so it was already a guard rather than decoration. Every measurement is recorded
  beside the constant so the next reader re-derives nothing.
- A process-map cell now drills into **this project's** reading of the process, not
  the theory page: `/pmbok/{id}?project={id}&as_of={date}` carries the project and the
  pinned as-of through the hop and adds the live status of every artifact its ITTO
  names (`mapping.resolve`), the project's computed process state, and the knowledge
  area's assessment with the live threats and recommended actions attached — then links
  back to the map the reader came from instead of the theory grid. A kind the store
  holds no data for reads *not tracked* rather than *absent*, and a process with no
  tracked output says so in words, so the nine Monitoring & Controlling cells that read
  "not started" forever finally reach the evaluator that is shouting about them.
  Without `?project=` the page is the stateless reference it always was.
- A process the catalog **never tracked** stops reading as work not started. 26 of the 49
  processes name no output the store holds a resolver for, so the state computed for them is
  `not_started` about the STORE — there is nothing to look for, so nothing is ever found —
  and every project's map printed that in 26 of its 49 cells as a verdict on the *project*:
  work it owes and has not begun. Nothing is owed on any of them. Those cells now read
  **Not Tracked**, in the grid and in the sign-off picker beneath it, the same word an
  artifact with no resolver already reads on the drill page. It is a word rather than a sixth
  mark, so it needs no legend chip to be read in greyscale or in print, and `ProcessState`
  keeps the five members the rollup, the wizard, the report and the API count on. A recorded
  decision still outranks it: waive or sign off an untracked process and its cell shows the
  decision that was signed.
- A page template that names something no route passed now **raises** instead of
  rendering the empty string. `report/engine.py` was made strict; the ~22 HTML page
  templates rendered through `web/templating.py` kept Jinja's default `Undefined`, so
  misspelling `{{ as_of }}` as `{{ as_off }}` on the department list printed
  `As of <strong></strong>` — the date gone — and the page still answered 200 with the
  web suite green. The shared environment is now built here rather than by Starlette's
  `directory=`, with `undefined=StrictUndefined`, so a missing or misspelt name stops
  the render and says which name, for all 22 templates at once and for pages not
  written yet. No template needed a fix: every route already passes every name its page
  uses, proven by walking every GET page the app registers against two stores — one
  with work under every row, and one with the rows bare, which is the only way an
  empty-state branch renders at all.
- The Process Map **document** now pins its completeness and its grid to **the engine's own
  answer**, not to the presence of a label. `tests/test_report_itto_docs.py` asserted only that
  the string `Completeness:` appeared — and the template prints that label unconditionally, so
  the test passed whether the figure read `9%`, `0%`, `n/a`, or nothing at all. Dropping the
  `* 100` in `report/documents/process_map.py` rendered `0%` and the file stayed green;
  typo'ing the template variable rendered the label with **no value** and the whole suite
  stayed green, because the report Jinja environment leaves an undefined name empty rather
  than raising. The test now walks `state.completeness` and `state.project_process_states`
  itself and requires the rendered percentage to match, and all 49 table rows to match id,
  name, group, area and state in catalog order — after first asserting the fixture is
  part-done and its states disagree, so a flat or blank document cannot satisfy either
  equality, and no expected figure needs editing when the fixture grows.
- A **waived process no longer looks exactly like an untouched one**. The process map
  drew all five states in colour alone — and two of them, `waived` and `not_started`, in
  the *same* neutral wash, so the legend shipped two identical grey chips under two
  labels for a distinction the grid never drew (a waiver drops a process from every
  completeness figure; not-started counts against it). Each state now also carries a
  visible **mark** — `○` not started, `◐` in progress, `●` produced,
  `✓` signed off, `—` waived — printed both in the cell and on the legend chip
  that names it, so the state reads in greyscale, in print and to a colour-blind reader,
  with colour only reinforcing it. The off-screen word and the hover title stay; neither
  was ever visible. On the business-wide map each cell now **prints its share** as a
  figure instead of carrying it only as a wash and a `title=`.
- Earned value is read at the date it is asked for, so an EV-derived trend can finally
  say "better" or "worse". `Task.percent_complete` is one undated *current* number and
  the EVM adapter stamped it with the as-of being asked about, so EV came out identical
  at any two as-ofs inside the plan window and every arrow comparing them could only
  read "flat". The series was never missing — the append-only ChangeLog has held it all
  along — so the assessment path replays it instead of inventing one. No new table, no
  migration. A logged change counts for an as-of on or after its own UTC date; a task
  reads as entered before its first dated change; and a reading the log cannot date — a
  task's creation, or a store written without the audit listener — answers every as-of,
  so no existing store starts reading zero.
- A report template that names something no document passed now **raises** instead of
  rendering the empty string. Under Jinja's default `Undefined`, misspelling
  `{{ completeness }}` as `{{ completness }}` made the Process Map print
  `**Completeness:** ` with no figure — and the whole suite still passed, because a
  vanished number looks like nothing at all. `report/engine.py` now sets
  `undefined=StrictUndefined`, so the render stops and names the missing variable, for
  every document at once and for templates not written yet, rather than one pinned
  assertion per document catching its own symptom after the fact. No template needed a
  fix: every document already passes every name it uses, proven by rendering all eleven
  for every seeded project across six as-of dates.
- **Risk threat scores are now one unit, so any two are comparable.** The score was
  a share of contingency when a reserve existed and raw dollars when none was held
  (a $1 denominator floor guarding the division), so a $600 uncovered exposure scored
  600.0 and outranked a $45,000 one scoring 29.0 on `/threats`, the dashboard attention
  rail and `assessment.md`. It is now the uncovered exposure as a share of the budget
  left to spend, in every case. **Every risk threat score changes**, so a threat
  sign-off recorded against the old number no longer suppresses it — re-sign the ones
  you still accept.
- A project with no approved plan, and any project asked about an as-of before its plan
  began, no longer reads red on risk. With no budget there is no reserve to fall short
  of, so the evaluator answers "nothing to assess" (green) — the same answer the cost
  evaluator already gives at BAC 0 — instead of reading every open risk as uncovered.
- The dashboard's business S-curve now takes its date range from the approved plan,
  like every figure drawn on it. It read the newest baseline of any status, so drafting
  a re-baseline that started earlier stretched the chart back over months the plan had
  not begun — months that earn nothing — and the curve filled with zeroes that looked
  like reported figures. A project whose only baseline is an unapproved draft now reads
  as unbaselined, the same empty state it shows everywhere else.
- A threat sign-off now records the score the server computed at that as-of, instead of
  the `signal` the caller posted. An arbitrarily large posted value used to mute a threat
  permanently — no live score could ever climb past it, so the promised re-arm on a
  regression silently never fired. The field is gone from `SignOffIn` and from the
  `POST /sign-off` form handler, so there is nothing left for a caller to influence; a
  sign-off whose subject is not a currently-scored threat (a process decision, or a threat
  that is not live) records no signal, and a signal-less sign-off never suppresses.
- **The weekly-status trend stops hiding a reading in a tooltip.** Each dot carried a
  `<title>` with its date and percent, inside an SVG marked `role="img"` — a role that makes
  the whole chart one node and prunes everything beneath it, so that string reached a mouse
  pointer and nobody else while reading, in the source, like the text alternative it is not.
  It was also a duplicate: the axis names both dates and the table twin beside the chart
  already prints date, percent **and** RAG for every snapshot, which the tooltip never
  carried. The tooltip is gone rather than the role — neither chart on this page holds a
  link for `role="img"` to prune, so the role is doing its job, and the label plus the twin
  are the alternative it promises.
- **A weekly status with no cost baseline names the next step.** The planned-vs-actual slot
  fell back to one italic line that named no command and no link, so the reader was told the
  curve was missing and left to guess how to get it. It now renders the shared empty state
  every other surface uses, naming `POST /baselines`, `POST /baseline-lines` and
  `POST /cost-entries`, and linking the wizard that walks them in order. The empty-state walk
  reaches `/projects/{id}/status` now, so a slot on this page cannot go back to saying
  nothing.
- The weekly-status trend plots **elapsed time**, not row number. Every point sat at
  `34 + index / span * 274`, so three readings taken a day apart and a fourth taken three
  months later drew as four evenly spaced points and the slope between them reported a rate
  of progress the dates never supported. Nothing enforces a weekly cadence — the only rule
  on the series is one row per project per **date** (`uq_status_snapshot_project_date`) and
  the form writes at whatever `as_of` it is posted. Each point now carries its position
  along the real span, computed in `pages.trend_series`, and the axis ends name the two
  dates it is drawn between. (The dashboard S-curve, burn sparkline and EVM curve stay
  index-plotted, honestly: their samples come from `gather.sample_dates`, evenly spaced by
  construction. This series is stored rows at operator-chosen dates, so it cannot.)
- Each snapshot's RAG is **readable as a word**. It was carried by the dot's fill (adjacent
  RAG values sit 1.01–1.31:1 apart, and each dot contrasts 1.06:1 with the line it sits on)
  and a hover-only `<title>` inside an SVG marked `role="img"`, which prunes it — so the RAG
  history was reachable by nobody but a mouse user with normal colour vision. The trend now
  carries a text twin: date, percent and RAG per snapshot, in the `scroll.wide` idiom the
  S-curve twin already uses.
- **A weekly status with no readings names the next step too.** The trend slot fell back to
  one italic line that named no command and no link — the same defect its planned-vs-actual
  neighbour had just been fixed for, left standing because converting it exposed the fixture
  hole below. It now renders the shared empty state, linking the snapshot form at the foot of
  the same page and naming `POST /status-snapshots`, and says why one reading draws no slope.
  The two slots empty independently and are filled by different actions, so the empty-state
  walk now pins both ids rather than accepting whichever one happens to render.
- **The weekly-status trend chart is walked for accessibility at all.** The a11y and
  responsive walks share one fixture, and it seeded no `StatusSnapshot` — so the trend drew
  its empty branch, which carried no `empty-state` class, so the page did not read as blank
  and nothing complained. Every rule both walks apply — one `<h1>`, scoped and captioned
  tables, no raw float in an `aria-label`, a named and focusable scroll box around each wide
  table — had therefore never once been applied to that chart's markup. The fixture seeds two
  dated snapshots a quarter apart, so the line, both axis ends and the table twin are rendered
  and walked; all four rules already held.
- **Severity is styled for the whole vocabulary, not for the two values that reached a
  card.** `base.html` declared `.sev-red` and `.sev-amber` only, so a `green` or
  `unknown` severity — the attention rail's data-signal items are `unknown` — drew no
  stripe at all, making "no severity shown" read exactly like "not a severity we style",
  and its severity badge inherited no fill: white ink on the white page, 1.00:1, the
  word invisible. All four RAG statuses now carry a stripe and a rated badge fill, and
  the test walks `calc.rollup.RAG_SEVERITY` rather than a hand-kept list, so a new
  member of the vocabulary cannot reach a card unstyled.
- **The "unchanged" trend badge says unchanged.** On the threat board it was a bare en
  dash with the whole meaning in a `title=` — hover only: no keyboard, no touch, no
  print, and not announced on a non-interactive span. The glyph is now `aria-hidden`
  with the words beside it in an `sr-only` span, the shape the process map already uses.
  (The same badge on the dashboard rail is still `title=`-only.)
- **Completion rings no longer borrow an all-clear.** Both process maps drew the arc in
  `--rag-green` at every level, so 5% complete was painted the colour reserved for
  "green status". The arc is now `currentColor` — the same ink the ring prints its own
  percentage in — over the unchanged 15%-opacity track.
- **The portfolio treemap is readable, and no longer claims an area it is not drawing.**
  Every label was painted in `--ink` over its own RAG rectangle — 2.66–3.48:1 in light and
  1.74–2.51:1 in dark, with the `.8`-opacity budget line down to 2.37:1, so all eight
  pairings sat under the 4.5:1 WCAG AA floor for 10.4px text. Labels now take
  `--badge-ink`, the token that exists to sit on a RAG fill (5.00–6.54:1 light,
  5.93–8.56:1 dark), and carry no opacity. Separately, a store with portfolios but no
  approved baseline anywhere drew every portfolio as an equal slice of the canvas under a
  heading and an `aria-label` that both promise area proportional to BAC; with no budget
  to divide there is no honest area, so the chart is replaced by the shared empty state
  naming the next step (`POST /baselines`) — the answer the Gantt already gives for the
  same missing input.
- The Weekly Status Report no longer prints cost variance `0.00` and schedule
  variance `0.00` for a project with no approved plan. A variance is a distance
  from a plan, so with no plan both now read `n/a` — the same answer CPI, SPI and
  EAC already gave in the same table, instead of a zero that read "exactly on
  budget, exactly on schedule" for a project with neither. Projects with an
  approved baseline are unchanged.
- **The wizard's producer no longer writes prose nobody typed** — `driftless wizard apply
  --kind assumption_log` (or any narrative kind) with no `--field body=` used to file
  `(seeded by the onboarding wizard)` as the project's own assumption log. It now refuses,
  the way the browser form already answers `422`: a message on stderr and exit 2. The
  request schema never caught this — `body` defaults to empty there — and the row that
  landed read *absent* to the process-state engine anyway, so the wizard reported an output
  every completeness figure still counted missing. The placeholder moved to
  `wizard.cli.seed_fields`, the seeding side that means it, so an unattended onboarding run
  still converges with nothing typed.

### Security
Both entered late — written off the code as it stands, newest first.

- **The operator's age private key cannot enter the image, and no deployment file points at one
  inside the build context.** `docker compose up --build` sends the whole repository to the daemon,
  and an image layer is permanent: `docker save` recovers a file copied in even after a later step
  deletes it. The `Dockerfile` did `COPY deploy ./deploy` while `OPERATIONS.md` had operators run
  `age-keygen -o deploy/age-key.txt`, so a build on the operator's own machine baked the key that
  decrypts `deploy/secrets.enc.env` — `DRIFTLESS_SESSION_SECRET` (forge any user's cookie),
  `DRIFTLESS_API_TOKEN`, `POSTGRES_PASSWORD` — into the image beside the encrypted overlay.
  `.gitignore` named the key and did nothing; git's ignore rules have no effect on a build context.
  Robust first: the image copies `deploy/entrypoint.sh` by name, so the key cannot enter even with no
  `.dockerignore` at all. `.dockerignore` is the second lock, the docs now generate the key at
  `~/.config/driftless/age-key.txt` outside the checkout, and the compose mount is
  `${DRIFTLESS_AGE_KEY:?…}` with no fallback — the old default pointed back at `./deploy/age-key.txt`,
  a value nobody typed aimed at the one directory a build would bake. `tests/test_docker_build_context.py`
  derives all three checks from `.gitignore`'s own secret section, so a pattern added there fails the
  suite until `.dockerignore` and the compose file learn it too.

- **The sign-off ledger records the signer the gate resolved, not the one the request claimed.**
  `signed_by` was an ordinary request field on both write paths, so any contributor could POST
  `signed_by="CFO"` — or edit the hidden input on the threat board's form — and append a permanent,
  un-deletable approval in somebody else's name, which is the one thing the ledger exists to prevent.
  Where the gate resolved a principal the server now stamps that username and discards the request's
  claim, the shape `StatusSnapshot` already used for its stamped percent; discarded rather than
  refused, because both browser forms post the field on every sign-off, and the 201 body carries the
  name actually stored. The on-behalf-of write survives and is now pinned by a test: the shared
  `DRIFTLESS_API_TOKEN` bearer resolves no principal by design, so an importer or an agent recording a
  decision a named human made offline still supplies the name — the only path that can.
- **The dependency audit runs. It never had.** `pip-audit` installed itself with the
  runner's system `pip`, which PEP 668 refuses (`externally-managed-environment`), so the
  step died before the tool existed — and a gate step skipped it on every pull request that
  did not touch a dependency file, which is nearly all of them. Of the 44 runs since this
  repository was extracted, 43 skipped the audit and the one scheduled run that reached it
  failed there. It now pins its interpreter with `actions/setup-python` and installs
  `pip-audit` into its own virtualenv, so nothing it does can touch a system Python.
- **The audit scans what the image ships.** A new `requirements.lock` records the resolved
  version of every dependency and is used as a *constraint* file by both the test job and
  the audit, so the two of them and the Docker image no longer resolve "latest" three times
  independently. The audit installs `uvicorn` alongside `.[dev]` because the image's own
  install line does, and a green audit that omitted the web server said nothing about it.
- **A red nightly now has a reader.** A scheduled run that fails opens a GitHub issue and
  comments on that same issue thereafter, so a week of red nights is one thread rather than
  seven — or, as before, nothing at all. That silence is why the broken audit above went
  unnoticed from extraction until an audit went looking for it.

### Docs
- `OPERATIONS.md` and `docs/admin-guide.md` now describe the health probe as the route
  became: one `SELECT 1` behind the container healthcheck, open to an orchestrator because
  it discloses only whether the store answered. The guide runs the probe rather than
  asserting it, and a new `tests/test_docs_health_truthfulness.py` fences the old prose
  against the route's real behaviour. The request-log section names the shipped
  `deploy/logging.json` the image already passes to uvicorn, instead of describing a
  document an operator has to author.
